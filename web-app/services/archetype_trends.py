"""Monthly Sorcerers Summit ranked archetype shares throughout the Gothic era.

Each eligible ranked match contributes two possible deck appearances. Only
appearances with a valid historical deck JSON count towards popularity share;
missing information is reported separately as coverage. Counts come directly
from the match-time deck snapshots, never from merged/clustering deck records.

The public API contains aggregated totals only, without player names or decks.
"""

import json
import logging
import sqlite3
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from repositories.archetype_decks import element_label
from services.tournament_normalization import GOTHIC_START
from webapp_config import MATCH_RECORDS_DB_PATH

logger = logging.getLogger(__name__)

MATCH_TABLES = (
    ("match_records", "match_id"),
    ("match_records_archive", "original_match_id"),
    ("season_match_records", "match_id"),
)
CACHE_SECONDS = 600
_cache_lock = threading.Lock()
_cached_at = 0.0
_cached_data = None


def classify_deck(raw_json):
    """Return (avatar, elements) from a deck recorded at match time, if known.

    Use the same spellbook element counting rule as Deck Archetypes. A missing
    avatar or spellbook must not be guessed from a player's later deck.
    """
    if not raw_json or raw_json in ("", "{}"):
        return None
    try:
        raw = json.loads(raw_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    avatar_list = raw.get("avatar") or []
    spellbook = raw.get("spellbook") or []
    if not isinstance(avatar_list, list) or not avatar_list or not isinstance(avatar_list[0], dict):
        return None
    if not isinstance(spellbook, list) or not any(
        isinstance(card, dict) and str(card.get("name") or "").strip()
        for card in spellbook
    ):
        return None
    avatar = str(avatar_list[0].get("name") or "").strip()
    if not avatar or avatar == "Unknown":
        return None
    elements = element_label(spellbook)
    if elements == "None":
        return None
    return avatar, elements


def _utc_day(stamp):
    """Match the Meta Report convention for historical match timestamps."""
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(str(stamp)).astimezone(timezone.utc).date().isoformat()
    except ValueError:
        # Older match timestamps may not include an ISO time portion.
        return str(stamp)[:10]


def monthly_ranked_trends(db_path=None):
    """Aggregate a read-only match archive into dated archetype appearances."""
    db_path = Path(db_path or MATCH_RECORDS_DB_PATH)
    if not db_path.exists():
        return {"months": [], "archetypes": [], "totalMatches": 0,
                "classifiedAppearances": 0, "possibleAppearances": 0,
                "start": GOTHIC_START, "coverage": 0.0}

    counts = defaultdict(Counter)
    matches = Counter()
    classified = Counter()
    by_id = {}
    seen_ids = set()
    # Include the previous day for time-zone offsets around midnight.
    earliest_scan = "2025-12-04" if GOTHIC_START == "2025-12-05" else GOTHIC_START
    today = datetime.now(timezone.utc).date().isoformat()

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    try:
        for table, id_column in MATCH_TABLES:
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            required = {"timestamp", "json_deck_data_winner", "json_deck_data_loser"}
            if not required <= columns:
                continue
            match_id = id_column if id_column in columns else "NULL"
            ranked_filter = (
                " AND (match_type = 'ranked' OR match_type IS NULL)"
                if "match_type" in columns else ""
            )
            rows = conn.execute(
                f"""SELECT {match_id}, timestamp, json_deck_data_winner,
                           json_deck_data_loser FROM {table}
                    WHERE substr(timestamp, 1, 10) >= ?{ranked_filter}""",
                (earliest_scan,),
            )
            for record_id, stamp, winner_json, loser_json in rows:
                day = _utc_day(stamp)
                if day is None or day < GOTHIC_START or day > today:
                    continue
                if record_id is not None:
                    # The live and archive tables can contain the same match.
                    if record_id in seen_ids:
                        continue
                    seen_ids.add(record_id)
                month = day[:7]
                matches[month] += 1
                for raw in (winner_json, loser_json):
                    identity = classify_deck(raw)
                    if identity is None:
                        continue
                    avatar, elements = identity
                    key = f"{avatar}-{elements}".lower().replace(" / ", "-").replace(" ", "-")
                    by_id[key] = {"id": key, "name": f"{avatar} · {elements}",
                                  "avatar": avatar, "elements": elements}
                    counts[month][key] += 1
                    classified[month] += 1
    finally:
        conn.close()

    # Preserve months with no recorded matches as gaps rather than connecting
    # adjacent lines across an unknown stretch of time.
    end_month = datetime.now(timezone.utc).date().strftime("%Y-%m")
    year, month_number = map(int, GOTHIC_START[:7].split("-"))
    months_in_range = []
    while f"{year:04d}-{month_number:02d}" <= end_month:
        months_in_range.append(f"{year:04d}-{month_number:02d}")
        month_number += 1
        if month_number == 13:
            year += 1
            month_number = 1

    total_counts = Counter()
    month_rows = []
    for month in months_in_range:
        total_counts.update(counts[month])
        possible = matches[month] * 2
        known = classified[month]
        month_rows.append({
            "month": month,
            "matches": matches[month],
            "possibleAppearances": possible,
            "classifiedAppearances": known,
            "coverage": round(known * 100 / possible, 1) if possible else 0.0,
            "counts": dict(counts[month]),
        })
    total_matches = sum(matches.values())
    possible_total = total_matches * 2
    known_total = sum(classified.values())
    return {
        "start": GOTHIC_START,
        "months": month_rows,
        "archetypes": sorted(
            [{**info, "totalAppearances": total_counts[key]}
             for key, info in by_id.items()],
            key=lambda a: (-a["totalAppearances"], a["name"]),
        ),
        "totalMatches": total_matches,
        "possibleAppearances": possible_total,
        "classifiedAppearances": known_total,
        "coverage": round(known_total * 100 / possible_total, 1) if possible_total else 0.0,
    }


def get_ranked_trends():
    """Cache the complete series, including monthly data completeness."""
    global _cached_data, _cached_at
    now = time.monotonic()
    if _cached_data is not None and now - _cached_at < CACHE_SECONDS:
        return _cached_data
    with _cache_lock:
        now = time.monotonic()
        if _cached_data is not None and now - _cached_at < CACHE_SECONDS:
            return _cached_data
        result = monthly_ranked_trends()
        _cached_data = result
        _cached_at = time.monotonic()
        logger.info("Ranked archetype trends: %s matches, %.1f%% classified",
                    result["totalMatches"], result["coverage"])
        return result
