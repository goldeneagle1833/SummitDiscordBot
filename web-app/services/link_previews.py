"""Link previews (like Discord embeds) for community website links.

Fetches each page once, reads its Open Graph / Twitter / standard meta tags,
and caches the result per worker so the Community page stays fast.
"""

import ipaddress
import logging
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger(__name__)

SUCCESS_TTL_SECONDS = 12 * 60 * 60
FAILURE_TTL_SECONDS = 60 * 60
REQUEST_TIMEOUT_SECONDS = 5
MAX_BYTES = 1024 * 1024
MAX_WORKERS = 6
MAX_DESCRIPTION = 300

_HEADERS = {
    # Present as a link-preview bot so sites serve their embed tags.
    "User-Agent": (
        "Mozilla/5.0 (compatible; SorcerersSummitBot/1.0; +https://sorcererssummit.com) "
        "Discordbot/2.0"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

# url -> (preview dict or None, expires_at)
_cache: dict[str, tuple[dict | None, float]] = {}
_lock = threading.Lock()


class _MetaParser(HTMLParser):
    """Collects <meta>, <title> and icon <link> tags from the page head."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self.icon = ""
        self._in_title = False
        self._done = False

    def handle_starttag(self, tag, attrs):
        if self._done:
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower().strip()
            content = a.get("content", "").strip()
            if key and content and key not in self.meta:
                self.meta[key] = content
        elif tag == "title":
            self._in_title = True
        elif tag == "link":
            rel = a.get("rel", "").lower()
            if "icon" in rel and a.get("href") and (not self.icon or "apple-touch" in rel):
                self.icon = a["href"]
        elif tag == "body":
            self._done = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "head":
            self._done = True

    def handle_data(self, data):
        if self._in_title and not self.title:
            self.title = data.strip()


def parse_preview(html: str, page_url: str) -> dict | None:
    """Turn a page's HTML into {title, description, image, site_name, icon}."""
    parser = _MetaParser()
    try:
        parser.feed(html)
    except Exception:
        pass
    m = parser.meta

    def first(*keys):
        for k in keys:
            if m.get(k):
                return m[k]
        return ""

    def absolute(u):
        if not u:
            return None
        full = urljoin(page_url, u)
        return full if urlparse(full).scheme in ("http", "https") else None

    title = first("og:title", "twitter:title") or parser.title
    description = first("og:description", "twitter:description", "description")
    if len(description) > MAX_DESCRIPTION:
        description = description[: MAX_DESCRIPTION - 1].rstrip() + "…"
    image = absolute(first("og:image:secure_url", "og:image", "og:image:url",
                           "twitter:image", "twitter:image:src"))
    icon = absolute(parser.icon or "/favicon.ico")
    site_name = first("og:site_name", "application-name")
    color = first("theme-color")

    if not (title or description or image):
        return None
    return {
        "title": title or None,
        "description": description or None,
        "image": image,
        "site_name": site_name or None,
        "icon": icon,
        "color": color or None,
    }


def _is_public_host(url: str) -> bool:
    """Only fetch http(s) URLs that resolve to public addresses."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            return False
    return True


def _fetch_preview(url: str) -> dict | None:
    try:
        current = url
        for _ in range(4):  # follow redirects ourselves so each hop is checked
            if not _is_public_host(current):
                return None
            resp = requests.get(current, headers=_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS,
                                stream=True, allow_redirects=False)
            if resp.is_redirect and resp.headers.get("Location"):
                current = urljoin(current, resp.headers["Location"])
                resp.close()
                continue
            break
        else:
            return None

        if resp.status_code != 200 or "html" not in resp.headers.get("Content-Type", "html"):
            resp.close()
            return None
        body = b""
        for chunk in resp.iter_content(16384):
            body += chunk
            if len(body) >= MAX_BYTES:
                break
        resp.close()
        html = body.decode(resp.encoding or "utf-8", errors="replace")
        return parse_preview(html, current)
    except Exception:
        logger.info("Link preview failed for %s", url, exc_info=True)
        return None


def get_previews(urls: list[str]) -> dict[str, dict | None]:
    """Map each URL to its preview (None when the page has nothing usable)."""
    now = time.time()
    urls = [u for u in urls if u]
    with _lock:
        missing = {u for u in urls if u not in _cache or _cache[u][1] <= now}

    if missing:
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(missing))) as pool:
            results = dict(zip(missing, pool.map(_fetch_preview, missing)))
        with _lock:
            for u, preview in results.items():
                ttl = SUCCESS_TTL_SECONDS if preview else FAILURE_TTL_SECONDS
                _cache[u] = (preview, now + ttl)

    with _lock:
        return {u: _cache.get(u, (None, 0))[0] for u in urls}


def add_previews(websites: list[dict]) -> list[dict]:
    """Attach a preview dict to each website entry."""
    previews = get_previews([w.get("url") or "" for w in websites])
    for w in websites:
        w["preview"] = previews.get(w.get("url") or "")
    return websites
