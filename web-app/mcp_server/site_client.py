"""Reads Summit data from the site's own API, as a logged-out visitor would.

The MCP server never opens the databases and never talks to Play Sorcery
Online. Every answer comes from the Flask API that already powers the
public pages, so privacy settings, provisional ratings and hidden sections
behave exactly as they do on the site.

Why a site token and not an API key: in the Flask app a valid API key counts
as an admin (utils/auth.is_admin), which would unlock admin-only fields. A
site token is what an anonymous browser gets, so the MCP server sees exactly
what a logged-out visitor sees.

Load protection for the site (it runs only two main web workers):
  - every answer is cached in memory (CACHE_TTL_SECONDS, longer for slow pages)
  - at most UPSTREAM_CONCURRENCY requests go to the site at once (default 1),
    so the MCP server can never tie up more than one web worker
  - short timeouts, and a failure is cached briefly so retries don't pile up
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any
from urllib.parse import quote, urlencode

import httpx

logger = logging.getLogger(__name__)

SITE_HOST = os.environ.get("SUMMIT_MCP_SITE_HOST", "sorcererssummit.com")
# Production talks to gunicorn over its unix socket; local dev can point at
# the Flask dev server instead with SUMMIT_MCP_SITE_URL=http://localhost:5000
SITE_SOCKET = os.environ.get("SUMMIT_MCP_SITE_SOCKET", "/tmp/summit-web.sock")
SITE_URL = os.environ.get("SUMMIT_MCP_SITE_URL", "").rstrip("/")
PUBLIC_URL = os.environ.get("SUMMIT_MCP_PUBLIC_URL", "https://sorcererssummit.com").rstrip("/")

CACHE_TTL_SECONDS = int(os.environ.get("SUMMIT_MCP_CACHE_TTL", "600"))
ERROR_TTL_SECONDS = 30
UPSTREAM_CONCURRENCY = max(1, int(os.environ.get("SUMMIT_MCP_UPSTREAM_CONCURRENCY", "1")))
UPSTREAM_TIMEOUT = float(os.environ.get("SUMMIT_MCP_UPSTREAM_TIMEOUT", "25"))
TOKEN_REFRESH_SECONDS = 3 * 60 * 60  # site tokens last 12 h; refresh well before
MAX_CACHE_ENTRIES = 500
USER_AGENT = "SummitMCP/1.0 (+https://sorcererssummit.com)"


class SiteError(Exception):
    """The site could not answer; the message is safe to show to a player."""


class SiteClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        if transport is None and not SITE_URL:
            transport = httpx.AsyncHTTPTransport(uds=SITE_SOCKET)
        self._base = SITE_URL or f"http://{SITE_HOST}"
        self._client = httpx.AsyncClient(
            base_url=self._base,
            transport=transport,
            timeout=httpx.Timeout(UPSTREAM_TIMEOUT, connect=5.0),
            headers={
                "Host": SITE_HOST if not SITE_URL else httpx.URL(SITE_URL).netloc.decode(),
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "X-Forwarded-Proto": "https",
            },
        )
        self._semaphore = asyncio.Semaphore(UPSTREAM_CONCURRENCY)
        self._cache: dict[str, tuple[float, int, Any]] = {}
        self._inflight: dict[str, asyncio.Future] = {}
        self._token: str | None = None
        self._token_at = 0.0
        self._token_lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Site token
    # ------------------------------------------------------------------

    async def _site_token(self, force: bool = False) -> str:
        async with self._token_lock:
            fresh = self._token and time.monotonic() - self._token_at < TOKEN_REFRESH_SECONDS
            if fresh and not force:
                return self._token  # type: ignore[return-value]
            response = await self._client.get(
                "/api/site-token",
                headers={"Sec-Fetch-Site": "same-origin", "Origin": PUBLIC_URL},
            )
            token = response.cookies.get("summit_site")
            if not token:
                # The cookie is marked Secure in production; read the header directly
                for header in response.headers.get_list("set-cookie"):
                    name, _, rest = header.partition("=")
                    if name.strip() == "summit_site":
                        token = rest.split(";", 1)[0].strip()
            if response.status_code != 200 or not token:
                raise SiteError("Summit data is unavailable right now. Please try again in a minute.")
            self._token, self._token_at = token, time.monotonic()
            return token

    # ------------------------------------------------------------------
    # Requests
    # ------------------------------------------------------------------

    @staticmethod
    def path(*parts: str, **params: Any) -> str:
        """Build an /api path with every part URL-escaped (card and event names have spaces)."""
        url = "/api/" + "/".join(quote(str(p), safe="") for p in parts)
        clean = {k: v for k, v in params.items() if v not in (None, "")}
        return f"{url}?{urlencode(clean)}" if clean else url

    async def get(self, path: str, *, ttl: int | None = None, allow_404: bool = False) -> Any:
        return await self._cached("GET", path, None, ttl, allow_404)

    async def post(self, path: str, body: dict, *, ttl: int | None = None) -> Any:
        return await self._cached("POST", path, body, ttl, False)

    async def _cached(self, method: str, path: str, body: dict | None, ttl: int | None, allow_404: bool) -> Any:
        key = method + " " + path + (" " + json.dumps(body, sort_keys=True) if body is not None else "")
        now = time.monotonic()
        hit = self._cache.get(key)
        if hit and hit[0] > now:
            return self._unwrap(hit[1], hit[2], allow_404)

        # Identical requests that arrive together share one upstream call
        pending = self._inflight.get(key)
        if pending is not None:
            status, data = await asyncio.shield(pending)
            return self._unwrap(status, data, allow_404)

        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        try:
            status, data = await self._fetch(method, path, body)
            good = (status < 400 and status != 202) or status == 404
            lifetime = (ttl or CACHE_TTL_SECONDS) if good else ERROR_TTL_SECONDS
            if len(self._cache) >= MAX_CACHE_ENTRIES:
                self._evict(now)
            self._cache[key] = (time.monotonic() + lifetime, status, data)
            future.set_result((status, data))
        except BaseException as exc:
            future.set_exception(exc)
            # Nobody else may be awaiting; mark the exception as retrieved
            future.exception()
            raise
        finally:
            self._inflight.pop(key, None)
        return self._unwrap(status, data, allow_404)

    def _evict(self, now: float) -> None:
        for k in [k for k, v in self._cache.items() if v[0] <= now]:
            del self._cache[k]
        while len(self._cache) >= MAX_CACHE_ENTRIES:
            self._cache.pop(next(iter(self._cache)))

    @staticmethod
    def _unwrap(status: int, data: Any, allow_404: bool) -> Any:
        if status == 404 and allow_404:
            return None
        if status == 202:
            raise SiteError("That page is still being prepared on the site. Try again in a minute.")
        if status >= 400:
            message = data.get("error") if isinstance(data, dict) else None
            if status == 404:
                raise SiteError(message or "Not found.")
            if status in (400, 503) and message:
                raise SiteError(message)
            raise SiteError("Summit data is unavailable right now. Please try again in a minute.")
        return data

    async def _fetch(self, method: str, path: str, body: dict | None) -> tuple[int, Any]:
        async with self._semaphore:
            for attempt in (1, 2):
                token = await self._site_token(force=attempt == 2)
                headers = {"X-Site-Token": token, "Sec-Fetch-Site": "same-origin"}
                try:
                    if method == "POST":
                        response = await self._client.post(path, json=body, headers=headers)
                    else:
                        response = await self._client.get(path, headers=headers)
                except httpx.HTTPError as exc:
                    logger.warning("Site request failed: %s %s (%r)", method, path, exc)
                    raise SiteError("Summit data is unavailable right now. Please try again in a minute.")
                if response.status_code == 401 and attempt == 1:
                    continue  # token expired or rotated: get a new one once
                try:
                    data = response.json()
                except ValueError:
                    data = None
                return response.status_code, data
        return 401, None  # pragma: no cover
