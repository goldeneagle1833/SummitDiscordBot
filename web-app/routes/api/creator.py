"""Creator-only API routes for advanced stats."""

import json
import logging
import sqlite3

from flask import Blueprint, jsonify, request

from webapp_config import MATCH_RECORDS_DB_PATH, ALL_CARDS_PATH
from utils.auth import require_creator
from routes.api.cards import _build_card_image_lookup, _find_card_image

logger = logging.getLogger(__name__)

creator_bp = Blueprint("creator", __name__)


def _get_ended_seasons():
    """Get all ended seasons from the seasons table."""
    seasons = []
    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()
        cur.execute("""
            SELECT season_id, title, start_date, end_date
            FROM seasons
            WHERE status = 'ended'
            ORDER BY end_date DESC
        """)
        for row in cur.fetchall():
            seasons.append({
                "id": row[0],
                "name": row[1],
                "start_date": row[2],
                "end_date": row[3],
            })
        conn.close()
    except sqlite3.OperationalError as e:
        logger.warning(f"Error fetching seasons: {e}")
    return seasons


@creator_bp.route("/popular-cards")
@require_creator
def get_creator_popular_cards():
    """Card popularity stats from ended seasons using season_match_elo data.

    Query params:
    - season: season_id (integer). If omitted, uses all ended seasons.
    - source: "discord" | "web" | "all" (default: "all")
    """
    season_id = request.args.get("season", type=int)
    source_filter = request.args.get("source", "all")

    # Get ended season IDs
    ended_seasons = _get_ended_seasons()
    if not ended_seasons:
        return jsonify([])

    ended_ids = [s["id"] for s in ended_seasons]

    if season_id:
        if season_id not in ended_ids:
            return jsonify({"error": "Season not found or still active"}), 404
        season_ids = [season_id]
    else:
        season_ids = ended_ids

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

    # Query season_match_elo for deck data from ended seasons
    placeholders = ",".join("?" * len(season_ids))
    all_decks = []

    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()
        cur.execute(f"""
            SELECT json_deck_data_winner, json_deck_data_loser
            FROM season_match_elo
            WHERE season_id IN ({placeholders})
            AND ((json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{{}}')
               OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{{}}'))
            {source_clause}
        """, season_ids)
        for row in cur.fetchall():
            for deck_str in [row[0], row[1]]:
                if deck_str and deck_str not in ("", "{}"):
                    try:
                        all_decks.append(json.loads(deck_str))
                    except json.JSONDecodeError:
                        pass
        conn.close()
    except sqlite3.OperationalError as e:
        logger.warning(f"Error querying season_match_elo: {e}")

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


@creator_bp.route("/seasons")
@require_creator
def get_creator_seasons():
    """Return ended seasons for the creator page dropdown."""
    return jsonify(_get_ended_seasons())
