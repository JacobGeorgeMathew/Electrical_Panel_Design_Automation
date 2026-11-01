from hashlib import sha256
from pathlib import Path
import time
import httpx
from .config import DATA_ROOT, load_yaml
from .robots import check_allowed

class FetchError(RuntimeError):
    pass

class HttpClient:
    def __init__(self, source_id, source):
        defaults = load_yaml("sources.yaml")["defaults"]
        self.source_id, self.source = source_id, source
        self.agent = defaults["user_agent"]
        self.timeout = defaults["timeout_seconds"]
        self.retries = defaults["max_retries"]
        self.delay = 1 / max(0.1, float(source.get("requests_per_domain", defaults["requests_per_domain"])))
        self.cache = DATA_ROOT / "raw"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.last_host = {}
        self.denied = {}

    def fetch(self, url):
        permission = self.source.get("permission", "UNVERIFIED")
        if permission not in {"ALLOWED", "ALLOWED_WITH_LIMITS"}:
            raise FetchError(f"Source {self.source_id} permission={permission}: network fetch blocked. {self.source.get('access_note', '')}")
        allowed, detail = check_allowed(url, self.agent, self.timeout)
        if not allowed:
            raise FetchError(f"robots.txt disallows or cannot verify {url}: {detail}")
        key = sha256(url.encode()).hexdigest()
        body_path = self.cache / f"{key}.body"
        meta_path = self.cache / f"{key}.url"
        if body_path.exists() and meta_path.exists() and meta_path.read_text(encoding="utf-8") == url:
            return body_path.read_bytes(), {"url": url, "cache": True, "robots": detail}
        host = httpx.URL(url).host
        wait = self.delay - (time.monotonic() - self.last_host.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        for attempt in range(self.retries):
            try:
                response = httpx.get(url, timeout=self.timeout, follow_redirects=True, headers={"User-Agent": self.agent, "Accept": "text/html,application/json,application/pdf;q=0.8,*/*;q=0.5"})
                self.last_host[host] = time.monotonic()
                if response.status_code in (403, 429):
                    self.denied[host] = self.denied.get(host, 0) + 1
                    if self.denied[host] >= 2:
                        raise FetchError(f"Stopping for {host} after repeated HTTP {response.status_code}")
                    raise FetchError(f"HTTP {response.status_code} from {url}; retry disabled for access-control responses")
                response.raise_for_status()
                body_path.write_bytes(response.content)
                meta_path.write_text(url, encoding="utf-8")
                return response.content, {"url": url, "cache": False, "status": response.status_code, "content_type": response.headers.get("content-type"), "robots": detail}
            except FetchError:
                raise
            except httpx.HTTPError as exc:
                if attempt + 1 == self.retries:
                    raise FetchError(str(exc)) from exc
                time.sleep(min(2 ** attempt, 20))
