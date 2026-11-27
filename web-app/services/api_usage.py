"""Usage log for Summit's open APIs (Staples, public match history, player search).

One row per (UTC day, endpoint, caller IP, outcome) with a call count, in
analytics.db, so each call is a single small UPSERT. Rows older than
RETENTION_DAYS are pruned (at most once an hour). Admins read it on the admin
page's "API Usage" section (GET /api/admin/api-usage). Logging never breaks a
call: any error here is swallowed.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

from urllib.parse import urlsplit

from flask import request

import webapp_config

logger = logging.getLogger(__name__)

RETENTION_DAYS = 90
_PRUNE_EVERY = 3600
_last_prune = 0.0
_prune_lock = threading.Lock()

# Flask endpoint -> label shown on the admin page
ENDPOINT_LABELS = {
    "api.public_matches.get_player_matches": "Match history",
    "api.public_matches.search_public_players": "Player search",
    "api.staples.get_staples": "Staples",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS api_usage_daily (
    day TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    client_ip TEXT NOT NULL,
    outcome TEXT NOT NULL,
    calls INTEGER NOT NULL DEFAULT 0,
    last_seen TEXT NOT NULL,
    user_agent TEXT,
    site TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (day, endpoint, client_ip, outcome, site)
)
"""


def _connect():
    conn = sqlite3.connect(str(webapp_config.ANALYTICS_DB_PATH), timeout=2)
    conn.execute(_SCHEMA)
    return conn


def client_ip() -> str:
    forwarded = request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For", "")
    return (forwarded.split(",")[0].strip() or request.remote_addr or "unknown")[:64]


SITE_PARAM = "site"
SITE_HEADER = "X-Summit-Site"
CONTACT_PARAM = "contact"
CONTACT_HEADER = "X-Summit-Contact"
CONTACT_PREFIX = "contact:"


def parse_site(value) -> str | None:
    """The caller's site as ``https://host/path`` (lower-case host, no query), or None if it isn't a web address."""
    raw = (value or "").strip()
    if not raw or len(raw) > 200 or any(ch.isspace() for ch in raw):
        return None
    if "://" not in raw:
        raw = f"https://{raw}"
    try:
        parts = urlsplit(raw)
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or parts.username or parts.password:
        return None
    labels = host.split(".")
    if len(labels) < 2 or not all(labels) or not all(c.isalnum() or c in "-." for c in host):
        return None
    netloc = f"{host}:{port}" if port else host
    path = parts.path.rstrip("/")
    return f"{parts.scheme}://{netloc}{path}"


def request_site() -> str | None:
    """The site the caller named (``?site=`` or the X-Summit-Site header), cleaned up."""
    return parse_site(request.args.get(SITE_PARAM) or request.headers.get(SITE_HEADER))


def parse_contact(value) -> str | None:
    """A personal project's contact (Discord name or ID, or similar): 2-64 printable characters."""
    text = " ".join((value or "").split())
    if not 2 <= len(text) <= 64 or not all(ch.isprintable() for ch in text):
        return None
    return text


def request_caller() -> str | None:
    """Who is calling: their site (``https://...``) or, for a personal project, ``contact:<name>``.

    A site wins when both are given.
    """
    site = request_site()
    if site:
        return site
    contact = parse_contact(request.args.get(CONTACT_PARAM) or request.headers.get(CONTACT_HEADER))
    return f"{CONTACT_PREFIX}{contact}" if contact else None


def outcome_for(status: int) -> str:
    if status == 429:
        return "limited"
    if status >= 500:
        return "error"
    if status >= 400:
        return "bad_request"
    return "ok"


def record(endpoint: str, status: int, ip: str, user_agent: str | None, now: datetime | None = None,
           site: str | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    try:
        conn = _connect()
        try:
            conn.execute(
                """INSERT INTO api_usage_daily (day, endpoint, client_ip, outcome, calls, last_seen, user_agent, site)
                   VALUES (?, ?, ?, ?, 1, ?, ?, ?)
                   ON CONFLICT (day, endpoint, client_ip, outcome, site) DO UPDATE SET
                       calls = calls + 1, last_seen = excluded.last_seen,
                       user_agent = COALESCE(excluded.user_agent, user_agent)""",
                (now.date().isoformat(), endpoint, ip, outcome_for(status),
                 now.isoformat(timespec="seconds"), (user_agent or "")[:200] or None, site or ""),
            )
            _maybe_prune(conn, now)
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.debug("Could not log API usage", exc_info=True)


def _maybe_prune(conn, now: datetime) -> None:
    global _last_prune
    with _prune_lock:
        if time.monotonic() - _last_prune < _PRUNE_EVERY and _last_prune:
            return
        _last_prune = time.monotonic()
    cutoff = (now.date() - timedelta(days=RETENTION_DAYS)).isoformat()
    conn.execute("DELETE FROM api_usage_daily WHERE day < ?", (cutoff,))


def log_response(response):
    """after_request hook for the open API blueprints."""
    endpoint = request.endpoint or ""
    if endpoint in ENDPOINT_LABELS and request.method == "GET":
        record(endpoint, response.status_code, client_ip(), request.headers.get("User-Agent"),
               site=request_caller())
    return response


def summary(days: int = 7, now: datetime | None = None, top: int = 25) -> dict:
    """Totals, calls per day, per endpoint and the top callers over the last ``days`` UTC days."""
    now = now or datetime.now(timezone.utc)
    start = (now.date() - timedelta(days=days - 1)).isoformat()
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT day, endpoint, client_ip, outcome, calls, last_seen, user_agent, site "
            "FROM api_usage_daily WHERE day >= ?",
            (start,),
        ).fetchall()
    finally:
        conn.close()

    def blank():
        return {"calls": 0, "ok": 0, "limited": 0, "bad_request": 0, "error": 0}

    totals = blank()
    by_day = {(now.date() - timedelta(days=i)).isoformat(): blank() for i in range(days)}
    by_endpoint = {label: blank() for label in ENDPOINT_LABELS.values()}
    callers = {}
    sites = {}
    for day, endpoint, ip, outcome, calls, last_seen, agent, site in rows:
        label = ENDPOINT_LABELS.get(endpoint, endpoint)
        for bucket in (totals, by_day.setdefault(day, blank()), by_endpoint.setdefault(label, blank())):
            bucket["calls"] += calls
            bucket[outcome] = bucket.get(outcome, 0) + calls
        site = site or None
        st = sites.setdefault(site, {"site": site, **blank(), "endpoints": {}, "ips": set(), "last_seen": ""})
        st["calls"] += calls
        st[outcome] = st.get(outcome, 0) + calls
        st["endpoints"][label] = st["endpoints"].get(label, 0) + calls
        st["ips"].add(ip)
        st["last_seen"] = max(st["last_seen"], last_seen)
        c = callers.setdefault(ip, {"ip": ip, **blank(), "endpoints": {}, "sites": set(), "last_seen": "",
                                    "user_agent": None})
        if site:
            c["sites"].add(site)
        c["calls"] += calls
        c[outcome] = c.get(outcome, 0) + calls
        c["endpoints"][label] = c["endpoints"].get(label, 0) + calls
        if last_seen >= c["last_seen"]:
            c["last_seen"] = last_seen
            c["user_agent"] = agent or c["user_agent"]

    top_callers = sorted(callers.values(), key=lambda c: c["calls"], reverse=True)[:top]
    for c in top_callers:
        c["sites"] = sorted(c["sites"])
    by_site = sorted(sites.values(), key=lambda x: x["calls"], reverse=True)[:top]
    for st in by_site:
        st["callers"] = len(st.pop("ips"))
    return {
        "days": days,
        "totals": {**totals, "callers": len(callers), "sites": len([k for k in sites if k])},
        "by_site": by_site,
        "by_day": [{"day": d, **v} for d, v in sorted(by_day.items())],
        "by_endpoint": [{"endpoint": k, **v} for k, v in by_endpoint.items()],
        "top_callers": top_callers,
        "retention_days": RETENTION_DAYS,
    }
