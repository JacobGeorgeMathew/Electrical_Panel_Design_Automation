import json
import sqlite3
from hashlib import sha256
from .config import DATA_ROOT

DB = DATA_ROOT / "staging.sqlite"

def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB)
    db.execute("CREATE TABLE IF NOT EXISTS records (record_key TEXT PRIMARY KEY, source_id TEXT NOT NULL, product_url TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'raw')")
    db.execute("CREATE TABLE IF NOT EXISTS rejected (record_key TEXT PRIMARY KEY, source_id TEXT, product_url TEXT, payload TEXT NOT NULL, reasons TEXT NOT NULL)")
    db.commit()
    return db

def key(record):
    identity = record.get("part_number") or record.get("id") or ""
    if not identity:
        file_info=record.get("file_provenance") or {}
        identity=sha256(f"{file_info.get('file','')}|{file_info.get('row','')}|{record.get('raw_text','')}".encode()).hexdigest()
    return f"{record.get('source_id','')}|{record.get('product_url','')}|{identity}"

def upsert(record, status="normalized"):
    db = connect()
    record_key=key(record)
    db.execute("INSERT INTO records(record_key,source_id,product_url,payload,status) VALUES(?,?,?,?,?) ON CONFLICT(record_key) DO UPDATE SET payload=excluded.payload,status=excluded.status", (record_key, record.get("source_id") or "", record.get("product_url") or "", json.dumps(record, ensure_ascii=False), status))
    if status == "validated":
        db.execute("DELETE FROM rejected WHERE record_key=?",(record_key,))
    db.commit(); db.close()

def all_records(status=None):
    db = connect()
    query = "SELECT payload FROM records"
    params = ()
    if status:
        query += " WHERE status=?"
        params = (status,)
    query += " ORDER BY record_key"
    rows = [json.loads(row[0]) for row in db.execute(query, params)]
    db.close(); return rows

def reject(record, reasons):
    db = connect(); k = key(record)
    db.execute("INSERT OR REPLACE INTO rejected VALUES(?,?,?,?,?)", (k, record.get("source_id"), record.get("product_url"), json.dumps(record, ensure_ascii=False), json.dumps(reasons)))
    db.execute("UPDATE records SET status='rejected' WHERE record_key=?", (k,))
    db.commit(); db.close()

def rejected_rows():
    db=connect(); rows=[(json.loads(r[0]),json.loads(r[1])) for r in db.execute("SELECT payload,reasons FROM rejected")]; db.close(); return rows
