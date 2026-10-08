"""API access gate: every ``/api/*`` request must carry an API key or a site token.

The goal is that nobody outside this project can pull data from the API
without a key, while the React site keeps working for anonymous visitors.

Two ways through the gate:

1. **API key** — ``X-API-Key`` (or ``Authorization: Bearer``) matching one of
   ``VALID_API_KEYS`` or ``DRAFT_SORCERY_API_KEY``.  Server-to-server callers
   (the Discord bot, Play Sorcery Online, partners) use this.

2. **Site token** — a signed, time-limited token the server hands out *only*
   to same-site browser requests via ``GET /api/site-token``.  It is stored in
   an ``HttpOnly``/``SameSite=Strict`` cookie, so:

   - the SPA's own ``fetch``/``sendBeacon`` calls carry it automatically,
   - other websites cannot make a visitor's browser send it (SameSite),
   - JavaScript on the page never sees it (HttpOnly).

   The token endpoint checks ``Sec-Fetch-Site``/``Origin``/``Referer`` against
   the configured site hosts before issuing one.  A cookie that is past half
   its lifetime is quietly re-issued on the response, so an open tab never
   expires while in use.

Honest limitation: browser-origin checks are a strong barrier for *browsers*
(other sites, CSRF) and stop casual ``curl``/script scraping, but a determined
client can still forge the same headers.  Real server-to-server trust must
always come from an API key.

Exempt endpoints (``EXEMPT_ENDPOINTS``) are the few that must be reachable with
neither: the token endpoint itself, the Stripe webhook (verified by signature)
and the uptime health check.
"""

from __future__ import annotations

import hmac
import logging
import time
from urllib.parse import urlsplit

from flask import Flask, Response, g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

import webapp_config

logger = logging.getLogger(__name__)

COOKIE_NAME = "summit_site"
HEADER_NAME = "X-Site-Token"
GATED_PREFIX = "/api/"

# Endpoints reachable with neither an API key nor a site token.
EXEMPT_ENDPOINTS = frozenset(
    {
        "api.site_token",  # issues the site token (same-site checked inside)
        "api.store.stripe_webhook",  # Stripe signs every webhook payload
        "api.monitoring.health",  # uptime monitors; pass/fail only, no data
    }
)

_DEV_HOSTS = frozenset({"localhost", "127.0.0.1"})


# ---------------------------------------------------------------------------
# API key check
# ---------------------------------------------------------------------------


def _extract_api_key() -> str | None:
    provided = request.headers.get("X-API-Key") or request.headers.get("Authorization")
    if provided and provided.startswith("Bearer "):
        provided = provided[7:]
    return provided or None


def _accepted_api_keys() -> list[str]:
    keys = list(webapp_config.VALID_API_KEYS)
    draft = (webapp_config.DRAFT_SORCERY_API_KEY or "").strip()
    if draft:
        keys.append(draft)
    return [k for k in keys if k]


def has_valid_api_key() -> bool:
    provided = _extract_api_key()
    if not provided:
        return False
    return any(hmac.compare_digest(provided, key) for key in _accepted_api_keys())


# ---------------------------------------------------------------------------
# Site token
# ---------------------------------------------------------------------------


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(webapp_config.SECRET_KEY, salt="summit-site-token")


def issue_site_token() -> str:
    return _serializer().dumps({"v": 1})


def _token_age(token: str | None) -> float | None:
    """Return the token's age in seconds, or None if missing/invalid/expired."""
    if not token:
        return None
    try:
        _, timestamp = _serializer().loads(
            token, max_age=webapp_config.SITE_TOKEN_MAX_AGE, return_timestamp=True
        )
    except (SignatureExpired, BadSignature):
        return None
    return max(0.0, time.time() - timestamp.timestamp())


def _presented_site_token() -> str | None:
    return request.headers.get(HEADER_NAME) or request.cookies.get(COOKIE_NAME)


# ---------------------------------------------------------------------------
# Same-site detection (used when *issuing* a token)
# ---------------------------------------------------------------------------


def _site_hosts() -> set[str]:
    hosts = set(webapp_config.SITE_HOSTS)
    # The host this request arrived on is always ours (nginx sets
    # X-Forwarded-Host; Flask's request.host honours it when trusted).
    forwarded = request.headers.get("X-Forwarded-Host", "")
    for candidate in (forwarded, request.host):
        candidate = candidate.split(",")[0].strip().lower()
        if candidate:
            hosts.add(candidate)
    if not webapp_config.IS_PRODUCTION:
        hosts |= _DEV_HOSTS
    return hosts


def _host_of(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return urlsplit(url).hostname
    except ValueError:
        return None


def _hostname_allowed(hostname: str | None, hosts: set[str]) -> bool:
    if not hostname:
        return False
    hostname = hostname.lower()
    return any(hostname == h.split(":")[0] for h in hosts)


def is_same_site_browser_request() -> bool:
    """Best-effort check that the request comes from a page on our own site."""
    fetch_site = request.headers.get("Sec-Fetch-Site", "").lower()
    if fetch_site in ("same-origin", "same-site"):
        return True
    if fetch_site in ("cross-site", "none"):
        return False
    # Older browsers: fall back to Origin / Referer.
    hosts = _site_hosts()
    origin_host = _host_of(request.headers.get("Origin"))
    if origin_host:
        return _hostname_allowed(origin_host, hosts)
    return _hostname_allowed(_host_of(request.headers.get("Referer")), hosts)


# ---------------------------------------------------------------------------
# Flask wiring
# ---------------------------------------------------------------------------


def _set_cookie(response: Response, token: str) -> Response:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=webapp_config.SITE_TOKEN_MAX_AGE,
        secure=request.is_secure or webapp_config.IS_PRODUCTION,
        httponly=True,
        samesite="Strict",
        path="/api/",
    )
    return response


def _reject(message: str, code: str):
    logger.warning("API gate rejected %s %s from %s (%s)", request.method, request.path, request.remote_addr, code)
    response = jsonify({"error": message, "code": code})
    response.status_code = 401
    response.headers["WWW-Authenticate"] = 'ApiKey realm="summit"'
    return response


def site_token_view():
    """``GET /api/site-token``: hand a site token to our own front end.

    Registered on the API blueprint in ``routes/api/__init__.py``.  Refuses
    callers that do not look like a page on our site.
    """
    if not is_same_site_browser_request():
        return _reject("Site token is only issued to the Summit website", "not_same_site")
    token = issue_site_token()
    response = jsonify({"ok": True, "expires_in": webapp_config.SITE_TOKEN_MAX_AGE})
    response.headers["Cache-Control"] = "no-store"
    return _set_cookie(response, token)


def init_site_gate(app: Flask) -> None:
    """Install the gate on ``app``.  Controlled by ``app.config["SITE_GATE_ENABLED"]``."""
    app.config.setdefault("SITE_GATE_ENABLED", webapp_config.SITE_GATE_ENABLED)

    @app.before_request
    def _gate():
        if not app.config.get("SITE_GATE_ENABLED"):
            return None
        if request.method == "OPTIONS" or not request.path.startswith(GATED_PREFIX):
            return None
        if request.endpoint in EXEMPT_ENDPOINTS:
            return None

        if has_valid_api_key():
            g.api_gate = "api_key"
            return None

        age = _token_age(_presented_site_token())
        if age is not None:
            g.api_gate = "site_token"
            if age > webapp_config.SITE_TOKEN_MAX_AGE / 2:
                g.api_gate_refresh = True
            return None

        if _extract_api_key():
            return _reject("Invalid API key", "invalid_api_key")
        return _reject(
            "An API key is required. Pass it in the X-API-Key header.",
            "api_key_required",
        )

    @app.after_request
    def _refresh_token(response: Response):
        if getattr(g, "api_gate_refresh", False):
            _set_cookie(response, issue_site_token())
        return response
