def dedupe_key(record):
    manufacturer = (record.get("manufacturer") or "").casefold().strip()
    part = (record.get("part_number") or record.get("id") or "").casefold().strip()
    return (manufacturer, part) if manufacturer and part else ("", "")
