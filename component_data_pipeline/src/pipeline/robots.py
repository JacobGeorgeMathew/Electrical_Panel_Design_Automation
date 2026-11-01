from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
import httpx

def check_allowed(url, user_agent, timeout=20):
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    response = httpx.get(robots_url, timeout=timeout, follow_redirects=True, headers={"User-Agent": user_agent})
    if response.status_code in (401, 403):
        return False, f"robots.txt returned HTTP {response.status_code}"
    if response.status_code == 404:
        return True, "robots.txt returned 404 (no rules file found)"
    if response.status_code >= 400:
        return False, f"robots.txt could not be verified (HTTP {response.status_code})"
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(response.text.splitlines())
    return parser.can_fetch(user_agent, url), robots_url
