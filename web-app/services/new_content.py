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


def _row(db_path, query: str, params: tuple = ()):
    if not db_path or not os.path.exists(str(db_path)):
        return None
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    try:
        return conn.execute(query, params).fetchone()
    finally:
        conn.close()


def _item(at: datetime | None, text: str, link: str | None = None) -> dict | None:
    """One source's newest content: when, a short line for the page's "What's new" bar, a link."""
    if at is None:
        return None
    return {"at": at, "text": text, "link": link}


# -- Sources -----------------------------------------------------------

def latest_event_import() -> dict | None:
    """The newest Top 8 event import (latest_event.json)."""
    path = webapp_config.TOP_8_DIR / "latest_event.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    folder = data.get("folder") or ""
    name = folder
    try:
        from utils.formatting import format_event_name
        name = format_event_name(folder)
        meta_path = webapp_config.TOP_8_DIR / "_event_metadata.json"
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                name = (json.load(f).get(folder) or {}).get("name") or name
    except Exception:
        pass
    return _item(parse_time(data.get("added_at"), naive_is_utc=False),
                 f"New Top 8 event: {name}", f"/top-8/{folder}" if folder else "/top-8")


def latest_stats_release(now: datetime | None = None) -> dict | None:
    """The newest stats batch (out at 00:01 UTC on the 1st/15th)."""
    from services.meta_report import PUBLISH_DELAY
    from services.data_release import latest_released_period

    period = latest_released_period(now)
    at = datetime.combine(period.publish_day, dtime(0), tzinfo=timezone.utc) + PUBLISH_DELAY
    through = f"{period.end:%b} {period.end.day}"
    return _item(at, f"New stats batch: games through {through}", "/meta-report")


def latest_article() -> dict | None:
    row = _row(
        webapp_config.ARTICLES_DB_PATH,
        "SELECT published_at, id, slug, title FROM articles WHERE status = 'approved' "
        "AND published_at IS NOT NULL ORDER BY published_at DESC LIMIT 1",
    )
    if not row:
        return None
    return _item(parse_time(row[0], naive_is_utc=True), f"New article: {row[3]}", f"/articles/{row[1]}-{row[2]}")


def latest_bracket() -> dict | None:
    row = _row(
        webapp_config.MATCH_RECORDS_DB_PATH,
        "SELECT published_at, slug, name FROM brackets WHERE published_at IS NOT NULL "
        "ORDER BY published_at DESC LIMIT 1",
    )
    if not row:
        return None
    return _item(parse_time(row[0], naive_is_utc=False), f"New bracket: {row[2]}", f"/brackets/{row[1]}")


def latest_explorer_event() -> dict | None:
    row = _row(webapp_config.EXPLORER_DB_PATH,
               "SELECT fetched_at, event_name FROM explorer_events ORDER BY fetched_at DESC LIMIT 1")
    if not row:
        return None
    # sqlite datetime('now') is UTC
    return _item(parse_time(row[0], naive_is_utc=True), f"New Explorer Series event: {row[1]}", "/explorer-series")


def latest_store_product() -> dict | None:
    from repositories.store import STORE_DB_PATH

    row = _row(
        STORE_DB_PATH,
        # Private (link only) listings don't announce themselves
        "SELECT p.created_at, p.name FROM products p WHERE p.is_active = 1 AND "
        "p.is_private = 0 AND p.storefront_id IN (SELECT id FROM storefronts WHERE is_active = 1) "
        "ORDER BY p.created_at DESC LIMIT 1",
    )
    if not row:
        return None
    return _item(parse_time(row[0], naive_is_utc=True), f"New in the store: {row[1]}", "/store")


SOURCES = {
    "event": latest_event_import,
    "release": latest_stats_release,
    "articles": latest_article,
    "brackets": latest_bracket,
    "explorer": latest_explorer_event,
    "store": latest_store_product,
}


def compute_new_content(now: datetime | None = None) -> dict:
    """{"latest": page key -> ISO time of its newest content,
        "notes": page key -> {"text", "link"}}, only for content in the window."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=NEW_WINDOW_DAYS)
    items: dict[str, dict | None] = {}
    for name, fn in SOURCES.items():
        try:
            items[name] = fn(now) if name == "release" else fn()
        except Exception:
            logger.warning("new-content source %s failed", name, exc_info=True)
            items[name] = None
    latest, notes = {}, {}
    for page, source in PAGE_SOURCES.items():
        item = items.get(source)
        if item and cutoff <= item["at"] <= now + timedelta(minutes=5):
            latest[page] = _iso(item["at"])
            notes[page] = {"text": item["text"], "link": item["link"]}
    return {"latest": latest, "notes": notes}


def compute_latest(now: datetime | None = None) -> dict[str, str]:
    return compute_new_content(now)["latest"]


def get_new_content() -> dict:
    """Cached compute_new_content(): worked out at most once every CACHE_SECONDS per worker."""
    with _lock:
        if _cache["latest"] is not None and time.time() - _cache["at"] < CACHE_SECONDS:
            return _cache["latest"]
    data = compute_new_content()
    with _lock:
        _cache["latest"] = data
        _cache["at"] = time.time()
    return data


def clear_cache() -> None:
    with _lock:
        _cache["latest"] = None
        _cache["at"] = 0.0
