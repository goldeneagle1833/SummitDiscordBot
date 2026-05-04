"""Creator-only API routes for advanced stats."""

import json
import logging
import sqlite3

from flask import Blueprint, jsonify, request

from webapp_config import MATCH_RECORDS_DB_PATH, ALL_CARDS_PATH, ELO_DB_PATH, SEASON_FILTERS
from utils.auth import require_creator
from routes.api.cards import _build_card_image_lookup, _find_card_image, _get_event_date_range

logger = logging.getLogger(__name__)

creator_bp = Blueprint("creator", __name__)


@creator_bp.route("/filters")
@require_creator
def get_creator_filters():
    """Return available past events and sources for the creator page filter dropdown.

    Same format as /api/avatars/filters but excludes active events.
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
            for row in cur.fetchall():
                if bool(row[4]):
                    continue  # Skip active events for creators
                events.append({
                    "event_id": row[0],
                    "event_name": row[1],
                    "start_date": row[2],
                    "end_date": row[3],
                    "is_active": False,
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
@require_creator
def get_creator_popular_cards():
    """Card popularity stats from match_records (same source as live-popular-cards).

    Query params:
    - event: event_id or season filter ID (e.g. "season_gothic_1"). Omit for all data.
    - source: "discord" | "web" | "all" (default: "discord")
    """
    event_filter = request.args.get("event", "all")
    source_filter = request.args.get("source", "discord")

    # Load card metadata
    card_metadata = {}
    try:
        with open(ALL_CARDS_PATH, "r", encoding="utf-8") as f:
            cards_array = json.load(f)
            for card in cards_array:
                card_metadata[card["name"]] = {
                    "type": card.get("guardian", {}).get("type", "Unknown"),
                    "element": card.get("elements", "None"),
                    "rarity": card.get("guardian", {}).get("rarity", "Unknown"),
                    "set": card.get("sets", [{}])[0].get("name", "Unknown") if card.get("sets") else "Unknown",
                }
    except Exception as e:
        logger.error(f"Error loading card pool: {e}")
        return jsonify({"error": "Failed to load card data"}), 500

    # Build source filter clause
    if source_filter == "discord":
        source_clause = "AND (source = 'Discord' OR source IS NULL)"
    elif source_filter == "web":
        source_clause = "AND source != 'Discord' AND source IS NOT NULL"
    else:
        source_clause = ""

    # Build date filter clause from event selection
    date_clause = ""
    date_params = []
    if event_filter and event_filter != "all":
        start_date, end_date = _get_event_date_range(event_filter)
        if start_date and end_date:
            date_clause = "AND timestamp >= ? AND timestamp <= ?"
            date_params = [start_date, end_date]

    all_decks = []
    conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
    cur = conn.cursor()

    # Query match_records
    try:
        cur.execute(f"""
            SELECT json_deck_data_winner, json_deck_data_loser
            FROM match_records
            WHERE ((json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{{}}')
               OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{{}}'))
            {source_clause}
            {date_clause}
        """, date_params)
        for row in cur.fetchall():
            for deck_str in [row[0], row[1]]:
                if deck_str and deck_str not in ("", "{}"):
                    try:
                        all_decks.append(json.loads(deck_str))
                    except json.JSONDecodeError:
                        pass
    except sqlite3.OperationalError as e:
        logger.warning(f"Error querying match_records: {e}")

    # Also query match_records_archive
    try:
        cur.execute(f"""
            SELECT json_deck_data_winner, json_deck_data_loser
            FROM match_records_archive
            WHERE ((json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{{}}')
               OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{{}}'))
            {source_clause}
            {date_clause}
        """, date_params)
        for row in cur.fetchall():
            for deck_str in [row[0], row[1]]:
                if deck_str and deck_str not in ("", "{}"):
                    try:
                        all_decks.append(json.loads(deck_str))
                    except json.JSONDecodeError:
                        pass
    except sqlite3.OperationalError:
        pass

    # Also get solo match reports
    try:
        cur.execute(f"""
            SELECT json_deck_data
            FROM solo_match_reports
            WHERE json_deck_data IS NOT NULL AND json_deck_data != '' AND json_deck_data != '{{}}'
            {source_clause}
            {date_clause}
        """, date_params)
        for row in cur.fetchall():
            if row[0]:
                try:
                    all_decks.append(json.loads(row[0]))
                except json.JSONDecodeError:
                    pass
    except sqlite3.OperationalError:
        pass

    conn.close()

    if not all_decks:
        return jsonify([])

    # Aggregate card stats
    card_stats = {}
    total_decks = len(all_decks)
    sections = ["avatar", "spellbook", "atlas", "sideboard"]

    for deck in all_decks:
        if isinstance(deck, list) and len(deck) > 0:
            deck = deck[0]

        cards_in_deck = set()

        for section in sections:
            for card in deck.get(section, []) or []:
                card_name = card.get("name")
                quantity = card.get("quantity", 1)

                if not card_name:
                    continue

                if card_name not in card_stats:
                    card_stats[card_name] = {"total_count": 0, "decks_with_card": 0}

                card_stats[card_name]["total_count"] += quantity

                if card_name not in cards_in_deck:
                    card_stats[card_name]["decks_with_card"] += 1
                    cards_in_deck.add(card_name)

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
        })

    # Add card images
    card_image_lookup = _build_card_image_lookup()
    for card in card_list:
        card["image"] = _find_card_image(card["name"], card_image_lookup)

    card_list.sort(key=lambda x: (x["percent_of_decks"], x["count"]), reverse=True)

    return jsonify(card_list)
