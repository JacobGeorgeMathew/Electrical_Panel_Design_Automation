from ..http_client import HttpClient

class CandidateSource:
    """Conservative connector. It only uses configured seed URLs until an audited discovery strategy is added."""
    def __init__(self, source_id, config):
        self.source_id, self.config = source_id, config
        self.http = HttpClient(source_id, config)

    def discover_product_urls(self):
        return []

    def fetch(self, url):
        return self.http.fetch(url)

    def parse(self, body, metadata):
        raise RuntimeError("Manufacturer scraping connectors are intentionally not implemented. Use import-file for files you obtain yourself.")
