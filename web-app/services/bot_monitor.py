"""Bot and scraper monitoring for the admin Bot Traffic page.

Traffic comes from ``client_traffic`` in the monitoring DB: hourly counts per
(User-Agent, IP), written by ``utils.monitoring``.  Blocks live in
``blocked_clients`` in the same DB; the API gate (``utils.site_gate``) asks
:func:`match_block` on every ``/api`` request and refuses matches with a 403
unless they carry a valid API key.

A block is either an ``agent`` rule (case-insensitive substring of the
User-Agent) or an ``ip`` rule (exact address).
"""

from __future__ import annotations

import re
import sqlite3
import threading
import time

import webapp_config
from utils.monitoring import CLIENT_BUCKET_S, connect, init_db

KINDS = ("agent", "ip")

# Blocks added by code rather than from the admin page.  Seeded once; removing
# one from the page sticks (the row is kept with active = 0).
SEEDED_BLOCKS = [
    ("agent", "sorceryrec",
     "SorceryRec competitive archive: copied every Top 8 event and ~2,000 deck recs nightly (Nov 2026)"),
]

# Agent rules that match any of these ordinary browsers are refused.
COMMON_BROWSERS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36 Edg/157.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:160.0) Gecko/20100101 Firefox/160.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:159.0) Gecko/20100101 Firefox/159.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36 OPR/139.0.0.0",
)
MIN_AGENT_PATTERN = 4

# A client that pulls this many data requests in one hour is not a person.
SUSPECT_DATA_PER_HOUR = 300
SUSPECT_DATA_TOTAL = 200

# Known crawlers, by family.  Checked in order; first match wins.
_FAMILIES = [
    ("search", re.compile(r"googlebot|google-inspectiontool|adsbot-google|bingbot|applebot|duckduckbot|"
                          r"baiduspider|yandexbot|googlebot-image|storebot-google", re.I)),
    ("ai", re.compile(r"gptbot|oai-searchbot|chatgpt-user|claudebot|claude-searchbot|perplexitybot|"
                      r"meta-externalagent|bytespider|amazonbot|ccbot|exasearchbot|reflectionbot|youbot|"
                      r"elevenlabscrawler|cohere|diffbot|petalbot", re.I)),
    ("seo", re.compile(r"ahrefsbot|semrushbot|mj12bot|dotbot|serpstatbot|dataforseobot|blexbot", re.I)),
    ("preview", re.compile(r"discordbot|facebookexternalhit|twitterbot|slackbot|telegrambot|whatsapp|"
                           r"linkedinbot|skypeuripreview|embedly|googlemessages", re.I)),
    ("bot", re.compile(r"bot\b|bot/|crawl|spider|slurp|scrap|archive", re.I)),
    ("script", re.compile(r"headlesschrome|lightpanda|phantomjs|puppeteer|playwright|^curl/|^wget/|"
                          r"python|aiohttp|^node|axios|go-http|okhttp|java/|libwww|httpclient|^ruby|"
                          r"^php|scrapy", re.I)),
]

KIND_LABELS = {
    "search": "Search engine",
    "ai": "AI crawler",
    "seo": "SEO crawler",
    "preview": "Link preview",
    "bot": "Bot",
    "script": "Script",
    "browser": "Browser",
    "partner": "API key",
}


def classify_agent(user_agent: str) -> str:
    agent = user_agent or ""
    for family, pattern in _FAMILIES:
        if pattern.search(agent):
            return family
    if not agent.startswith("Mozilla/"):
        return "script"
    return "browser"


# ---------------------------------------------------------------------------
# Block list (cached per process so the gate doesn't hit SQLite per request)
# ---------------------------------------------------------------------------

_CACHE_TTL_S = 30
_cache_lock = threading.Lock()
_cache: dict = {"at": 0.0, "agents": (), "ips": frozenset()}
_seeded_dbs: set[str] = set()


def _db_key(db_path) -> str:
    return str(db_path or webapp_config.MONITORING_DB_PATH)


def _ensure(conn: sqlite3.Connection, db_key: str) -> None:
    if db_key in _seeded_dbs:
        return
    now = int(time.time())
    conn.executemany(
        """INSERT OR IGNORE INTO blocked_clients (kind, pattern, reason, active, created_by, created_at)
           VALUES (?, ?, ?, 1, 'system', ?)""",
        [(kind, pattern, reason, now) for kind, pattern, reason in SEEDED_BLOCKS],
    )
    conn.commit()
    _seeded_dbs.add(db_key)


def _open(db_path=None) -> sqlite3.Connection:
    init_db(db_path)
    conn = connect(db_path)
    _ensure(conn, _db_key(db_path))
    return conn


def clear_cache() -> None:
    with _cache_lock:
        _cache["at"] = 0.0


def _active_rules(db_path=None) -> tuple[tuple[tuple[int, str], ...], frozenset]:
    now = time.time()
    with _cache_lock:
        if now - _cache["at"] < _CACHE_TTL_S:
            return _cache["agents"], _cache["ips"]
    try:
        conn = _open(db_path)
        try:
            rows = conn.execute(
                "SELECT id, kind, pattern FROM blocked_clients WHERE active = 1"
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        # Never let the block list take the API down; fall back to what we had
        with _cache_lock:
            return _cache["agents"], _cache["ips"]
    agents = tuple((r["id"], r["pattern"].lower()) for r in rows if r["kind"] == "agent")
    ips = frozenset(r["pattern"] for r in rows if r["kind"] == "ip")
    with _cache_lock:
        _cache.update(at=now, agents=agents, ips=ips)
    return agents, ips


def match_block(user_agent: str, ip: str, db_path=None) -> bool:
    agents, ips = _active_rules(db_path)
    if ip and ip in ips:
        return True
    agent = (user_agent or "").lower()
    return any(pattern in agent for _, pattern in agents)


def list_blocks(db_path=None) -> list[dict]:
    conn = _open(db_path)
    try:
        rows = conn.execute(
            """SELECT id, kind, pattern, reason, active, created_by, created_at, removed_by, removed_at
               FROM blocked_clients ORDER BY active DESC, created_at DESC"""
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


class BlockError(ValueError):
    """A block the page should refuse, with a message for the admin."""


def validate_block(kind: str, pattern: str, *, own_agent: str = "", own_ip: str = "") -> str:
    if kind not in KINDS:
        raise BlockError("kind must be 'agent' or 'ip'")
    pattern = (pattern or "").strip()
    if kind == "agent":
        pattern = pattern.lower()
        if len(pattern) < MIN_AGENT_PATTERN:
            raise BlockError(f"Use at least {MIN_AGENT_PATTERN} characters of the client's name")
        if any(pattern in browser.lower() for browser in COMMON_BROWSERS):
            raise BlockError("That would block ordinary browsers. Use a word unique to this client")
        if own_agent and pattern in own_agent.lower():
            raise BlockError("That would block your own browser")
    else:
        if not re.fullmatch(r"[0-9A-Fa-f:.]{3,45}", pattern):
            raise BlockError("That doesn't look like an IP address")
        if own_ip and pattern == own_ip:
            raise BlockError("That is your own IP address")
    return pattern


def add_block(kind: str, pattern: str, reason: str, admin: str, db_path=None,
              *, own_agent: str = "", own_ip: str = "") -> dict:
    pattern = validate_block(kind, pattern, own_agent=own_agent, own_ip=own_ip)
    now = int(time.time())
    conn = _open(db_path)
    try:
        conn.execute(
            """INSERT INTO blocked_clients (kind, pattern, reason, active, created_by, created_at)
               VALUES (?, ?, ?, 1, ?, ?)
               ON CONFLICT(kind, pattern) DO UPDATE SET
                   active = 1, reason = excluded.reason, created_by = excluded.created_by,
                   created_at = excluded.created_at, removed_by = NULL, removed_at = NULL""",
            (kind, pattern, (reason or "").strip()[:300] or None, admin, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM blocked_clients WHERE kind = ? AND pattern = ?", (kind, pattern)
        ).fetchone()
    finally:
        conn.close()
    clear_cache()
    return dict(row)


def remove_block(block_id: int, admin: str, db_path=None) -> dict | None:
    conn = _open(db_path)
    try:
        row = conn.execute("SELECT * FROM blocked_clients WHERE id = ?", (block_id,)).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE blocked_clients SET active = 0, removed_by = ?, removed_at = ? WHERE id = ?",
            (admin, int(time.time()), block_id),
        )
        conn.commit()
    finally:
        conn.close()
    clear_cache()
    return dict(row)


# ---------------------------------------------------------------------------
# Traffic summary
# ---------------------------------------------------------------------------

def _rule_for(user_agent: str, ip: str | None, blocks: list[dict]) -> dict | None:
    agent = (user_agent or "").lower()
    for b in blocks:
        if not b["active"]:
            continue
        if b["kind"] == "agent" and b["pattern"] in agent:
            return b
        if b["kind"] == "ip" and ip and b["pattern"] == ip:
            return b
    return None


def bot_summary(hours: float, db_path=None, limit: int = 150) -> dict:
    since = int(time.time() - hours * 3600) // CLIENT_BUCKET_S * CLIENT_BUCKET_S
    blocks = list_blocks(db_path)
    conn = _open(db_path)
    try:
        totals = conn.execute(
            """SELECT COALESCE(SUM(requests), 0) AS requests, COALESCE(SUM(data_requests), 0) AS data_requests,
                      COALESCE(SUM(blocked), 0) AS blocked
               FROM client_traffic WHERE bucket >= ?""",
            (since,),
        ).fetchone()
        agent_rows = conn.execute(
            """SELECT user_agent,
                      SUM(requests) AS requests, SUM(api_requests) AS api_requests,
                      SUM(data_requests) AS data_requests, SUM(keyed_requests) AS keyed_requests,
                      SUM(errors_4xx) AS errors_4xx, SUM(blocked) AS blocked,
                      COUNT(DISTINCT ip) AS ips, MIN(bucket) AS first_seen, MAX(last_ts) AS last_seen
               FROM client_traffic WHERE bucket >= ?
               GROUP BY user_agent ORDER BY data_requests DESC, requests DESC LIMIT ?""",
            (since, limit),
        ).fetchall()
        peak: dict[str, int] = {}
        active: dict[str, int] = {}
        for r in conn.execute(
            """SELECT user_agent, SUM(data_requests) AS d FROM client_traffic
               WHERE bucket >= ? GROUP BY user_agent, bucket HAVING d > 0""",
            (since,),
        ):
            ua = r["user_agent"]
            peak[ua] = max(peak.get(ua, 0), r["d"])
            active[ua] = active.get(ua, 0) + 1
        ip_rows = conn.execute(
            """SELECT ip, SUM(requests) AS requests, SUM(data_requests) AS data_requests,
                      SUM(keyed_requests) AS keyed_requests, SUM(blocked) AS blocked,
                      COUNT(DISTINCT user_agent) AS agents, MAX(last_ts) AS last_seen,
                      MAX(data_requests) AS peak_data_hour
               FROM client_traffic WHERE bucket >= ? AND ip != 'unknown'
               GROUP BY ip ORDER BY data_requests DESC LIMIT 25""",
            (since,),
        ).fetchall()
        top_agent = {
            r["ip"]: r["user_agent"]
            for r in conn.execute(
                """SELECT ip, user_agent, SUM(data_requests) AS d FROM client_traffic
                   WHERE bucket >= ? GROUP BY ip, user_agent ORDER BY d ASC""",
                (since,),
            )
        }
    finally:
        conn.close()

    clients = []
    for r in agent_rows:
        row = dict(r)
        row["peak_data_hour"] = peak.get(row["user_agent"], 0)
        row["active_hours"] = active.get(row["user_agent"], 0)
        kind = classify_agent(row["user_agent"])
        if row["keyed_requests"] and row["keyed_requests"] >= row["api_requests"] / 2:
            kind = "partner"
        rule = _rule_for(row["user_agent"], None, blocks)
        row.update(
            kind=kind,
            kind_label=KIND_LABELS[kind],
            is_bot=kind != "browser",
            suspect=kind not in ("partner", "search", "preview") and (
                (row["peak_data_hour"] or 0) >= SUSPECT_DATA_PER_HOUR
                or (kind != "browser" and row["data_requests"] >= SUSPECT_DATA_TOTAL)
            ),
            block_id=rule["id"] if rule else None,
        )
        clients.append(row)

    ips = []
    for r in ip_rows:
        row = dict(r)
        agent = top_agent.get(row["ip"], "")
        rule = _rule_for(agent, row["ip"], [b for b in blocks if b["kind"] == "ip"])
        row.update(
            top_agent=agent,
            suspect=not row["keyed_requests"] and (row["peak_data_hour"] or 0) >= SUSPECT_DATA_PER_HOUR,
            block_id=rule["id"] if rule else None,
        )
        ips.append(row)

    bot_requests = sum(c["requests"] for c in clients if c["kind"] not in ("browser", "partner"))
    return {
        "hours": hours,
        "totals": {
            "requests": totals["requests"],
            "data_requests": totals["data_requests"],
            "blocked": totals["blocked"],
            "bot_requests": bot_requests,
            "bot_clients": sum(1 for c in clients if c["kind"] not in ("browser", "partner")),
            "suspects": sum(1 for c in clients if c["suspect"]),
        },
        "clients": clients,
        "ips": ips,
        "blocks": blocks,
        "thresholds": {"suspect_data_per_hour": SUSPECT_DATA_PER_HOUR},
    }
