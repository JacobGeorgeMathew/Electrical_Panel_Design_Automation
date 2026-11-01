"""Offline imports for user-provided catalog sheets and datasheets."""
import csv
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from .config import ROOT
from .normalize import normalize_manual_record
from .store import all_records, upsert, reject
from .dedupe import dedupe_key
from .validate import validate_record

ALIASES = {
    "part number": "part_number", "order code": "part_number", "catalog number": "part_number", "mpn": "part_number", "sku": "part_number",
    "product name": "name", "product": "name", "rated current": "current_rating", "rated current a": "current_rating",
    "breaking capacity ka": "breaking_capacity", "breaking capacity": "breaking_capacity", "no of poles": "poles", "number of poles": "poles",
    "rated voltage": "voltage_rating", "voltage rating": "voltage_rating", "heat loss w": "heat_loss", "power loss": "heat_loss",
    "overall dimensions": "dimensions", "dimensions mm": "dimensions", "width mm": "width", "height mm": "height", "depth mm": "depth",
    "datasheet": "datasheet_url", "product url": "product_url", "cad url": "cad_url", "manufacturer name": "manufacturer",
    "ip rating": "ip_rating", "standard": "standards", "standards": "standards", "source url": "source_url",
}

def canonical_header(value):
    key = re.sub(r"[_\-]+", " ", str(value or "").strip().lower())
    return ALIASES.get(key, key.replace(" ", "_"))

def _read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))

def _read_xlsx(path):
    try:
        from openpyxl import load_workbook
    except ImportError:
        load_workbook = None
    if load_workbook:
        book = load_workbook(path, read_only=True, data_only=True)
        sheet = book.active
        rows = sheet.iter_rows(values_only=True)
        headers = [str(x or "").strip() for x in next(rows, ())]
        result = [dict(zip(headers, values)) for values in rows if any(v not in (None, "") for v in values)]
        book.close()
        return result
    # Minimal standards-based OpenXML reader for simple single-sheet catalog workbooks.
    ns={"m":"http://schemas.openxmlformats.org/spreadsheetml/2006/main","r":"http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    with zipfile.ZipFile(path) as archive:
        strings=[]
        if "xl/sharedStrings.xml" in archive.namelist():
            tree=ET.fromstring(archive.read("xl/sharedStrings.xml"))
            strings=["".join(t.text or "" for t in item.findall(".//m:t",ns)) for item in tree.findall("m:si",ns)]
        sheet_path="xl/worksheets/sheet1.xml"
        if "xl/workbook.xml" in archive.namelist() and "xl/_rels/workbook.xml.rels" in archive.namelist():
            workbook=ET.fromstring(archive.read("xl/workbook.xml")); rels=ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            first=workbook.find("m:sheets/m:sheet",ns)
            if first is not None:
                rid=first.attrib.get(f"{{{ns['r']}}}id")
                relationship=next((r for r in rels if r.attrib.get("Id")==rid),None)
                if relationship is not None:
                    target=relationship.attrib["Target"].lstrip("/")
                    sheet_path=target if target.startswith("xl/") else "xl/"+target
        sheet=ET.fromstring(archive.read(sheet_path))
        matrix=[]
        for row in sheet.findall(".//m:sheetData/m:row",ns):
            cells=[]
            for cell in row.findall("m:c",ns):
                ref=cell.attrib.get("r",""); col=0
                for char in re.match(r"[A-Z]+",ref).group(0): col=col*26+(ord(char)-64)
                while len(cells)<col: cells.append(None)
                typ=cell.attrib.get("t"); value=cell.findtext("m:v",default="",namespaces=ns)
                if typ=="s" and value: value=strings[int(value)]
                elif typ=="inlineStr": value="".join(t.text or "" for t in cell.findall(".//m:t",ns))
                elif value=="": value=None
                cells[col-1]=value
            matrix.append(cells)
    if not matrix: return []
    headers=[str(v or "").strip() for v in matrix[0]]
    return [dict(zip(headers,row)) for row in matrix[1:] if any(v not in (None, "") for v in row)]

def _read_json(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("records", data.get("items", [data]))
    if not isinstance(data, list):
        raise ValueError("JSON must contain an array of records or an object with records/items.")
    return data

def _read_pdf(path):
    from .parsers.pdf_tables import parse_pdf_tables
    parsed = []
    for table in parse_pdf_tables(path):
        rows = table["rows"]
        if not rows:
            continue
        headers = [canonical_header(x) for x in rows[0]]
        for cells in rows[1:]:
            if len(cells) != len(headers):
                continue
            record = dict(zip(headers, cells))
            if any(str(v or "").strip() for v in cells):
                record["page_number"] = table["page"]
                record["raw_text"] = " | ".join(str(x or "") for x in cells)
                parsed.append(record)
    return parsed

def _read_bmecat(path):
    root = ET.parse(path).getroot()
    catalog_currency=next(((x.text or "").strip() for x in root.iter() if x.tag.split("}")[-1]=="CATALOG_CURRENCY" and (x.text or "").strip()),None)
    rows = []
    for product in root.iter():
        if product.tag.split("}")[-1] not in {"PRODUCT", "ARTICLE"}:
            continue
        values = {}
        raw_attributes = []
        currency = catalog_currency
        price = None
        for item in product.iter():
            tag = item.tag.split("}")[-1]
            text = (item.text or "").strip()
            if tag == "SUPPLIER_PID": values["part_number"] = text
            elif tag == "DESCRIPTION_SHORT": values["name"] = text
            elif tag == "DESCRIPTION_LONG": values["description"] = text
            elif tag == "MANUFACTURER_NAME": values["manufacturer"] = text
            elif tag == "MANUFACTURER_TYPE_DESCR": values["series"] = text
            elif tag == "ARTICLE_GROUP_ID": values["article_group_id"] = text
            elif tag in {"PRODUCT_WIDTH", "WIDTH"} and text: values["width"] = text
            elif tag in {"PRODUCT_HEIGHT", "HEIGHT"} and text: values["height"] = text
            elif tag in {"PRODUCT_DEPTH", "PRODUCT_LENGTH", "DEPTH", "LENGTH"} and text: values["depth"] = text
            elif tag in {"PRODUCT_WEIGHT", "WEIGHT"} and text: values["weight"] = text
            elif tag == "PRICE_AMOUNT" and text:
                price = text
        for feature in product.iter():
            if feature.tag.split("}")[-1] != "FEATURE": continue
            feature_values={child.tag.split("}")[-1]:(child.text or "").strip() for child in feature.iter() if child is not feature and (child.text or "").strip()}
            if feature_values:
                raw_attributes.append({"name":feature_values.get("FNAME"),"value":feature_values.get("FVALUE"),"unit":feature_values.get("FUNIT"),"unit_code":feature_values.get("FUNIT_CODE")})
                feature_name=(feature_values.get("FNAME") or "").casefold()
                feature_value=feature_values.get("FVALUE")
                if feature_value and "rated current" in feature_name: values["current_rating"]=feature_value
                elif feature_value and "breaking capacity" in feature_name: values["breaking_capacity"]=feature_value
                elif feature_value and "number of poles" in feature_name: values["poles"]=feature_value
                elif feature_value and "rated voltage" in feature_name: values["voltage_rating"]=feature_value
                elif feature_value and "power loss" in feature_name: values["heat_loss"]=feature_value
        if price:
            values["price"] = json.dumps({"amount": price, "currency": currency}, ensure_ascii=False)
        if raw_attributes: values["bmecat_features"] = json.dumps(raw_attributes, ensure_ascii=False)
        # Retain feature names/values and units as raw BMEcat fields; no unit is fabricated here.
        if values:
            values["raw_text"] = json.dumps(values, ensure_ascii=False)
            rows.append(values)
    return rows

def _source_row(row, source_id, path, index):
    clean = {canonical_header(k): (v.strip() if isinstance(v, str) else v) for k,v in row.items() if k is not None}
    page = clean.get("page_number")
    if isinstance(page,str) and page.isdigit(): page=int(page)
    clean["page_number"] = page
    raw_text = clean.get("raw_text")
    if not raw_text:
        raw_text = " | ".join(f"{k}={v}" for k,v in clean.items() if v not in (None, ""))
    provenance = {}
    for key,value in clean.items():
        if value not in (None, "") and key not in {"raw_text", "page_number", "notes", "source_url", "document_name", "retrieved_on"}:
            provenance[key] = {"raw_text": str(value), "file": path.name, "page": page, "source_url": clean.get("source_url"), "row": index}
    return {**clean, "source_id": source_id, "raw_text": raw_text, "provenance": provenance,
            "file_provenance": {"file": path.name, "page": page, "source_url": clean.get("source_url"),
                                "document_name": clean.get("document_name") or path.name,
                                "retrieved_on": clean.get("retrieved_on"), "row": index,
                                "notes": clean.get("notes")}}

def _merge(old, new):
    merged = dict(old)
    old_sources = list(merged.get("source_observations", []))
    observation={"source_id": new.get("source_id"), "product_url": new.get("product_url"),
                 "file_provenance": new.get("file_provenance"), "raw_text": new.get("raw_text"),
                 "provenance": new.get("provenance", {})}
    if observation not in old_sources:
        old_sources.append(observation)
    merged["source_observations"] = old_sources
    merged.setdefault("provenance", {}).update(new.get("provenance", {}))
    for key,value in new.items():
        if merged.get(key) in (None, "", [], {}) and value not in (None, "", [], {}):
            merged[key] = value
    return merged

def import_file(path, source_id):
    path = Path(path).expanduser().resolve()
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        inbox = (ROOT / "data" / "manual" / "inbox").resolve()
        if not path.is_relative_to(inbox):
            raise ValueError(f"PDFs must be placed in {inbox}; PDFs outside this inbox are not read.")
    if not path.is_file():
        raise FileNotFoundError(path)
    if suffix == ".pdf":
        raw_rows = _read_pdf(path)
    elif suffix == ".csv": raw_rows = _read_csv(path)
    elif suffix == ".xlsx": raw_rows = _read_xlsx(path)
    elif suffix == ".json": raw_rows = _read_json(path)
    elif suffix == ".xml": raw_rows = _read_bmecat(path)
    else: raise ValueError("Supported input formats: CSV, XLSX, JSON, PDF and BMEcat XML.")

    existing = {dedupe_key(r): r for r in all_records() if dedupe_key(r)[1]}
    counts = {"read": len(raw_rows), "template_rows_skipped": 0, "normalized": 0, "accepted": 0, "rejected": 0, "duplicates_merged": 0,
              "accepted_records": [], "rejected_records": []}
    for index,row in enumerate(raw_rows, start=2):
        identity = any(row.get(key) for key in ("id", "part_number", "mpn", "sku", "name", "product name"))
        actual_values = [v for k,v in row.items() if canonical_header(k) not in {"template_family", "notes"} and v not in (None, "")]
        if not actual_values or (row.get("template_family") and not identity):
            counts["template_rows_skipped"] += 1
            continue
        source = _source_row(row, source_id, path, index)
        normalized = normalize_manual_record(source)
        counts["normalized"] += 1
        key = dedupe_key(normalized)
        if key[0] and key[1] and key in existing:
            normalized = _merge(existing[key], normalized)
            counts["duplicates_merged"] += 1
        reasons = validate_record(normalized)
        if reasons:
            reject(normalized, reasons); counts["rejected"] += 1
            counts["rejected_records"].append({"id": normalized.get("id"), "part_number": normalized.get("part_number"), "category": normalized.get("category"), "reasons": reasons})
        else:
            upsert(normalized, "validated"); existing[key] = normalized; counts["accepted"] += 1
            counts["accepted_records"].append({k: normalized.get(k) for k in ("id", "name", "category", "current_rating", "breaking_capacity", "poles", "width", "height", "depth", "heat_loss", "part_number", "source_id", "provenance")})
    counts["source_id"] = source_id
    counts["input_file"] = path.name
    return counts
