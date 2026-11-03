"""Saved copies of Play Sorcery Online's ranked card table.

PSO only releases new card data on the 1st and 15th (00:00 UTC), so there is
no reason to ask it on every page visit. Once per release this module pulls
PSO's ``/cards`` table for every selection the site offers by name and keeps
it in our own database (CARD_SNAPSHOTS_DB_PATH):

- ``all``       All time
- ``season:<id>`` each Summit season (same dates as /api/ranked-analytics/seasons)
- ``recent``    the last RECENT_DAYS days up to the latest release (Staples default)

Card Win Rates and the Staples API read these rows. A page visit never calls
PSO for them, and they keep working while PSO is down. Only selections nobody
can name ahead of time (custom date ranges) still go to PSO live.

The refresh runs from the Meta Report scheduler (one worker at a time). A
selection is fetched again when its copy is older than the latest release,
and retried at most hourly while PSO has not caught up yet.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import webapp_config
from services import ranked_analytics

logger = logging.getLogger(__name__)

FORMAT = "constructed"
RECENT_DAYS = 90
RETRY_AFTER = timedelta(hours=1)

_init_lock = threading.Lock()
_ready: set[str] = set()


def _db_path() -> Path:
    return Path(webapp_config.CARD_SNAPSHOTS_DB_PATH)


def _connect() -> sqlite3.Connection:
    path = _db_path()
    key = str(path)
    conn = sqlite3.connect(key, timeout=15)
    conn.row_factory = sqlite3.Row
    if key not in _ready:
        with _init_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pso_card_snapshots (
                    selection_key TEXT PRIMARY KEY,   -- all | season:<id> | recent
                    label TEXT NOT NULL,
                    date_from TEXT,                   -- YYYY-MM-DD or NULL (open)
                    date_through TEXT,                -- YYYY-MM-DD or NULL (open)
                    body TEXT,                        -- PSO /cards JSON, NULL until first success
                    released_through TEXT,            -- PSO's releasedThrough in that body
                    fetched_at TEXT,                  -- last successful fetch, UTC
                    attempted_at TEXT                 -- last attempt, UTC
                )
            """)
            conn.commit()
            _ready.add(key)
    return conn


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def _parse(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    return datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def latest_release(now: datetime | None = None) -> tuple[date, datetime]:
    """(last day of released data, moment it was released) for the newest batch."""
    from services import meta_report

    now = now or _now()
    period = meta_report.latest_due_period(meta_report.report_today(now))
    released_at = datetime.combine(period.publish_day, datetime.min.time(), tzinfo=timezone.utc)
    return period.end, released_at + meta_report.PUBLISH_DELAY


def selections(now: datetime | None = None) -> list[dict]:
    """Every selection saved ahead of time."""
    cutoff, _ = latest_release(now)
    chosen = [
        {"key": "all", "label": "All time", "from": None, "through": None},
        {"key": "recent", "label": f"Last {RECENT_DAYS} days",
         "from": (cutoff - timedelta(days=RECENT_DAYS - 1)).isoformat(), "through": cutoff.isoformat()},
    ]
    for season in ranked_analytics.list_seasons():
        chosen.append({"key": f"season:{season['id']}", "label": season["name"],
                       "from": season["from"], "through": season["through"]})
    return chosen


def _params(selection: dict) -> dict:
    params = {"format": FORMAT}
    if selection["from"]:
        params["from"] = selection["from"]
    if selection["through"]:
        params["through"] = selection["through"]
    return params


def find(date_from: str | None, date_through: str | None) -> dict | None:
    """The named selection with exactly these dates, or None (a custom range)."""
    for selection in selections():
        if (selection["from"] or None, selection["through"] or None) == (date_from or None, date_through or None):
            return selection
    return None


def saved(key: str) -> dict | None:
    """The saved PSO body for a selection key, or None."""
    with _connect() as conn:
        row = conn.execute("SELECT body FROM pso_card_snapshots WHERE selection_key = ?", (key,)).fetchone()
    if not row or not row["body"]:
        return None
    try:
        body = json.loads(row["body"])
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def fetch_and_save(selection: dict) -> dict | None:
    """Ask PSO for one selection and save the answer. None if PSO can't answer."""
    now = _stamp(_now())
    body = None
    try:
        result = ranked_analytics.forward("GET", "cards", params=_params(selection))
        if result.status == 200 and isinstance(result.body, dict):
            body = result.body
    except ranked_analytics.AnalyticsUnavailable as exc:
        logger.info("Card snapshot %s: PSO unavailable: %s", selection["key"], exc)
    with _connect() as conn:
        conn.execute("""
            INSERT INTO pso_card_snapshots (selection_key, label, date_from, date_through, attempted_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(selection_key) DO UPDATE SET
                label = excluded.label, date_from = excluded.date_from,
                date_through = excluded.date_through, attempted_at = excluded.attempted_at
        """, (selection["key"], selection["label"], selection["from"], selection["through"], now))
        if body is not None and body.get("dataAvailable") is not False:
            conn.execute("""
                UPDATE pso_card_snapshots SET body = ?, released_through = ?, fetched_at = ?
                WHERE selection_key = ?
            """, (json.dumps(body, separators=(",", ":")), body.get("releasedThrough"), now, selection["key"]))
        conn.commit()
    return body if body is not None and body.get("dataAvailable") is not False else None


def get(selection: dict) -> dict | None:
    """Saved body for a named selection.

    Only a selection we have never saved (first visit after a deploy, or a
    brand new season) asks PSO, and at most once an hour while PSO is down.
    """
    body = saved(selection["key"])
    if body is not None:
        return body
    with _connect() as conn:
        row = conn.execute("SELECT attempted_at FROM pso_card_snapshots WHERE selection_key = ?",
                           (selection["key"],)).fetchone()
    attempted = _parse(row["attempted_at"]) if row else None
    if attempted and _now() - attempted < RETRY_AFTER:
        return None
    return fetch_and_save(selection)


def _needs_refresh(row: sqlite3.Row | None, selection: dict, cutoff: date, released_at: datetime,
                   now: datetime) -> bool:
    if row is None or not row["body"]:
        attempted = _parse(row["attempted_at"]) if row else None
        return attempted is None or now - attempted >= RETRY_AFTER
    if (row["date_from"], row["date_through"]) != (selection["from"], selection["through"]):
        return True  # season dates changed (e.g. the running season ended)
    fetched = _parse(row["fetched_at"])
    if fetched is None or fetched < released_at:
        attempted = _parse(row["attempted_at"])
        return attempted is None or attempted < released_at or now - attempted >= RETRY_AFTER
    # Fetched after the release but PSO had not caught up yet: retry hourly.
    wanted = cutoff.isoformat()
    if selection["through"] and selection["through"] < wanted:
        wanted = selection["through"]
    behind = (row["released_through"] or "") < wanted
    attempted = _parse(row["attempted_at"])
    return behind and (attempted is None or now - attempted >= RETRY_AFTER)


def refresh_due(now: datetime | None = None) -> int:
    """Fetch every selection whose copy predates the latest release. Returns how many were fetched."""
    now = now or _now()
    cutoff, released_at = latest_release(now)
    with _connect() as conn:
        rows = {r["selection_key"]: r for r in conn.execute("SELECT * FROM pso_card_snapshots")}
    fetched = 0
    for selection in selections(now):
        if _needs_refresh(rows.get(selection["key"]), selection, cutoff, released_at, now):
            fetch_and_save(selection)
            fetched += 1
    return fetched


def status() -> list[dict]:
    """Saved selections and when they were fetched (for admins and tests)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT selection_key, label, date_from, date_through, released_through, fetched_at, attempted_at "
            "FROM pso_card_snapshots ORDER BY selection_key"
        ).fetchall()
    return [dict(r) for r in rows]


def reset() -> None:
    """For tests: forget every saved copy."""
    with _connect() as conn:
        conn.execute("DELETE FROM pso_card_snapshots")
        conn.commit()
