# Manual curation guide: 30–50 distribution-board parts

The manual path works without manufacturer scraping. Use product datasheets and catalogs that you personally obtain from public product pages or through an authorized college/manufacturer account. Keep source files local in `data/manual/inbox/`; that folder is gitignored. Do not upload or commit third-party PDFs or CAD files.

## 1. Collect a small, balanced set

Aim for 30–50 distinct order codes, with roughly:

- 6–8 MCCBs up to 630 A, including common pole counts and breaking-capacity variants.
- 8–10 MCBs covering 6–63 A and 1P/2P/3P/4P configurations.
- 3–5 RCCB/RCBO devices, including residual-current type/sensitivity in `notes` or the source-specific `raw_text` until dedicated schema fields are added.
- 3–5 SPDs, keeping Uc, Up, In/Imax/Iimp distinct in notes/raw text rather than mapping them incorrectly to `current_rating`.
- 3–5 busbar or busbar-system parts; 2–3 neutral/earth bars; 3–5 terminal blocks; 1–2 DIN rails; and 3–5 enclosures with dimensions and IP rating.

Treat these as collection targets, not product data. Prefer one manufacturer datasheet per product family, then capture the exact order code and configuration for each row.

## 2. Record each product in the template

Copy `data/manual/component_template.csv` to a working copy. Keep the `template_family` rows as guidance; replace them with one row per actual order code and put the category in `category`. Do not fill values by inference from a family name or product photo.

For every row, record:

1. `manufacturer`, `series`, `part_number` and `name` exactly as printed.
2. `current_rating` in A, `breaking_capacity` in kA, `poles`, and `voltage_rating` in V when given.
3. Overall `width`, `height`, and `depth` in mm. Confirm the vendor's axis order from a dimension drawing. If the document only gives a combined dimension string, enter it in `dimensions` in a JSON/CSV working sheet or enter each confirmed axis separately in the template.
4. `heat_loss` in W only when the datasheet states it; otherwise leave blank.
5. `mounting`, terminal details, clearances, standards, weight, IP rating, and enclosure mounting-plate dimensions when stated.
6. Exact `source_url`, `document_name`, `page_number`, `retrieved_on` (YYYY-MM-DD), and a short `raw_text` excerpt such as the table row or dimension callout. Keep excerpts brief and factual.
7. `notes` for configuration caveats, axis order, or category-specific attributes not represented in the common fields. Do not silently substitute estimates.

Use one row for one order code/configuration. A family-level range such as “6–63 A” is not a specific part and should not be imported as if it were one. If a catalog has a range, select its individual rated variants and exact order codes.

## 3. Cite and retain provenance

For each sourced value, make the raw text traceable to its document and page. In CSV/XLSX/JSON, the importer records a per-field raw value plus input filename, source URL, row, and (if supplied) PDF page. In PDF imports, extraction preserves each table cell row and page. Recheck every parsed row against the original page; table extraction can shift columns or join line breaks.

Some BMEcat files use ETIM codes without human-readable category names; those rows will be rejected until you map the exact product category in your source sheet. The parser preserves raw feature names, values, and units in provenance.

Keep only the URL and extracted facts in the staging catalog. Do not redistribute source documents. If the right to retain or reuse extracted product data is unclear, ask the manufacturer or college before importing it into a distributable artifact.

## 4. Import and inspect

Place any PDF to import under `data/manual/inbox/`; the pipeline refuses PDF paths outside that directory. CSV, XLSX, JSON and manually downloaded ABB BMEcat XML can be imported from a path you specify.

```powershell
pipeline import-file --path component_data_pipeline/data/manual/my_parts.csv --source manual
pipeline import-file --path component_data_pipeline/data/manual/inbox/my_datasheet.pdf --source abb
pipeline import-file --path component_data_pipeline/data/manual/abb_bmecat.xml --source abb
pipeline report
```

`import-file` normalizes units, records missing-field flags, validates category-specific minimums, merges duplicate manufacturer/order-code records while retaining source observations, stores accepted and rejected rows in SQLite, and writes exports. Review the rejection reasons and `components_full.jsonl` before using the legacy JSON export. Missing values remain null in the full record and are not estimated.

The JSON export is intended to match the legacy component object shape, with null/inapplicable legacy properties omitted where the current repository expects missing keys. The full JSONL carries extra metadata and provenance. The pipeline does not import to PostgreSQL.
