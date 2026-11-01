import json
from .config import DATA_ROOT
from .store import all_records

LEGACY_FIELDS = ("id", "name", "category", "current_rating", "breaking_capacity", "poles", "width", "height", "depth", "mounting", "heat_loss", "cad_model", "clearance_top", "clearance_bottom", "clearance_sides", "terminals")

def export():
    out = DATA_ROOT / "exports"; out.mkdir(parents=True, exist_ok=True)
    rows = all_records(status="validated")
    components, enclosures = [], []
    for row in rows:
        if row.get("category") == "ENCLOSURE":
            enclosure = {k: row.get(k) for k in ("id", "name", "width", "height", "depth", "ip_rating", "mounting_plate_width", "mounting_plate_height", "mounting_plate_offset_x", "mounting_plate_offset_y", "mounting_plate_offset_z", "max_thermal_dissipation", "zones")}
            enclosures.append(enclosure)
        else:
            components.append({k: row.get(k) for k in LEGACY_FIELDS if k in row and row.get(k) is not None})
    (out / "components.json").write_text(json.dumps(components, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "components_full.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    if enclosures:
        (out / "enclosures.json").write_text(json.dumps(enclosures, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"components": len(components), "enclosures": len(enclosures), "full": len(rows)}
