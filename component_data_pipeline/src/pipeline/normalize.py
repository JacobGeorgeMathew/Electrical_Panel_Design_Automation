import json
import re

NUMBER = re.compile(r"[-+]?\d+(?:[.,]\d+)?")

def parse_number(value):
    if value is None or isinstance(value, (int, float)):
        return value
    match = NUMBER.search(str(value).replace(",", "."))
    return float(match.group()) if match else None

def _number(value, unit):
    if value in (None, ""):
        return None
    text = str(value).strip().lower().replace(",", ".")
    number = parse_number(text)
    if number is None: return None
    if unit == "current_rating" and "ka" in text: number *= 1000
    elif unit == "breaking_capacity" and re.search(r"\ba\b", text) and "ka" not in text: number /= 1000
    elif unit in {"width", "height", "depth"} and re.search(r"\bcm\b", text): number *= 10
    elif unit in {"width", "height", "depth"} and re.search(r"\bm\b", text) and "mm" not in text: number *= 1000
    elif unit == "weight" and "kg" in text: number *= 1000
    return number

def normalize_manual_record(raw):
    source = dict(raw)
    category = str(source.get("category") or "").strip().upper().replace(" ", "_")
    category_aliases = {"MINIATURE_CIRCUIT_BREAKER":"MCB", "MOULDED_CASE_CIRCUIT_BREAKER":"MCCB", "MOLDED_CASE_CIRCUIT_BREAKER":"MCCB",
                        "RESIDUAL_CURRENT_CIRCUIT_BREAKER":"RCCB", "RESIDUAL_CURRENT_BREAKER":"RCCB", "SURGE_PROTECTIVE_DEVICE":"SPD",
                        "TERMINAL_BLOCK":"TERMINAL", "NEUTRAL_BAR":"NEUTRAL_BAR", "EARTH_BAR":"EARTH_BAR", "DIN_RAIL":"DIN_RAIL", "ENCLOSURE":"ENCLOSURE"}
    category = category_aliases.get(category, category)
    raw_fields = {k:v for k,v in source.items() if k not in {"provenance", "file_provenance"}}
    pole_value = parse_number(source.get("poles"))
    if isinstance(pole_value,float) and pole_value.is_integer(): pole_value = int(pole_value)
    result = {
        "id": str(source.get("id") or ((re.sub(r"[^A-Za-z0-9]+", "_", str(source.get("manufacturer") or "").strip()).strip("_") + "_") if source.get("manufacturer") else "") + str(source.get("part_number") or "")).strip("_"),
        "name": source.get("name"), "category": category or None,
        "current_rating": _number(source.get("current_rating"), "current_rating"),
        "breaking_capacity": _number(source.get("breaking_capacity"), "breaking_capacity"),
        "poles": pole_value,
        "width": _number(source.get("width"), "width"), "height": _number(source.get("height"), "height"), "depth": _number(source.get("depth"), "depth"),
        "mounting": source.get("mounting"), "heat_loss": _number(source.get("heat_loss"), "heat_loss"),
        "terminals": source.get("terminals") or [], "cad_model": source.get("cad_model"),
        "clearance_top": _number(source.get("clearance_top"), "width"), "clearance_bottom": _number(source.get("clearance_bottom"), "width"),
        "clearance_sides": _number(source.get("clearance_sides"), "width"),
        "mounting_plate_width": _number(source.get("mounting_plate_width"), "width"),
        "mounting_plate_height": _number(source.get("mounting_plate_height"), "height"),
        "mounting_plate_offset_x": _number(source.get("mounting_plate_offset_x"), "width"),
        "mounting_plate_offset_y": _number(source.get("mounting_plate_offset_y"), "height"),
        "mounting_plate_offset_z": _number(source.get("mounting_plate_offset_z"), "depth"),
        "max_thermal_dissipation": _number(source.get("max_thermal_dissipation"), "heat_loss"),
        "zones": source.get("zones"),
        "manufacturer": source.get("manufacturer"), "series": source.get("series"), "part_number": source.get("part_number") or source.get("id"),
        "description": source.get("description"), "datasheet_url": source.get("datasheet_url"),
        "product_url": source.get("product_url") or source.get("source_url"), "cad_url": source.get("cad_url"),
        "weight": _number(source.get("weight"), "weight"), "price": source.get("price"),
        "standards": source.get("standards") or [], "voltage_rating": _number(source.get("voltage_rating"), "voltage_rating"), "ip_rating": source.get("ip_rating"),
        "source_id": source.get("source_id"), "scraped_at": None,
        "source_url": source.get("source_url"), "document_name": source.get("document_name"), "page_number": source.get("page_number"),
        "retrieved_on": source.get("retrieved_on"), "raw_text": source.get("raw_text"), "notes": source.get("notes"),
        "file_provenance": source.get("file_provenance"), "provenance": source.get("provenance", {}), "raw_fields": raw_fields,
    }
    dims = source.get("dimensions")
    if dims:
        values = re.findall(r"\d+(?:[.,]\d+)?", str(dims))
        if len(values) >= 3:
            result["width"], result["height"], result["depth"] = [_number(f"{v} {('mm' if 'mm' in str(dims).lower() else 'cm' if 'cm' in str(dims).lower() else 'mm')}", "width") for v in values[:3]]
            result["provenance"].setdefault("width", {"raw_text": str(dims), "file": result.get("document_name"), "page": result.get("page_number")})
            result["provenance"].setdefault("height", dict(result["provenance"]["width"]))
            result["provenance"].setdefault("depth", dict(result["provenance"]["width"]))
    if isinstance(result["terminals"], str):
        try: result["terminals"] = json.loads(result["terminals"])
        except json.JSONDecodeError: result["terminals"] = []
    if isinstance(result["zones"], str):
        try: result["zones"] = json.loads(result["zones"])
        except json.JSONDecodeError: result["zones"] = None
    if isinstance(result["standards"], str):
        try: result["standards"] = json.loads(result["standards"])
        except json.JSONDecodeError: result["standards"] = [x.strip() for x in re.split(r"[,;|]", result["standards"]) if x.strip()]
    if isinstance(result["price"], str):
        price_text=result["price"].strip()
        try:
            parsed_price=json.loads(price_text)
        except json.JSONDecodeError:
            parsed_price=None
        if isinstance(parsed_price,dict):
            result["price"]={"amount":_number(parsed_price.get("amount"),"price"),"currency":parsed_price.get("currency")}
        else:
            parsed = parse_number(price_text)
            currency = "INR" if "₹" in price_text or "inr" in price_text.casefold() or "rs" in price_text.casefold() else "USD" if "$" in price_text or "usd" in price_text.casefold() else "EUR" if "€" in price_text or "eur" in price_text.casefold() else "GBP" if "£" in price_text or "gbp" in price_text.casefold() else None
            result["price"] = {"amount": parsed, "currency": currency} if parsed is not None else None
    missing = [f for f in ("heat_loss", "terminals", "voltage_rating", "datasheet_url") if result.get(f) in (None, [], "")]
    result["data_quality"] = {"missing_fields": missing}
    return result

def normalize_record(raw):
    fields = raw.get("raw_fields", {})
    product = raw.get("raw_product", {})
    brand = fields.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    return {
        "id": str(fields.get("mpn") or fields.get("sku") or "").strip(),
        "name": fields.get("name"), "category": None,
        "current_rating": None, "breaking_capacity": None, "poles": None,
        "width": None, "height": None, "depth": None, "mounting": None,
        "heat_loss": None, "terminals": [], "cad_model": None,
        "manufacturer": brand, "series": None,
        "part_number": fields.get("mpn") or fields.get("sku"),
        "description": fields.get("description"),
        "datasheet_url": None, "product_url": raw.get("product_url"),
        "cad_url": None, "weight": None, "price": None,
        "standards": [], "voltage_rating": None, "ip_rating": None,
        "source_id": raw.get("source_id"), "scraped_at": raw.get("scraped_at"),
        "raw_fields": fields, "data_quality": {"missing_core_specs": True},
        "provenance": {key: {"raw_text": str(value), "source_url": raw.get("product_url")} for key, value in fields.items()},
        "raw_product": product,
    }
