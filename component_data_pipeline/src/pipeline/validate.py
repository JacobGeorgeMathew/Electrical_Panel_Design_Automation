def validate_record(record):
    reasons = []
    if not record.get("id"):
        reasons.append("missing part number/id")
    if not record.get("name"):
        reasons.append("missing name")
    if record.get("category") not in {"MCCB", "MCB", "RCCB", "RCBO", "SPD", "BUSBAR", "TERMINAL", "NEUTRAL_BAR", "EARTH_BAR", "DIN_RAIL", "ENCLOSURE"}:
        reasons.append("missing or unsupported category")
    category = record.get("category")
    required = {"id", "name", "category", "width", "height", "depth"}
    if category in {"MCCB", "MCB", "RCBO"}:
        required |= {"current_rating", "breaking_capacity", "poles"}
    elif category == "RCCB":
        required |= {"current_rating", "poles"}
    elif category in {"BUSBAR", "TERMINAL", "NEUTRAL_BAR", "EARTH_BAR"}:
        required |= {"current_rating"}
    elif category == "SPD":
        required |= {"poles"}
    elif category == "ENCLOSURE":
        required |= {"ip_rating", "mounting_plate_width", "mounting_plate_height", "max_thermal_dissipation"}
    for field in sorted(required):
        if record.get(field) is None:
            reasons.append(f"missing required field: {field}")
    current = record.get("current_rating")
    if category == "MCB" and current is not None and not 6 <= current <= 63:
        reasons.append("MCB current_rating outside project target 6-63 A range")
    if category == "MCCB" and current is not None and not 16 <= current <= 630:
        reasons.append("MCCB current_rating outside project target 16-630 A range")
    if category in {"MCCB", "MCB", "RCCB", "RCBO", "SPD"} and record.get("poles") is not None and record["poles"] not in (1, 2, 3, 4):
        reasons.append("poles must be 1, 2, 3, or 4 for this category")
    for field in ("width", "height", "depth"):
        value = record.get(field)
        if value is not None and value <= 0:
            reasons.append(f"{field} must be positive")
    if record.get("current_rating") is not None and record["current_rating"] < 0:
        reasons.append("current_rating must not be negative")
    if record.get("breaking_capacity") is not None and record["breaking_capacity"] < 0:
        reasons.append("breaking_capacity must not be negative")
    for field in ("current_rating", "poles", "width", "height", "depth"):
        if record.get(field) is None:
            record.setdefault("data_quality", {}).setdefault("missing_fields", []).append(field)
    return reasons
