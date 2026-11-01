import argparse
import json
from datetime import datetime, timezone
from .config import ROOT, DATA_ROOT, load_yaml, source_config
from .sources import get_source
from .store import upsert, all_records, reject
from .validate import validate_record
from .export_catalog import export
from .report import generate_report
from .manual_import import import_file
from .official_connectors import SchneiderProductCatalogApi

def run(args):
    if args.command == "discover":
        sid, cfg = source_config(args.source)
        print(json.dumps({"source_id": sid, "permission": cfg.get("permission", "UNVERIFIED"), "candidate_urls": get_source(sid,cfg).discover_product_urls()}, indent=2))
    elif args.command == "scrape":
        sid,cfg=source_config(args.source); source=get_source(sid,cfg); urls=source.discover_product_urls()[:args.limit]
        if cfg.get("permission") not in {"ALLOWED", "ALLOWED_WITH_LIMITS"}:
            print(f"Blocked: {sid} permission={cfg.get('permission')}; no page requests made.")
            return 2
        fetched=0
        for url in urls:
            body,meta=source.fetch(url)
            cache_key=__import__('hashlib').sha256(url.encode()).hexdigest()
            (DATA_ROOT/"raw"/(cache_key+".meta.json")).write_text(json.dumps({**meta,"source_id":sid}),encoding="utf-8")
            fetched+=1
        print(f"Fetched {fetched} permitted pages for {sid}.")
    elif args.command == "parse":
        sid,cfg=source_config(args.source); source=get_source(sid,cfg); raw=DATA_ROOT/"raw"; parsed=0
        if raw.exists():
            for meta_path in raw.glob("*.meta.json"):
                meta=json.loads(meta_path.read_text(encoding="utf-8"))
                if meta.get("source_id") != sid: continue
                body_path=meta_path.with_name(meta_path.name.replace(".meta.json",".body"))
                for row in source.parse(body_path.read_bytes(),meta):
                    row["scraped_at"]=meta.get("fetched_at") or datetime.now(timezone.utc).isoformat()
                    upsert(row,"raw"); parsed+=1
        print(f"Parsed {parsed} product records from cached pages for {sid}.")
    elif args.command == "normalize":
        count=0
        for row in all_records():
            if "raw_fields" in row and "raw_product" in row:
                normalized=normalize_record(row); upsert(normalized,"normalized"); count+=1
        print(f"Normalized {count} records.")
    elif args.command == "validate":
        valid=rejected=0
        for row in all_records():
            reasons=validate_record(row)
            if reasons: reject(row,reasons); rejected+=1
            else: upsert(row,"validated"); valid+=1
        print(json.dumps({"valid":valid,"rejected":rejected},indent=2))
    elif args.command == "import-file":
        result=import_file(args.path,args.source)
        print(json.dumps(result,indent=2))
        print(json.dumps({"export":export()},indent=2))
    elif args.command == "import-schneider-api":
        try: SchneiderProductCatalogApi().import_products()
        except RuntimeError as exc:
            print(str(exc))
            return 2
    elif args.command == "export": print(json.dumps(export(),indent=2))
    elif args.command == "report": print(json.dumps(generate_report(),indent=2))
    elif args.command == "permissions":
        print(json.dumps({sid:{"permission":cfg.get("permission","UNVERIFIED"),"note":cfg.get("access_note")} for sid,cfg in load_yaml("sources.yaml")["sources"].items()},indent=2))
    elif args.command == "run-all":
        sources=load_yaml("sources.yaml")["sources"]
        for sid,cfg in sources.items():
            if cfg.get("permission") in {"ALLOWED", "ALLOWED_WITH_LIMITS"}:
                child=argparse.Namespace(command="scrape",source=sid,limit=args.limit)
                if run(child): return 2
                run(argparse.Namespace(command="parse",source=sid))
        for command in ("normalize","validate","export","report"):
            run(argparse.Namespace(command=command))
    return 0

def main():
    parser=argparse.ArgumentParser(prog="pipeline")
    subs=parser.add_subparsers(dest="command",required=True)
    p=subs.add_parser("discover");p.add_argument("--source",required=True)
    p=subs.add_parser("scrape");p.add_argument("--source",required=True);p.add_argument("--limit",type=int,default=20)
    p=subs.add_parser("parse");p.add_argument("--source",required=True)
    for command in ("normalize","validate","export","report","permissions"):
        subs.add_parser(command)
    p=subs.add_parser("run-all");p.add_argument("--limit",type=int,default=20)
    p=subs.add_parser("import-file");p.add_argument("--path",required=True);p.add_argument("--source",required=True)
    subs.add_parser("import-schneider-api",help="disabled placeholder; requires written permission and API credentials")
    try: code=run(parser.parse_args())
    except (KeyError,RuntimeError,ValueError) as exc:
        parser.exit(2,f"pipeline: {exc}\n")
    raise SystemExit(code or 0)

if __name__ == "__main__": main()
