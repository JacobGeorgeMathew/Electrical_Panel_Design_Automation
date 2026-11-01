import csv
import json
import sys
import zipfile
from pathlib import Path

import pytest

SRC=Path(__file__).resolve().parents[1]/"src"
sys.path.insert(0,str(SRC))

from pipeline import store
from pipeline import manual_import
from pipeline.normalize import normalize_manual_record
from pipeline.export_catalog import export

FIXTURE=Path(__file__).parent/"fixtures"/"synthetic_sample.csv"

@pytest.fixture
def isolated_db(tmp_path,monkeypatch):
    monkeypatch.setattr(store,"DB",tmp_path/"staging.sqlite")
    return tmp_path

def test_csv_import_normalizes_rejects_and_reruns_idempotently(isolated_db):
    result=manual_import.import_file(FIXTURE,"synthetic_test")
    assert result["accepted"] == 1 and result["rejected"] == 1
    accepted=store.all_records(status="validated")
    assert len(accepted)==1
    row=accepted[0]
    assert (row["current_rating"],row["breaking_capacity"],row["poles"]) == (100,25,3)
    assert (row["width"],row["height"],row["depth"]) == (90,140,75)
    assert row["provenance"]["current_rating"]["raw_text"] == "100 A"
    assert row["file_provenance"]["page"] == 1
    rejected=store.rejected_rows()
    assert len(rejected)==1
    assert "missing required field: width" in rejected[0][1]
    again=manual_import.import_file(FIXTURE,"synthetic_test")
    assert again["accepted"] == 1 and again["rejected"] == 1
    assert len(store.all_records()) == 1
    assert len(store.rejected_rows()) == 1

def test_blank_family_template_rows_are_skipped(isolated_db):
    template=Path(__file__).resolve().parents[1]/"data"/"manual"/"component_template.csv"
    result=manual_import.import_file(template,"manual")
    assert result["read"]==11
    assert result["template_rows_skipped"]==11
    assert result["accepted"]==0 and result["rejected"]==0

def test_json_and_xlsx_inputs(tmp_path,isolated_db):
    payload=[{"manufacturer":"Test Vendor","part_number":"JSON-1","name":"Synthetic MCB","category":"MCB","current_rating":"16 A","breaking_capacity":"10 kA","poles":"1P","width":"18 mm","height":"85 mm","depth":"70 mm"}]
    json_path=tmp_path/"input.json";json_path.write_text(json.dumps(payload),encoding="utf-8")
    result=manual_import.import_file(json_path,"synthetic_json")
    assert result["accepted"]==1
    fields=list(payload[0].keys());values=list(payload[0].values())
    def excel_col(n):
        out=""
        while n:
            n,rem=divmod(n-1,26);out=chr(65+rem)+out
        return out
    def make_row(row_number,cells):
        out=[]
        for index,value in enumerate(cells,1):
            if value is None: continue
            ref=f"{excel_col(index)}{row_number}"
            out.append(f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>')
        return f'<row r="{row_number}">'+''.join(out)+'</row>'
    sheet=f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{make_row(1,fields)}{make_row(2,values)}</sheetData></worksheet>'
    workbook='<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'
    rels='<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
    xlsx_path=tmp_path/"input.xlsx"
    with zipfile.ZipFile(xlsx_path,"w") as archive:
        archive.writestr("xl/workbook.xml",workbook);archive.writestr("xl/_rels/workbook.xml.rels",rels);archive.writestr("xl/worksheets/sheet1.xml",sheet)
    result=manual_import.import_file(xlsx_path,"synthetic_xlsx")
    assert result["accepted"]==1

def test_pdf_import_is_limited_to_inbox_and_keeps_page_provenance(tmp_path,isolated_db,monkeypatch):
    monkeypatch.setattr(manual_import,"ROOT",tmp_path)
    inbox=tmp_path/"data"/"manual"/"inbox";inbox.mkdir(parents=True)
    pdf=inbox/"synthetic.pdf";pdf.write_bytes(b"synthetic placeholder; parser is stubbed in this test")
    table={"page":7,"rows":[["part_number","name","category","current_rating","breaking_capacity","poles","width","height","depth","manufacturer"],
                               ["PDF-TEST","Synthetic MCB","MCB","6 A","6 kA","1P","18 mm","85 mm","70 mm","Test Vendor"]]}
    monkeypatch.setattr("pipeline.parsers.pdf_tables.parse_pdf_tables",lambda _: [table])
    result=manual_import.import_file(pdf,"synthetic_pdf")
    assert result["accepted"]==1
    record=store.all_records(status="validated")[0]
    assert record["page_number"]==7
    assert record["file_provenance"]["file"]=="synthetic.pdf"
    assert record["provenance"]["width"]["raw_text"]=="18 mm"
    with pytest.raises(ValueError,match="PDFs must be placed"):
        manual_import.import_file(tmp_path/"outside.pdf","synthetic_pdf")

def test_bmecat_xml_import(tmp_path,isolated_db):
    xml='''<?xml version="1.0"?><BMECAT><T_NEW_CATALOG><ARTICLE><SUPPLIER_PID>XML-TEST</SUPPLIER_PID><ARTICLE_DETAILS><DESCRIPTION_SHORT>Synthetic item</DESCRIPTION_SHORT><DESCRIPTION_LONG>Fixture only</DESCRIPTION_LONG></ARTICLE_DETAILS><ARTICLE_DETAILS><MANUFACTURER_NAME>Test Vendor</MANUFACTURER_NAME></ARTICLE_DETAILS></ARTICLE></T_NEW_CATALOG></BMECAT>'''
    path=tmp_path/"sample.xml";path.write_text(xml,encoding="utf-8")
    result=manual_import.import_file(path,"synthetic_xml")
    assert result["accepted"]==0
    assert result["rejected"]==1
    assert any("missing or unsupported category" in reason for _,reasons in store.rejected_rows() for reason in reasons)

def test_legacy_export_contains_validated_records_only(isolated_db,tmp_path,monkeypatch):
    monkeypatch.setattr("pipeline.export_catalog.DATA_ROOT",tmp_path/"data")
    manual_import.import_file(FIXTURE,"synthetic_test")
    result=export()
    payload=json.loads((tmp_path/"data"/"exports"/"components.json").read_text(encoding="utf-8"))
    assert result["components"]==1
    assert len(payload)==1
    assert payload[0]["category"]=="MCCB"
    assert "manufacturer" not in payload[0]
