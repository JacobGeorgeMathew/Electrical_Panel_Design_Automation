import sys
from pathlib import Path
import pytest

SRC=Path(__file__).resolve().parents[1]/"src"
sys.path.insert(0,str(SRC))

from pipeline.config import load_yaml
from pipeline.http_client import HttpClient, FetchError
from pipeline.official_connectors import SchneiderProductCatalogApi

def test_blocked_sources_never_reach_robots_or_page_request(monkeypatch):
    config=load_yaml("sources.yaml")["sources"]
    expected={"schneider_india":"PERMISSION_REQUIRED","abb":"PERMISSION_REQUIRED","havells_india":"UNVERIFIED","lt_india":"UNVERIFIED","siemens":"FORBIDDEN"}
    assert {k:v["permission"] for k,v in config.items()} == expected
    def should_not_check_robots(*args,**kwargs):
        pytest.fail("blocked source tried to check robots or fetch a page")
    monkeypatch.setattr("pipeline.http_client.check_allowed",should_not_check_robots)
    for sid in expected:
        client=HttpClient(sid,config[sid])
        with pytest.raises(FetchError,match="network fetch blocked"):
            client.fetch("https://example.invalid/product")

def test_allowed_status_still_blocks_disallowed_robots_path(monkeypatch):
    def disallowed(*args,**kwargs): return False,"synthetic robots rule: Disallow: /private/"
    monkeypatch.setattr("pipeline.http_client.check_allowed",disallowed)
    client=HttpClient("synthetic",{"permission":"ALLOWED"})
    with pytest.raises(FetchError,match="robots.txt disallows"):
        client.fetch("https://example.invalid/private/item")

def test_schneider_api_placeholder_is_disabled_without_network():
    connector=SchneiderProductCatalogApi()
    assert connector.enabled is False
    with pytest.raises(RuntimeError,match="disabled"):
        connector.import_products()
