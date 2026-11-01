def parse_pdf_tables(path):
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("Install the optional PDF extra: pip install -e '.[pdf]'") from exc
    tables = []
    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables() or []:
                tables.append({"page": page_number, "rows": table})
    return tables
