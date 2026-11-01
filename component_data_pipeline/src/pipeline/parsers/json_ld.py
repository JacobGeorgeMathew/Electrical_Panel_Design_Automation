import json
from bs4 import BeautifulSoup

def parse_product_page(body, url, source_id):
    soup = BeautifulSoup(body, "html.parser")
    records = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        values = payload if isinstance(payload, list) else payload.get("@graph", [payload]) if isinstance(payload, dict) else []
        for item in values:
            if isinstance(item, dict) and item.get("@type") == "Product":
                raw = {k: item.get(k) for k in ("name", "description", "sku", "mpn", "brand", "url", "image", "offers") if item.get(k) is not None}
                records.append({"source_id": source_id, "product_url": url, "raw_fields": raw, "raw_product": item})
    return records
