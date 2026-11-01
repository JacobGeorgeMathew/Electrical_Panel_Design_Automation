# Electrical Component Data Pipeline

This sub-project imports product data supplied by you, preserves field-level provenance, validates it, and exports the main project's JSON catalog shape. It does not modify the main application's backend or frontend.

## Permission status

No manufacturer scraper is implemented. The five manufacturer sources remain blocked in `config/sources.yaml`: Schneider and ABB are `PERMISSION_REQUIRED`; Havells and L&T are `UNVERIFIED`; Siemens website extraction is `FORBIDDEN`. The HTTP client refuses all these statuses before robots checks or page requests. The previous robots.txt DNS failures remain unverified. `pipeline permissions` displays the local status without making a network request.

## Setup

From the repository root in PowerShell:

```powershell
py -3 -m venv component_data_pipeline/.venv
component_data_pipeline/.venv/Scripts/python -m pip install -e component_data_pipeline
```

## Manual import

Fill a copy of `component_data_pipeline/data/manual/component_template.csv`, or import an XLSX/JSON file. For PDF files, first place your own downloaded copy under `component_data_pipeline/data/manual/inbox/`; PDFs outside that directory are refused. The importer also supports manually downloaded ABB BMEcat XML.

```powershell
pipeline permissions
pipeline import-file --path component_data_pipeline/data/manual/my_parts.csv --source manual
pipeline import-file --path component_data_pipeline/data/manual/my_parts.xlsx --source abb
pipeline import-file --path component_data_pipeline/data/manual/my_parts.json --source manual
pipeline import-file --path component_data_pipeline/data/manual/inbox/vendor_datasheet.pdf --source abb
pipeline import-file --path component_data_pipeline/data/manual/abb_products.xml --source abb
pipeline report
```

`--source` is a provenance label you choose, such as `manual`, `abb`, or `schneider_india`; using a label does not access that source. CSV template rows are blank family prompts and are skipped until product fields are entered. Import displays normalized accepted rows and rejected rows with reasons, then updates `data/exports/components.json` and `components_full.jsonl`. Enclosure rows are written to `enclosures.json` when present.

Each value retains its raw text plus source file, URL, row, and PDF page where available. Missing values remain null in the full export and are listed in `data_quality`. Duplicate manufacturer/part-number records merge while retaining source observations. Validate and review both accepted and rejected output before use.

## Official channels

- **Schneider Product Catalog API:** a disabled placeholder is provided. It requires written permission/API onboarding and credentials. The placeholder makes no network request.

  ```powershell
  pipeline import-schneider-api
  ```

  It currently exits with a clear disabled message. Do not enable it until you supply written permission, applicable API terms, credentials, and a robots review for the API host.
- **ABB BMEcat/Excel:** use the offline import command above (`.xml` for BMEcat or `.xlsx` for Excel). The importer reads only the local file you provide; it does not download catalogs.
- **EPLAN:** no automatic connector is provided. Ask your college about account/license access and the terms for exporting product data.

## Tests and local proof

```powershell
py -3 -m pytest component_data_pipeline/tests -q
```

The tests use synthetic-only fixtures under `tests/fixtures/`; these are not product data. To keep a manual proof run separate from the normal staging DB, set `COMPONENT_PIPELINE_DATA_DIR` to a scratch folder before running `pipeline import-file`.

## Reports and exports

```powershell
pipeline export
pipeline report
```

- `data/staging.sqlite` stores normalized records and rejected rows.
- `data/exports/components.json` is the legacy component JSON format.
- `data/exports/components_full.jsonl` includes metadata and provenance.
- `data/exports/enclosures.json` is generated when enclosure records exist.
- `docs/data_quality_report.md` summarizes current completeness and gaps.

No PostgreSQL import is run by this project. `scripts/import_to_main_catalog.py` only prints handoff instructions.

## Curation and source setup

See [manual_curation_guide.md](docs/manual_curation_guide.md), [source_permissions.md](docs/source_permissions.md), and [target_schema.md](docs/target_schema.md). Keep the downloaded vendor files local in the gitignored inbox. Do not commit or redistribute third-party PDFs or CAD assets. Recheck terms and robots.txt before any future authorized online connection; never bypass logins, paywalls, CAPTCHAs, or anti-bot controls.
