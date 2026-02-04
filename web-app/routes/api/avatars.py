"""Avatar API routes."""

import json
import logging
import sqlite3
from collections import Counter
from urllib.parse import unquote

from flask import Blueprint, jsonify

from webapp_config import MATCH_RECORDS_DB_PATH, ALL_CARDS_PATH
from utils.formatting import generate_pseudonym
from utils.auth import is_admin

logger = logging.getLogger(__name__)

avatars_bp = Blueprint("avatars", __name__)


@avatars_bp.route("/avatars")
def get_all_avatars():
    """API endpoint for global avatar stats from all matches with deck data.

    Includes both current event matches and archived matches for lifetime stats.
    """
    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()

        all_rows = []
        use_new_columns = True

        # Query current match_records
        try:
            cur.execute("""
                SELECT
                    json_deck_data_winner,
                    json_deck_data_loser
                FROM match_records
                WHERE (json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{}')
                   OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{}')
            """)
            all_rows.extend(cur.fetchall())
        except sqlite3.OperationalError:
            cur.execute("""
                SELECT
                    CASE WHEN reporter_id = winner_id THEN 1 ELSE 0 END as reporter_won,
                    json_deck_data
                FROM match_records
                WHERE json_deck_data IS NOT NULL AND json_deck_data != '' AND json_deck_data != '{}'
            """)
            all_rows.extend(cur.fetchall())
            use_new_columns = False

        # Also query match_records_archive for lifetime stats
        if use_new_columns:
            try:
                cur.execute("""
                    SELECT
                        json_deck_data_winner,
                        json_deck_data_loser
                    FROM match_records_archive
                    WHERE (json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{}')
                       OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{}')
                """)
                all_rows.extend(cur.fetchall())
            except sqlite3.OperationalError:
                pass  # Archive table may not exist

        rows = all_rows
        conn.close()
    except sqlite3.OperationalError:
        return jsonify([])

    avatar_stats = {}

    if use_new_columns:
        for row in rows:
            winner_deck_data_str = row[0]
            loser_deck_data_str = row[1]

            # Process winner's deck
            if winner_deck_data_str and winner_deck_data_str not in ("", "{}"):
                try:
                    deck_data = json.loads(winner_deck_data_str)
                    avatar = deck_data.get("avatar", [{}])
                    avatar_name = avatar[0].get("name", "Unknown") if avatar else "Unknown"

                    if avatar_name and avatar_name != "Unknown":
                        if avatar_name not in avatar_stats:
                            avatar_stats[avatar_name] = {"wins": 0, "losses": 0}
                        avatar_stats[avatar_name]["wins"] += 1
                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    pass

            # Process loser's deck
            if loser_deck_data_str and loser_deck_data_str not in ("", "{}"):
                try:
                    deck_data = json.loads(loser_deck_data_str)
                    avatar = deck_data.get("avatar", [{}])
                    avatar_name = avatar[0].get("name", "Unknown") if avatar else "Unknown"

                    if avatar_name and avatar_name != "Unknown":
                        if avatar_name not in avatar_stats:
                            avatar_stats[avatar_name] = {"wins": 0, "losses": 0}
                        avatar_stats[avatar_name]["losses"] += 1
                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    pass
    else:
        for row in rows:
            reporter_won = row[0]
            deck_data_str = row[1]

            if not deck_data_str:
                continue

            try:
                deck_data = json.loads(deck_data_str)
                avatar = deck_data.get("avatar", [{}])
                avatar_name = avatar[0].get("name", "Unknown") if avatar else "Unknown"

                if avatar_name == "Unknown" or not avatar_name:
                    continue

                if avatar_name not in avatar_stats:
                    avatar_stats[avatar_name] = {"wins": 0, "losses": 0}

                if reporter_won:
                    avatar_stats[avatar_name]["wins"] += 1
                else:
                    avatar_stats[avatar_name]["losses"] += 1
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                continue

    avatar_list = []
    for name, stats in avatar_stats.items():
        total = stats["wins"] + stats["losses"]
        if total > 0:
            win_rate = stats["wins"] / total * 100
            avatar_list.append({
                "name": name,
                "wins": stats["wins"],
                "losses": stats["losses"],
                "total": total,
                "win_rate": round(win_rate, 1),
            })

    avatar_list.sort(key=lambda x: x["total"], reverse=True)
    return jsonify(avatar_list)


@avatars_bp.route("/avatar/<avatar_name>")
def get_avatar(avatar_name):
    """API endpoint for a specific avatar's stats and match history.

    Includes both current event matches and archived matches for lifetime stats.
    """
    avatar_name = unquote(avatar_name)

    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()

        all_rows = []
        use_new_columns = True

        # Query current match_records
        try:
            cur.execute("""
                SELECT
                    winner_id,
                    winner_display_name,
                    losser_id,
                    losser_display_name,
                    timestamp,
                    winner_elo_change,
                    loser_elo_change,
                    first_player,
                    match_time,
                    json_deck_data_winner,
                    json_deck_data_loser,
                    curiosa_url_winner,
                    curiosa_url_loser,
                    rowid as match_id
                FROM match_records
                WHERE json_deck_data_winner IS NOT NULL OR json_deck_data_loser IS NOT NULL
                ORDER BY timestamp DESC
            """)
            all_rows.extend(cur.fetchall())
        except sqlite3.OperationalError:
            cur.execute("""
                SELECT
                    winner_id,
                    winner_display_name,
                    losser_id,
                    losser_display_name,
                    timestamp,
                    winner_elo_change,
                    loser_elo_change,
                    first_player,
                    match_time,
                    json_deck_data,
                    curiosa_url,
                    rowid as match_id
                FROM match_records
                WHERE json_deck_data IS NOT NULL
                ORDER BY timestamp DESC
            """)
            all_rows.extend(cur.fetchall())
            use_new_columns = False

        # Also query match_records_archive for lifetime stats
        if use_new_columns:
            try:
                cur.execute("""
                    SELECT
                        winner_id,
                        winner_display_name,
                        losser_id,
                        losser_display_name,
                        timestamp,
                        winner_elo_change,
                        loser_elo_change,
                        first_player,
                        match_time,
                        json_deck_data_winner,
                        json_deck_data_loser,
                        curiosa_url_winner,
                        curiosa_url_loser,
                        rowid as match_id
                    FROM match_records_archive
                    WHERE json_deck_data_winner IS NOT NULL OR json_deck_data_loser IS NOT NULL
                    ORDER BY timestamp DESC
                """)
                all_rows.extend(cur.fetchall())
            except sqlite3.OperationalError:
                pass  # Archive table may not exist

        rows = all_rows
        conn.close()
    except sqlite3.OperationalError:
        return jsonify({"error": "Database not found"}), 404

    wins_matches = []
    losses_matches = []
    total_wins = 0
    total_losses = 0

    if use_new_columns:
        for row in rows:
            winner_json = row[9]
            loser_json = row[10]

            avatar_in_winner = False
            if winner_json and winner_json not in ("", "{}"):
                try:
                    deck_data = json.loads(winner_json)
                    if deck_data.get("avatar") and len(deck_data["avatar"]) > 0:
                        if deck_data["avatar"][0].get("name") == avatar_name:
                            avatar_in_winner = True
                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    pass

            avatar_in_loser = False
            if loser_json and loser_json not in ("", "{}"):
                try:
                    deck_data = json.loads(loser_json)
                    if deck_data.get("avatar") and len(deck_data["avatar"]) > 0:
                        if deck_data["avatar"][0].get("name") == avatar_name:
                            avatar_in_loser = True
                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    pass

            match_obj = {
                "match_id": row[13],
                "winner_id": str(row[0]),
                "winner_name": generate_pseudonym(row[0]),
                "loser_id": str(row[2]),
                "loser_name": generate_pseudonym(row[2]),
                "date": row[4],
                "winner_elo_change": row[5] if row[5] else 0,
                "loser_elo_change": row[6] if row[6] else 0,
                "first_player": "Play" if row[7] and "y" in str(row[7]).lower() else "Draw",
                "match_time": row[8] if row[8] else None,
                "winner_deck_url": row[11] if len(row) > 11 else None,
                "loser_deck_url": row[12] if len(row) > 12 else None,
            }

            if avatar_in_winner:
                total_wins += 1
                wins_matches.append(match_obj.copy())

            if avatar_in_loser:
                total_losses += 1
                losses_matches.append(match_obj.copy())
    else:
        for row in rows:
            deck_json = row[9]

            if not deck_json or deck_json in ("", "{}"):
                continue

            try:
                deck_data = json.loads(deck_json)
                if deck_data.get("avatar") and len(deck_data["avatar"]) > 0:
                    if deck_data["avatar"][0].get("name") == avatar_name:
                        match_obj = {
                            "match_id": row[11],
                            "winner_id": str(row[0]),
                            "winner_name": generate_pseudonym(row[0]),
                            "loser_id": str(row[2]),
                            "loser_name": generate_pseudonym(row[2]),
                            "date": row[4],
                            "winner_elo_change": row[5] if row[5] else 0,
                            "loser_elo_change": row[6] if row[6] else 0,
                            "first_player": "Play" if row[7] and "y" in str(row[7]).lower() else "Draw",
                            "match_time": row[8] if row[8] else None,
                            "winner_deck_url": row[10] if len(row) > 10 else None,
                            "loser_deck_url": None,
                        }
                        wins_matches.append(match_obj)
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                continue

    total_matches = total_wins + total_losses
    win_rate = (total_wins / total_matches * 100) if total_matches > 0 else 0

    return jsonify({
        "name": avatar_name,
        "total_matches": total_matches,
        "wins": total_wins,
        "losses": total_losses,
        "win_rate": round(win_rate, 1),
        "wins_matches": wins_matches[:100],
        "losses_matches": losses_matches[:100],
    })


@avatars_bp.route("/avatar/<avatar_name>/deck-composition")
def get_avatar_deck_composition(avatar_name):
    """API endpoint for deck element composition for a specific avatar."""
    if not is_admin():
        return jsonify({"error": "Forbidden"}), 403

    avatar_name = unquote(avatar_name)

    # Load card elements lookup
    card_elements = {}
    try:
        with open(ALL_CARDS_PATH, "r", encoding="utf-8") as f:
            all_cards = json.load(f)
            for card in all_cards:
                name = card.get("name", "")
                elements_str = card.get("elements", "None")
                if name and elements_str and elements_str != "None":
                    card_elements[name.lower()] = set(
                        e.strip() for e in elements_str.split(",") if e.strip()
                    )
    except Exception as e:
        logger.error(f"Failed to load All_Cards_Array.json: {e}")

    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()

        all_rows = []
        use_new_columns = True

        # Query current match_records
        try:
            cur.execute("""
                SELECT json_deck_data_winner, json_deck_data_loser
                FROM match_records
                WHERE (json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{}')
                   OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{}')
            """)
            all_rows.extend(cur.fetchall())
        except sqlite3.OperationalError:
            cur.execute("""
                SELECT json_deck_data
                FROM match_records
                WHERE json_deck_data IS NOT NULL AND json_deck_data != '' AND json_deck_data != '{}'
            """)
            all_rows.extend(cur.fetchall())
            use_new_columns = False

        # Also query match_records_archive for lifetime stats
        if use_new_columns:
            try:
                cur.execute("""
                    SELECT json_deck_data_winner, json_deck_data_loser
                    FROM match_records_archive
                    WHERE (json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{}')
                       OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{}')
                """)
                all_rows.extend(cur.fetchall())
            except sqlite3.OperationalError:
                pass  # Archive table may not exist

        rows = all_rows
        conn.close()
    except sqlite3.OperationalError:
        return jsonify({"error": "Database not found"}), 404

    sections = ["spellbook"]

    def get_deck_elements(deck_json):
        elements = set()
        if not deck_json or deck_json in ("", "{}"):
            return elements
        try:
            deck_data = json.loads(deck_json)
            deck = deck_data[0] if isinstance(deck_data, list) else deck_data
            for sec in sections:
                for card in deck.get(sec, []) or []:
                    card_name = (card.get("name") or "").lower()
                    if card_name in card_elements:
                        elements.update(card_elements[card_name])
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            pass
        return elements

    def get_avatar_from_deck(deck_json):
        if not deck_json or deck_json in ("", "{}"):
            return None
        try:
            deck_data = json.loads(deck_json)
            deck = deck_data[0] if isinstance(deck_data, list) else deck_data
            if deck.get("avatar") and len(deck["avatar"]) > 0:
                return deck["avatar"][0].get("name")
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            pass
        return None

    element_combo_counter = Counter()
    total_decks = 0

    if use_new_columns:
        for row in rows:
            winner_json = row[0]
            loser_json = row[1]

            if winner_json and get_avatar_from_deck(winner_json) == avatar_name:
                elements = get_deck_elements(winner_json)
                if elements:
                    combo = ", ".join(sorted(elements))
                    element_combo_counter[combo] += 1
                    total_decks += 1

            if loser_json and get_avatar_from_deck(loser_json) == avatar_name:
                elements = get_deck_elements(loser_json)
                if elements:
                    combo = ", ".join(sorted(elements))
                    element_combo_counter[combo] += 1
                    total_decks += 1
    else:
        for row in rows:
            deck_json = row[0]
            if get_avatar_from_deck(deck_json) == avatar_name:
                elements = get_deck_elements(deck_json)
                if elements:
                    combo = ", ".join(sorted(elements))
                    element_combo_counter[combo] += 1
                    total_decks += 1

    composition_data = []
    for combo, count in element_combo_counter.most_common():
        percent = (count / total_decks * 100) if total_decks > 0 else 0
        composition_data.append({
            "elements": combo,
            "count": count,
            "percent": round(percent, 1),
        })

    return jsonify({"total_decks": total_decks, "composition": composition_data})


@avatars_bp.route("/list-all-avatars")
def list_all_avatars():
    """API endpoint to list all unique avatar names from match records.

    Includes both current event matches and archived matches for lifetime stats.
    """
    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()

        all_rows = []
        use_new_columns = True

        # Query current match_records
        try:
            cur.execute("""
                SELECT json_deck_data_winner, json_deck_data_loser
                FROM match_records
                WHERE (json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{}')
                   OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{}')
            """)
            all_rows.extend(cur.fetchall())
        except sqlite3.OperationalError:
            cur.execute("""
                SELECT json_deck_data
                FROM match_records
                WHERE json_deck_data IS NOT NULL AND json_deck_data != '' AND json_deck_data != '{}'
            """)
            all_rows.extend(cur.fetchall())
            use_new_columns = False

        # Also query match_records_archive for lifetime stats
        if use_new_columns:
            try:
                cur.execute("""
                    SELECT json_deck_data_winner, json_deck_data_loser
                    FROM match_records_archive
                    WHERE (json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{}')
                       OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{}')
                """)
                all_rows.extend(cur.fetchall())
            except sqlite3.OperationalError:
                pass  # Archive table may not exist

        rows = all_rows
        conn.close()
    except sqlite3.OperationalError:
        return jsonify([])

    avatar_names = set()

    def extract_avatar(deck_json):
        if not deck_json or deck_json in ("", "{}"):
            return None
        try:
            deck_data = json.loads(deck_json)
            if deck_data.get("avatar") and len(deck_data["avatar"]) > 0:
                return deck_data["avatar"][0].get("name")
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            pass
        return None

    if use_new_columns:
        for row in rows:
            name = extract_avatar(row[0])
            if name:
                avatar_names.add(name)
            name = extract_avatar(row[1])
            if name:
                avatar_names.add(name)
    else:
        for row in rows:
            name = extract_avatar(row[0])
            if name:
                avatar_names.add(name)

    return jsonify(sorted(list(avatar_names)))
