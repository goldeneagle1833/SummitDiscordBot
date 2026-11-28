"""Usage log for the Summit MCP server (AI apps), shown on the admin page's "AI Apps (MCP)" section.

One row per (UTC day, connector, tool, outcome, caller) with a call count and total
time, in its own small SQLite file (mcp_usage.db next to analytics.db), so each call is
a single UPSERT. Standard library only: the MCP service's venv has just the MCP SDK,
and the Flask site imports this module to read the same file.

Callers are stored only as a short one-way hash ("p:" signed-in player, "ip:" public
visitor), so the table can count distinct players and visitors without holding names,
player ids or IP addresses. Logging never breaks a tool call: errors are swallowed.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(os.environ.get("SUMMIT_MCP_USAGE_DB", Path(__file__).resolve().parent.parent / "mcp_usage.db"))
RETENTION_DAYS = 90
_PRUNE_EVERY = 3600
_last_prune = 0.0
_lock = threading.Lock()

PUBLIC = "public"
ACCOUNT = "account"
RATE_LIMITED_TOOL = "(rate limited)"

OUTCOMES = ("ok", "no_result", "error", "limited", "signin")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS mcp_usage_daily (
    day TEXT NOT NULL,
    connector TEXT NOT NULL,
    tool TEXT NOT NULL,
    outcome TEXT NOT NULL,
    caller TEXT NOT NULL,
    calls INTEGER NOT NULL DEFAULT 0,
    total_ms INTEGER NOT NULL DEFAULT 0,
    last_seen TEXT NOT NULL,
    PRIMARY KEY (day, connector, tool, outcome, caller)
)
"""

_SALT = "summit-mcp-usage-v1"


def caller_key(player_id: str | None = None, ip: str | None = None) -> str:
    """A short one-way id: the same player (or IP) always gets the same key."""
    if player_id:
        return "p:" + hashlib.sha256(f"{_SALT}:player:{player_id}".encode()).hexdigest()[:16]
    return "ip:" + hashlib.sha256(f"{_SALT}:ip:{ip or 'unknown'}".encode()).hexdigest()[:16]


def _connect(path: Path | None = None):
    conn = sqlite3.connect(str(path or DB_PATH), timeout=2)
    conn.execute(_SCHEMA)
    return conn


def record(connector: str, tool: str, outcome: str, caller: str, ms: int = 0,
           now: datetime | None = None, path: Path | None = None) -> None:
    """Count one call. Never raises."""
    global _last_prune
    now = now or datetime.now(timezone.utc)
    try:
        with _lock:
            conn = _connect(path)
            try:
                conn.execute(
                    """INSERT INTO mcp_usage_daily (day, connector, tool, outcome, caller, calls, total_ms, last_seen)
                       VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                       ON CONFLICT (day, connector, tool, outcome, caller) DO UPDATE SET
                           calls = calls + 1, total_ms = total_ms + excluded.total_ms,
                           last_seen = excluded.last_seen""",
                    (now.date().isoformat(), connector, tool[:64], outcome, caller[:40], max(0, int(ms)),
                     now.isoformat(timespec="seconds")),
                )
                if not _last_prune or time.monotonic() - _last_prune > _PRUNE_EVERY:
                    _last_prune = time.monotonic()
                    cutoff = (now.date() - timedelta(days=RETENTION_DAYS)).isoformat()
                    conn.execute("DELETE FROM mcp_usage_daily WHERE day < ?", (cutoff,))
                conn.commit()
            finally:
                conn.close()
    except Exception:
        logger.debug("Could not log MCP usage", exc_info=True)


def _blank() -> dict:
    return {"calls": 0, **{o: 0 for o in OUTCOMES}}


def summary(days: int = 7, now: datetime | None = None, path: Path | None = None) -> dict:
    """Totals, calls per day (public vs signed in) and per tool over the last ``days`` UTC days."""
    now = now or datetime.now(timezone.utc)
    start = (now.date() - timedelta(days=days - 1)).isoformat()
    try:
        conn = _connect(path)
    except sqlite3.Error:
        rows = []
    else:
        try:
            rows = conn.execute(
                "SELECT day, connector, tool, outcome, caller, calls, total_ms, last_seen "
                "FROM mcp_usage_daily WHERE day >= ?",
                (start,),
            ).fetchall()
        finally:
            conn.close()

    totals = {**_blank(), "public": 0, "account": 0, "last_seen": None}
    by_day = {(now.date() - timedelta(days=i)).isoformat(): {**_blank(), "public": 0, "account": 0}
              for i in range(days)}
    tools: dict[str, dict] = {}
    players, visitors = set(), set()
    players_by_day: dict[str, set] = {}

    for day, connector, tool, outcome, caller, calls, total_ms, last_seen in rows:
        side = ACCOUNT if connector == ACCOUNT else PUBLIC
        d = by_day.setdefault(day, {**_blank(), "public": 0, "account": 0})
        for bucket in (totals, d):
            bucket["calls"] += calls
            bucket[outcome] = bucket.get(outcome, 0) + calls
            bucket[side] += calls
        if not totals["last_seen"] or last_seen > totals["last_seen"]:
            totals["last_seen"] = last_seen
        if caller.startswith("p:"):
            players.add(caller)
            players_by_day.setdefault(day, set()).add(caller)
        else:
            visitors.add(caller)
        t = tools.setdefault(tool, {"tool": tool, **_blank(), "public": 0, "account": 0, "total_ms": 0,
                                    "timed": 0, "_players": set(), "_visitors": set(), "last_seen": ""})
        t["calls"] += calls
        t[outcome] = t.get(outcome, 0) + calls
        t[side] += calls
        if outcome != "limited":
            t["total_ms"] += total_ms
            t["timed"] += calls
        (t["_players"] if caller.startswith("p:") else t["_visitors"]).add(caller)
        t["last_seen"] = max(t["last_seen"], last_seen)

    by_tool = []
    for t in tools.values():
        timed = t.pop("timed")
        total_ms = t.pop("total_ms")
        t["avg_ms"] = round(total_ms / timed) if timed else None
        t["players"] = len(t.pop("_players"))
        t["visitors"] = len(t.pop("_visitors"))
        by_tool.append(t)
    by_tool.sort(key=lambda t: (t["tool"] == RATE_LIMITED_TOOL, -t["calls"], t["tool"]))

    return {
        "days": days,
        "totals": {**totals, "players": len(players), "visitors": len(visitors)},
        "by_day": [{"day": k, **v, "players": len(players_by_day.get(k, ()))} for k, v in sorted(by_day.items())],
        "by_tool": by_tool,
        "retention_days": RETENTION_DAYS,
    }
