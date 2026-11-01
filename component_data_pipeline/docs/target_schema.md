# Target component schema

This schema is based on `backend/app/data/components.json`, `enclosures.json`, `panel_hardware.json`, the JSON repositories, and `CatalogRepository`/the legacy import. It describes the input/export contract; it does not change the main project.

## Electrical and mechanical components

The legacy `components.json` row shape is a JSON object with these fields:

| Field | Type | Unit / allowed form | Presence and notes |
|---|---|---|---|
| `id` | string | stable catalog identifier | Required, unique. |
| `name` | string | — | Required display name. |
| `category` | string | `MCCB`, `MCB`, `SPD`, `BUSBAR`, `TERMINAL`, `NEUTRAL_BAR`, `EARTH_BAR`, `DIN_RAIL`; current data also includes supporting hardware categories | Required. Current JSON has no RCCB/RCBO entry; these can use new `RCCB` / `RCBO` categories after explicit downstream compatibility review. |
| `current_rating` | number | A | Required by existing candidate selection for protective/current-rated parts; absent or inapplicable for mechanical DIN rail. |
| `breaking_capacity` | number | kA | Used by existing candidate selection. It currently appears as `0` on non-protective hardware; use `null` for genuinely inapplicable values in the full schema and map to `0` only if the legacy consumer requires it. |
| `poles` | integer | count | Electrical pole count; absent/inapplicable for purely mechanical hardware. |
| `width` | number | mm | Product envelope width. Required by catalog geometry. |
| `height` | number | mm | Product envelope height. Required by catalog geometry. |
| `depth` | number | mm | Product envelope depth. Required by catalog geometry. |
| `mounting` | string | existing values include `PLATE`, `DIN_RAIL`; may be omitted on some mechanical fixture parts | Mounting interface. |
| `heat_loss` | number | W | Thermal dissipation; legacy importer defaults missing values to 0, but a real-data pipeline must preserve missing as null and flag it. |
| `cad_model` | string | URL/reference/identifier | Existing JSON uses local illustrative `.step` names and `parametric:` hints. A source URL belongs in `cad_url`; never imply a CAD file exists when it does not. |
| `clearance_top` | number | mm | Optional installation clearance. |
| `clearance_bottom` | number | mm | Optional installation clearance. |
| `clearance_sides` | number | mm | Optional installation clearance applied to both sides in the fixture. |
| `terminals` | array of objects | coordinates in mm | Optional in fixture, important for wiring/physical routing. |
| `terminals[].id` | string | — | Stable terminal identifier, required per terminal. |
| `terminals[].label` | string | — | Human-readable terminal label; optional in panel hardware. |
| `terminals[].type` | string | e.g. `POWER`, `NEUTRAL`, `PE` | Electrical role. |
| `terminals[].x`, `terminals[].y`, `terminals[].z` | number | mm, component-local coordinates | Required to place terminal accurately when coordinates are supplied. Fixture origin/face convention is not globally documented; preserve the source convention and source raw text. |
| `terminals[].connection_type` | string | e.g. screw/clamp, if sourced | Supported by the PostgreSQL `component_terminals` table, not by the legacy JSON contract. |
| `terminals[].conductor_min_mm2`, `terminals[].conductor_max_mm2` | number | mm² | Supported by PostgreSQL terminal catalog, not by the legacy JSON contract. |
| `material` | string | — | Optional extra used by `panel_hardware.json`; importer retains it in specification JSON. |
| `color` | string | color value | Optional fixture/rendering hint, not a manufacturer electrical property. |
| `parameters` | object | named values; units must be explicit in keys or documentation | Optional parametric geometry values used by hardware fixtures. |

### Categories and category-specific applicability

The schema is a common superset; fields that do not apply are null/absent in the full record and must not be fabricated.

| Category | Key properties expected when applicable |
|---|---|
| `MCCB` | `current_rating` (A), `poles`, `breaking_capacity` (kA), `voltage_rating` (V), envelope dimensions, `mounting`, `heat_loss` (W), terminal map, clearances. |
| `MCB` | Same core electrical/geometry fields as MCCB; trip curve and rated short-circuit capacities can be retained in `specification` until the legacy schema grows. |
| `SPD` | `poles`; discharge-current ratings and voltage protection level belong in `specification` unless/until a typed downstream field exists. Do not treat discharge-current rating as `current_rating`. |
| `BUSBAR` | `current_rating` (A), poles/conductor configuration, dimensions, mounting and terminals; breaking capacity only when manufacturer specifies a relevant short-circuit withstand value. |
| `TERMINAL` | `current_rating` (A), dimensions, mounting, connection type and conductor range where sourced; poles may represent number of isolated ways for existing fixtures. |
| `NEUTRAL_BAR` | Current rating (A), way count/poles if applicable, dimensions, mounting and terminals. |
| `EARTH_BAR` | Current/short-time withstand rating only when specified, way count if applicable, dimensions, mounting and terminals. |
| `DIN_RAIL` | Dimensions and mounting profile/material; electrical rating fields are inapplicable. Current `DIN_RAIL_35` uses `width=1000`, `height=35`, `depth=7.5` mm. |
| `ENCLOSURE` | Separate enclosure shape below. Existing repository stores enclosures in `enclosures.json`, not in `components.json`; the DB import represents them as `components` with category `ENCLOSURE`. |

## Enclosures (`enclosures.json`)

| Field | Type | Unit / allowed form | Presence and notes |
|---|---|---|---|
| `id` | string | stable catalog identifier | Required, unique. |
| `name` | string | — | Required. |
| `width`, `height`, `depth` | number | mm | Required outer dimensions. |
| `ip_rating` | string | e.g. `IP54`, `IP65` | Required for current enclosure selection; rating order is explicitly hard-coded only for IP31/IP42/IP54/IP65. |
| `mounting_plate_width`, `mounting_plate_height` | number | mm | Usable plate dimensions; used by enclosure fit. |
| `mounting_plate_offset_x`, `mounting_plate_offset_y`, `mounting_plate_offset_z` | number | mm | Plate offsets from enclosure coordinate origin. |
| `max_thermal_dissipation` | number | W | Used by enclosure selection; preserve null if the manufacturer does not state a value. |
| `zones` | array of objects | coordinates in mm | Fixture layout regions; real enclosure zones are project-derived unless the manufacturer provides them. |
| `zones[].name` | string | — | Layout zone name. |
| `zones[].x_min`, `x_max`, `y_min`, `y_max` | number | mm | Bounds in enclosure/layout coordinate frame. |
| `manufacturer`, `series`, `part_number`, `description`, `datasheet_url`, `product_url`, `cad_url`, `weight`, `price`, `standards`, `voltage_rating`, `source_id`, `scraped_at` | see shared real-data metadata below | — | Optional provenance/product data. `ip_rating` already exists as a legacy enclosure field. |

## Optional real-product metadata and provenance

These fields extend normalized records. They are optional and should also be included in the full JSONL export. Keep them out of the strict legacy JSON export unless the consuming loader has been confirmed to ignore unknown fields.

| Field | Type | Unit / format |
|---|---|---|
| `manufacturer` | string | Manufacturer's displayed name. |
| `series` | string | Manufacturer product family/series. |
| `part_number` | string | Manufacturer's order code / catalog number; preserve punctuation and leading zeros. |
| `description` | string | Concise sourced description. |
| `datasheet_url`, `product_url`, `cad_url` | string (URL) or null | Canonical source links. Store CAD URL only; downloading/rehosting requires a clear license. |
| `weight` | number or null | grams. |
| `price` | object or null | `{ "amount": number, "currency": "INR" }`; record market/date if available in provenance, because prices change. |
| `standards` | array of strings | e.g. `IEC 60947-2`; preserve exact standard identifiers. |
| `voltage_rating` | number or null | V. For ratings with distinct AC/DC or line/phase contexts, retain the exact raw text and structured detail in `specification`. |
| `ip_rating` | string or null | e.g. `IP20`; also a required legacy enclosure field. |
| `source_id` | string | Stable configured source identifier. |
| `scraped_at` | string (ISO 8601 with timezone) | Retrieval timestamp. |
| `data_quality` | object | Completeness/validation flags; missing `heat_loss` must be explicit. |
| `provenance` | object | Per-field raw text, source URL/document/page/table, extraction method, and estimated flag/method when applicable. Never merge estimates silently with sourced values. |

## PostgreSQL mapping observed

`CatalogRepository` emits a normalized component DTO with `id`, `code`, `catalog_id`, `component_version_id`, `version_no`, `name`, `category`, `kind`, `current_rating`, `rated_voltage_v`, `breaking_capacity`, `poles`, `width`, `height`, `depth`, `mounting`, `mounting_parameters`, `heat_loss`, `terminals`, `cad_model`, `specification`, `manufacturer`, `sku`, and `product_version_id`; detail calls add `cad_models`, `clearances`, and `documents`. The versioned SQL model separates terminal coordinates/connection data, mounting, clearances, and thermal specs into tables, while extra specifications/provenance are retained in JSONB. Products carry manufacturer and manufacturer SKU. This is richer than the legacy JSON shape and is the intended eventual import mapping.

The legacy importer derives component `code` from `id`, reads the `category`, electrical ratings and geometry directly, puts unrecognized component keys into `specification`, and inserts terminals, mounting, thermal loss and clearances separately. Enclosure selection additionally depends on plate dimensions, offsets, `max_thermal_dissipation`, and `ip_rating`.

## Scope caveats

- Current illustrative `components.json` contains 14 rows across MCCB, MCB, SPD, BUSBAR, TERMINAL, EARTH_BAR and NEUTRAL_BAR; it has no RCCB/RCBO or DIN_RAIL entries. `panel_hardware.json` adds DIN_RAIL and supporting mechanical components.
- Existing fixture values and terminal coordinates are explicitly illustrative/unverified. They are schema examples, not source data to carry into real catalog records.
- `current_rating`, `breaking_capacity`, zero defaults, and some terminal/clearance assumptions are consumer conventions, not universal meanings for every product category.
- The common export must maintain the existing `id` field for `ComponentRepository`; PostgreSQL uses that value as component code during the legacy import.
