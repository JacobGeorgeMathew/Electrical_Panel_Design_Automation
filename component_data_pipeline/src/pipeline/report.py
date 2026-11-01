import json
from collections import Counter, defaultdict
from .config import ROOT, DATA_ROOT
from .store import all_records, rejected_rows

FIELDS = ("current_rating", "breaking_capacity", "poles", "width", "height", "depth", "mounting", "heat_loss", "terminals", "manufacturer", "part_number", "datasheet_url", "voltage_rating", "ip_rating")

def generate_report():
    records = all_records(status="validated")
    rejected = rejected_rows()
    counts = Counter((r.get("source_id"), r.get("category")) for r in records)
    completeness = defaultdict(Counter)
    totals = Counter()
    for row in records:
        category=row.get("category") or "UNKNOWN"; totals[category]+=1
        for field in FIELDS:
            completeness[category][field] += row.get(field) is not None
    percentages = {category:{field:round(100*completeness[category][field]/count,1) for field in FIELDS} for category,count in totals.items()}
    reasons=Counter(reason for _,items in rejected for reason in items)
    examples=[]
    for row in records:
        for field, provenance in (row.get("provenance") or {}).items():
            if field in row and isinstance(provenance,dict) and provenance.get("raw_text") is not None:
                examples.append({"field":field,"raw_text":provenance["raw_text"],"normalized_value":row.get(field),"file":provenance.get("file"),"page":provenance.get("page"),"source_url":provenance.get("source_url")})
                if len(examples)==5: break
        if len(examples)==5: break
    gaps=[]
    if not records:
        gaps.append("No validated real product records have been imported.")
    for category,values in percentages.items():
        for field,percent in values.items():
            if percent < 100:
                gaps.append(f"{category}: {field} is populated for {percent}% of validated records.")
    summary={
        "validated_record_count":len(records),
        "record_counts_by_source_and_category":{f"{s or 'unknown'}:{c or 'unknown'}": n for (s,c),n in counts.items()},
        "rejected_count":len(rejected),
        "rejected_reasons":dict(reasons),
        "completeness_percent":percentages,
        "raw_to_normalized_examples":examples,
        "known_gaps":gaps,
        "project_field_gaps":["Terminal coordinates and clearances require sourced values; missing fields remain null.","Legacy component JSON does not model all category-specific fields (for example SPD Uc/Up/In/Imax/Iimp or RCCB residual-current sensitivity); retain these in full provenance/notes until schema extension is approved."]
    }
    DATA_ROOT.joinpath("exports").mkdir(parents=True, exist_ok=True)
    DATA_ROOT.joinpath("exports", "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    report=["# Data quality report", "", f"Validated records: {len(records)}", f"Rejected records: {len(rejected)}", "", "## Counts by source/category", "", "| Source/category | Count |", "|---|---:|"]
    report += [f"| {key} | {value} |" for key,value in summary["record_counts_by_source_and_category"].items()]
    report += ["", "## Field completeness", "", "| Category | Field | Non-null |", "|---|---|---:|"]
    for category,values in percentages.items():
        report += [f"| {category} | {field} | {percent}% |" for field,percent in values.items()]
    report += ["", "## Rejected reasons", ""]
    report += [f"- {reason}: {count}" for reason,count in reasons.items()] or ["- No rejected rows."]
    report += ["", "## Raw-to-normalized examples", ""]
    report += [f"- `{item['field']}`: `{item['raw_text']}` → `{item['normalized_value']}`" for item in examples] or ["- No sourced conversions available yet."]
    report += ["", "## Known gaps", ""] + [f"- {gap}" for gap in gaps+summary["project_field_gaps"]]
    ROOT.joinpath("docs", "data_quality_report.md").write_text("\n".join(report)+"\n", encoding="utf-8")
    return summary
