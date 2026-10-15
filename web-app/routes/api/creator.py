"""Popular Cards API (the page used to be creator-only "Creator Stats").

Public with the same season limits creators had: the running season is never
offered on its own (only finished events, past season ranges, and all-time).
Admins can still ask for the running season.
"""

import json
import logging
import sqlite3
import threading
import time
from collections import defaultdict

from flask import Blueprint, jsonify, request

from repositories.card_catalog import CardCatalogRepository
from webapp_config import MATCH_RECORDS_DB_PATH, ELO_DB_PATH, SEASON_FILTERS
from utils.auth import is_admin
from routes.api.cards import _build_card_image_lookup, _find_card_image, _get_event_date_range

logger = logging.getLogger(__name__)

creator_bp = Blueprint("creator", __name__)

# Both endpoints read every reported decklist, so results are cached per worker
# for a few minutes; the lock keeps a burst of visitors from each starting the
# same build.
_CACHE_TTL_SECONDS = 600
_cache = {}  # key -> (built_at, data)
_cache_lock = threading.Lock()


def _cached(key, build):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < _CACHE_TTL_SECONDS:
        return hit[1]
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < _CACHE_TTL_SECONDS:
            return hit[1]
        data = build()
        _cache[key] = (time.time(), data)
        return data


def _active_event_ids():
    try:
        conn = sqlite3.connect(str(ELO_DB_PATH))
        try:
            rows = conn.execute("SELECT event_id FROM events WHERE is_active = 1").fetchall()
        finally:
            conn.close()
        return {str(r[0]) for r in rows}
    except sqlite3.OperationalError:
        return set()


@creator_bp.route("/filters")
def get_creator_filters():
    """Return available past events and sources for the Popular Cards filter dropdown.

    Same format as /api/avatars/filters but excludes active events (admins see them).
    """
    events = []

    # Get events from elo.db (exclude active)
    try:
        conn = sqlite3.connect(str(ELO_DB_PATH))
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'")
        if cur.fetchone():
            cur.execute("""
                SELECT event_id, event_name, start_date, end_date, is_active
                FROM events
                ORDER BY start_date DESC
            """)
            user_admin = is_admin()
            for row in cur.fetchall():
                active = bool(row[4])
                if active and not user_admin:
                    continue  # The running season is admin-only
                events.append({
                    "event_id": row[0],
                    "event_name": row[1],
                    "start_date": row[2],
                    "end_date": row[3],
                    "is_active": active,
                })
        conn.close()
    except sqlite3.OperationalError as e:
        logger.warning(f"Could not query events: {e}")

    # Append season date-range filters
    for sf in SEASON_FILTERS:
        events.append({
            "event_id": sf["id"],
            "event_name": sf["name"],
            "start_date": sf["start_date"],
            "end_date": sf["end_date"],
            "is_active": False,
        })

    return jsonify({"events": events})


@creator_bp.route("/popular-cards")
def get_creator_popular_cards():
    """Card popularity stats from match_records (same source as live-popular-cards).

    Query params:
    - event: event_id or season filter ID (e.g. "season_gothic_1"). Omit for all data.
      "current" and the running season's event_id are admin-only.
    - source: "discord" | "web" | "all" (default: "all")
    """
    event_filter = request.args.get("event", "all")
    source_filter = request.args.get("source", "all")
    if source_filter not in ("discord", "web", "all"):
        source_filter = "all"

    if not is_admin() and (event_filter == "current" or event_filter in _active_event_ids()):
        return jsonify({"error": "The current season isn't public yet"}), 403

    if event_filter not in ("all", "current") and not event_filter.startswith("season_"):
        try:
            event_filter = str(int(event_filter))
        except ValueError:
            return jsonify([])

    result = _cached(("popular", event_filter, source_filter),
                     lambda: _build_popular_cards(event_filter, source_filter))
    if result is None:
        return jsonify({"error": "Failed to load card data"}), 500
    return jsonify(result)


def _build_popular_cards(event_filter, source_filter):

    # Load card metadata from DB
    card_metadata = {}
    try:
        catalog = CardCatalogRepository()
        for card in catalog.get_all_cards():
            sets_json = json.loads(card.get("sets_json") or "[]")
            card_metadata[card["name"]] = {
                "type": card.get("card_type", "Unknown"),
                "element": card.get("elements", "None"),
                "rarity": card.get("rarity", "Unknown"),
                "set": sets_json[0].get("name", "Unknown") if sets_json else "Unknown",
            }
    except Exception as e:
        logger.error(f"Error loading card pool: {e}")
        return None

    # Match the avatar winrates query pattern exactly
    deck_where = ("((json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{}')"
                  " OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{}'))")
    solo_deck_where = "json_deck_data IS NOT NULL AND json_deck_data != '' AND json_deck_data != '{}'"

    # Source filter (same as avatar winrates)
    if source_filter == "discord":
        source_clause = "AND (source = 'Discord' OR source IS NULL)"
    elif source_filter == "web":
        source_clause = "AND source != 'Discord' AND source IS NOT NULL"
    else:
        source_clause = ""

    # Decks are tallied as they are read rather than held in memory
    card_stats = {}
    deck_count = [0]
    sections = ["avatar", "spellbook", "atlas", "sideboard"]

    def _add_deck(deck):
        if isinstance(deck, list) and len(deck) > 0:
            deck = deck[0]
        if not isinstance(deck, dict):
            return
        deck_count[0] += 1
        cards_in_deck = set()
        for section in sections:
            for card in deck.get(section, []) or []:
                card_name = card.get("name")
                quantity = card.get("quantity", 1)
                if not card_name:
                    continue
                if card_name not in card_stats:
                    card_stats[card_name] = {"total_count": 0, "decks_with_card": 0, "sideboard_count": 0}
                card_stats[card_name]["total_count"] += quantity
                if section == "sideboard":
                    card_stats[card_name]["sideboard_count"] += quantity
                if card_name not in cards_in_deck:
                    card_stats[card_name]["decks_with_card"] += 1
                    cards_in_deck.add(card_name)
    conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
    cur = conn.cursor()

    def _parse_deck_rows(rows, dual_column=True):
        """Parse deck JSON from query rows and tally each deck."""
        for row in rows:
            if dual_column:
                for deck_str in [row[0], row[1]]:
                    if deck_str and deck_str not in ("", "{}"):
                        try:
                            _add_deck(json.loads(deck_str))
                        except json.JSONDecodeError:
                            pass
            else:
                if row[0]:
                    try:
                        _add_deck(json.loads(row[0]))
                    except json.JSONDecodeError:
                        pass

    if event_filter in ("all", "current"):
        # Query current match_records (same as avatar winrates "all"/"current" path)
        try:
            cur.execute(f"""
                SELECT json_deck_data_winner, json_deck_data_loser
                FROM match_records
                WHERE {deck_where} {source_clause}
            """)
            _parse_deck_rows(cur)
        except sqlite3.OperationalError as e:
            logger.warning(f"Error querying match_records: {e}")

        # For "all", also include archive (same as avatar winrates)
        if event_filter == "all":
            try:
                cur.execute(f"""
                    SELECT json_deck_data_winner, json_deck_data_loser
                    FROM match_records_archive
                    WHERE {deck_where}
                """)
                _parse_deck_rows(cur)
            except sqlite3.OperationalError:
                logger.info("Archive table not found - continuing without archive data")

        # Solo match reports (no source column in this table)
        try:
            cur.execute(f"""
                SELECT json_deck_data FROM solo_match_reports
                WHERE {solo_deck_where}
            """)
            _parse_deck_rows(cur, dual_column=False)
        except sqlite3.OperationalError:
            pass

    elif isinstance(event_filter, str) and event_filter.startswith("season_"):
        # Season date-range filter - query both tables by timestamp (same as avatar winrates)
        start_date, end_date = _get_event_date_range(event_filter)
        if start_date and end_date:
            # match_records has source column, archive does not
            try:
                cur.execute(f"""
                    SELECT json_deck_data_winner, json_deck_data_loser
                    FROM match_records
                    WHERE {deck_where} {source_clause}
                      AND timestamp >= ? AND timestamp <= ?
                """, (start_date, end_date))
                _parse_deck_rows(cur)
            except sqlite3.OperationalError:
                pass
            try:
                cur.execute(f"""
                    SELECT json_deck_data_winner, json_deck_data_loser
                    FROM match_records_archive
                    WHERE {deck_where}
                      AND timestamp >= ? AND timestamp <= ?
                """, (start_date, end_date))
                _parse_deck_rows(cur)
            except sqlite3.OperationalError:
                pass
            # Solo match reports with date range (no source column, uses report_date)
            try:
                cur.execute(f"""
                    SELECT json_deck_data FROM solo_match_reports
                    WHERE {solo_deck_where}
                      AND report_date >= ? AND report_date <= ?
                """, (start_date, end_date))
                _parse_deck_rows(cur, dual_column=False)
            except sqlite3.OperationalError:
                pass

    else:
        # Specific past event - query archive by event_id (same as avatar winrates)
        try:
            event_id = int(event_filter)
            cur.execute(f"""
                SELECT json_deck_data_winner, json_deck_data_loser
                FROM match_records_archive
                WHERE {deck_where} AND event_id = ?
            """, (event_id,))
            _parse_deck_rows(cur)
        except (ValueError, sqlite3.OperationalError) as e:
            logger.warning(f"Error querying archive for event {event_filter}: {e}")

    conn.close()

    total_decks = deck_count[0]
    if not total_decks:
        return []

    card_list = []
    for name, stats in card_stats.items():
        decks_with = stats["decks_with_card"]
        total_count = stats["total_count"]

        if decks_with == 0:
            continue

        average_played = round(total_count / decks_with) if decks_with > 0 else 0
        percent_of_decks = round((decks_with / total_decks) * 100) if total_decks > 0 else 0

        meta = card_metadata.get(name, {})

        card_list.append({
            "name": name,
            "type": meta.get("type", "Unknown"),
            "element": meta.get("element", "None"),
            "count": total_count,
            "rarity": meta.get("rarity", "Unknown"),
            "set": meta.get("set", "Unknown"),
            "average_played": average_played,
            "percent_of_decks": percent_of_decks,
            "decks_with_card": decks_with,
            "total_decks": total_decks,
            "sideboard_count": stats["sideboard_count"],
        })

    # Add card images
    card_image_lookup = _build_card_image_lookup()
    for card in card_list:
        card["image"] = _find_card_image(card["name"], card_image_lookup)

    card_list.sort(key=lambda x: (x["percent_of_decks"], x["count"]), reverse=True)

    return card_list


@creator_bp.route("/card-history")
def get_card_history():
    """Monthly popularity trend for a specific card.

    Query params:
    - card: card name (required)
    - source: "discord" | "web" | "all" (default: "all")

    Returns list of {month, decks_with_card, total_decks, percent_of_decks} sorted chronologically.
    """
    card_name = request.args.get("card", "").strip()
    if not card_name:
        return jsonify({"error": "card parameter required"}), 400

    source_filter = request.args.get("source", "all")
    if source_filter not in ("discord", "web", "all"):
        source_filter = "all"

    totals, per_card = _cached(("history", source_filter), lambda: _build_card_history(source_filter))
    card_months = per_card.get(card_name, {})

    result = []
    for month in sorted(totals.keys()):
        total = totals[month]
        with_card = card_months.get(month, 0)
        result.append({
            "month": month,
            "total_decks": total,
            "decks_with_card": with_card,
            "percent_of_decks": round((with_card / total) * 100, 1) if total > 0 else 0,
        })

    return jsonify(result)


def _build_card_history(source_filter):
    """Decks per month, and decks per month containing each card, for every card at once."""

    if source_filter == "discord":
        source_clause = "AND (source = 'Discord' OR source IS NULL)"
    elif source_filter == "web":
        source_clause = "AND source != 'Discord' AND source IS NOT NULL"
    else:
        source_clause = ""

    deck_where = ("((json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{}')"
                  " OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{}'))")
    solo_deck_where = "json_deck_data IS NOT NULL AND json_deck_data != '' AND json_deck_data != '{}'"

    sections = ["avatar", "spellbook", "atlas", "sideboard"]

    totals = defaultdict(int)  # month -> decks
    per_card = defaultdict(lambda: defaultdict(int))  # card -> month -> decks with it

    conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
    cur = conn.cursor()

    def _process_rows(rows, dual_column=True):
        for row in rows:
            ts = row[-1] or ""
            month = ts[:7]  # "YYYY-MM"
            if len(month) != 7:
                continue

            deck_jsons = []
            if dual_column:
                for deck_str in [row[0], row[1]]:
                    if deck_str and deck_str not in ("", "{}"):
                        try:
                            deck_jsons.append(json.loads(deck_str))
                        except json.JSONDecodeError:
                            pass
            else:
                if row[0] and row[0] not in ("", "{}"):
                    try:
                        deck_jsons.append(json.loads(row[0]))
                    except json.JSONDecodeError:
                        pass

            for deck in deck_jsons:
                if isinstance(deck, list) and len(deck) > 0:
                    deck = deck[0]

                if not isinstance(deck, dict):
                    continue
                totals[month] += 1

                names = set()
                for section in sections:
                    for c in deck.get(section, []) or []:
                        name = c.get("name")
                        if name:
                            names.add(name)
                for name in names:
                    per_card[name][month] += 1

    # match_records (current)
    try:
        cur.execute(f"""
            SELECT json_deck_data_winner, json_deck_data_loser, timestamp
            FROM match_records
            WHERE {deck_where} {source_clause}
        """)
        _process_rows(cur)
    except sqlite3.OperationalError:
        pass

    # match_records_archive
    try:
        cur.execute(f"""
            SELECT json_deck_data_winner, json_deck_data_loser, timestamp
            FROM match_records_archive
            WHERE {deck_where}
        """)
        _process_rows(cur)
    except sqlite3.OperationalError:
        pass

    # solo_match_reports
    try:
        cur.execute(f"""
            SELECT json_deck_data, report_date
            FROM solo_match_reports
            WHERE {solo_deck_where}
        """)
        _process_rows(cur, dual_column=False)
    except sqlite3.OperationalError:
        pass

    conn.close()

    return dict(totals), {name: dict(months) for name, months in per_card.items()}
