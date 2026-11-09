"""New-content dots for the site menu.

Each menu page gets a "latest content" time: when something new last appeared
on it (a Top 8 event imported, a stats batch released, an article approved...).
The menu shows a dot next to a link when that time is newer than when the
person last opened the page.

The latest times are the same for everyone, so they are worked out once and
cached for a few minutes; a visitor never triggers more than one cheap read of
what they have already seen. Every source is our own saved data (no PSO or
other outside calls).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, time as dtime, timedelta, timezone

import webapp_config

logger = logging.getLogger(__name__)

CACHE_SECONDS = 300
# Content older than this never gets a dot, so a first-time visitor doesn't
# open a menu full of them.
NEW_WINDOW_DAYS = 14

# Menu page key -> where its "latest content" time comes from.
PAGE_SOURCES = {
    "top-8": "event",
    "deck-rec": "event",
    "deck-archetypes": "event",
    "meta-report": "release",
    "avatars": "release",
    "card-stats": "release",
    "articles": "articles",
    "brackets": "brackets",
    "explorer": "explorer",
    "store": "store",
}

_cache: dict = {"at": 0.0, "latest": None}
_lock = threading.Lock()


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(value, naive_is_utc: bool) -> datetime | None:
    """Parse a stored timestamp. Naive values are server-local unless naive_is_utc."""
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    if " " in text and "T" not in text:
        text = text.replace(" ", "T", 1)
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc) if naive_is_utc else dt.astimezone()
    return dt.astimezone(timezone.utc)


def _scalar(db_path, query: str, params: tuple = ()) -> str | None:
    if not db_path or not os.path.exists(str(db_path)):
        return None
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    try:
        row = conn.execute(query, params).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


# -- Sources -----------------------------------------------------------

def latest_event_import() -> datetime | None:
    """When the newest Top 8 event was imported (latest_event.json)."""
    path = webapp_config.TOP_8_DIR / "latest_event.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return parse_time(data.get("added_at"), naive_is_utc=False)


def latest_stats_release(now: datetime | None = None) -> datetime | None:
    """Publish time of the newest stats batch (00:01 UTC on the 1st/15th)."""
    from services.meta_report import PUBLISH_DELAY
    from services.data_release import latest_released_period

    day = latest_released_period(now).publish_day
    return datetime.combine(day, dtime(0), tzinfo=timezone.utc) + PUBLISH_DELAY


def latest_article() -> datetime | None:
    value = _scalar(
        webapp_config.ARTICLES_DB_PATH,
        "SELECT MAX(published_at) FROM articles WHERE status = 'approved'",
    )
    return parse_time(value, naive_is_utc=True)


def latest_bracket() -> datetime | None:
    value = _scalar(
        webapp_config.MATCH_RECORDS_DB_PATH,
        "SELECT MAX(published_at) FROM brackets WHERE published_at IS NOT NULL",
    )
    return parse_time(value, naive_is_utc=False)


def latest_explorer_event() -> datetime | None:
    value = _scalar(webapp_config.EXPLORER_DB_PATH, "SELECT MAX(fetched_at) FROM explorer_events")
    return parse_time(value, naive_is_utc=True)  # sqlite datetime('now') is UTC


def latest_store_product() -> datetime | None:
    from repositories.store import STORE_DB_PATH

    value = _scalar(
        STORE_DB_PATH,
        "SELECT MAX(p.created_at) FROM products p WHERE p.is_active = 1 AND "
        "p.storefront_id IN (SELECT id FROM storefronts WHERE is_active = 1)",
    )
    return parse_time(value, naive_is_utc=True)


SOURCES = {
    "event": latest_event_import,
    "release": latest_stats_release,
    "articles": latest_article,
    "brackets": latest_bracket,
    "explorer": latest_explorer_event,
    "store": latest_store_product,
}


def compute_latest(now: datetime | None = None) -> dict[str, str]:
    """page key -> ISO time of its newest content, only for content in the window."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=NEW_WINDOW_DAYS)
    times: dict[str, datetime | None] = {}
    for name, fn in SOURCES.items():
        try:
            times[name] = fn(now) if name == "release" else fn()
        except Exception:
            logger.warning("new-content source %s failed", name, exc_info=True)
            times[name] = None
    latest = {}
    for page, source in PAGE_SOURCES.items():
        dt = times.get(source)
        if dt is not None and cutoff <= dt <= now + timedelta(minutes=5):
            latest[page] = _iso(dt)
    return latest


def get_latest() -> dict[str, str]:
    """Cached compute_latest(): worked out at most once every CACHE_SECONDS per worker."""
    with _lock:
        if _cache["latest"] is not None and time.time() - _cache["at"] < CACHE_SECONDS:
            return _cache["latest"]
    latest = compute_latest()
    with _lock:
        _cache["latest"] = latest
        _cache["at"] = time.time()
    return latest


def clear_cache() -> None:
    with _lock:
        _cache["latest"] = None
        _cache["at"] = 0.0
