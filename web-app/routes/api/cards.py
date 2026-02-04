"""Card and element statistics API routes."""

import json
import os
import re
import logging
import sqlite3
from collections import Counter
from pathlib import Path

from flask import Blueprint, jsonify, current_app

from webapp_config import MATCH_RECORDS_DB_PATH, ALL_CARDS_PATH, CARD_IMAGES_DIR
from utils.auth import is_admin

logger = logging.getLogger(__name__)

cards_bp = Blueprint("cards", __name__)


def _load_card_elements():
    """Load card name -> element mapping from All_Cards_Array.json."""
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
    return card_elements


def _build_card_image_lookup():
    """Build card name -> image filename lookup."""
    card_image_lookup = {}
    if CARD_IMAGES_DIR.exists():
        for filename in os.listdir(CARD_IMAGES_DIR):
            if not filename.lower().endswith(".png"):
                continue
            base = filename[:-4].lower()
            for suffix in ["-b-s", "-b-f", "-bt-s", "-bt-f", "-scg-f", "-bt-s-r"]:
                if base.endswith(suffix):
                    base = base[:-len(suffix)]
                    break
            if "-" in base:
                card_name_normalized = base.split("-", 1)[1]
                is_standard = "-b-s" in filename.lower() or "-bt-s" in filename.lower()
                if card_name_normalized not in card_image_lookup or is_standard:
                    card_image_lookup[card_name_normalized] = filename
    return card_image_lookup


def _find_card_image(card_name, lookup):
    """Find matching image filename for a card name."""
    normalized = card_name.lower().replace(" ", "_").replace("'", "").replace(",", "")
    normalized = re.sub(r"[^a-z0-9_]", "", normalized)
    return lookup.get(normalized)


@cards_bp.route("/cards")
def get_cards():
    """API endpoint for per-card winrates from all matches with deck data.

    Includes both current event matches and archived matches for lifetime stats.
    """
    if not is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    card_image_lookup = _build_card_image_lookup()

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

    card_stats = {}
    sections = ["spellbook", "atlas", "sideboard"]

    def process_deck(deck_str, is_winner):
        if not deck_str or deck_str in ("", "{}"):
            return
        try:
            deck_data = json.loads(deck_str)
            deck = deck_data[0] if isinstance(deck_data, list) else deck_data
            names = set()
            for sec in sections:
                for card in deck.get(sec, []) or []:
                    name = card.get("name")
                    if name:
                        names.add(name)
                    ctype = card.get("type") or "Unknown"
                    if name:
                        if name not in card_stats:
                            card_stats[name] = {"wins": 0, "losses": 0, "type": ctype}
                        elif not card_stats[name].get("type"):
                            card_stats[name]["type"] = ctype

            for name in names:
                if name not in card_stats:
                    card_stats[name] = {"wins": 0, "losses": 0, "type": "Unknown"}
                if is_winner:
                    card_stats[name]["wins"] += 1
                else:
                    card_stats[name]["losses"] += 1
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            pass

    if use_new_columns:
        for row in rows:
            process_deck(row[0], is_winner=True)
            process_deck(row[1], is_winner=False)
    else:
        for row in rows:
            reporter_won = row[0]
            process_deck(row[1], is_winner=reporter_won)

    card_list = []
    for name, stats in card_stats.items():
        total = stats["wins"] + stats["losses"]
        if total > 0:
            win_rate = stats["wins"] / total * 100
            if win_rate == 100 and total < 10:
                continue
            image = _find_card_image(name, card_image_lookup)
            card_list.append({
                "name": name,
                "wins": stats["wins"],
                "losses": stats["losses"],
                "total": total,
                "win_rate": round(win_rate, 1),
                "type": stats.get("type", "Unknown"),
                "image": image,
            })

    card_list.sort(key=lambda x: (x["win_rate"], x["total"]), reverse=True)
    return jsonify(card_list)


@cards_bp.route("/live-popular-cards")
def get_live_popular_cards():
    """API endpoint for live card popularity stats from all matches with deck data."""
    if not is_admin():
        return jsonify({"error": "Unauthorized"}), 403

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

    all_decks = []
    conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
    cur = conn.cursor()

    use_new_columns = True
    all_rows = []

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
        use_new_columns = False
        cur.execute("""
            SELECT json_deck_data
            FROM match_records
            WHERE json_deck_data IS NOT NULL AND json_deck_data != '' AND json_deck_data != '{}'
        """)
        all_rows.extend(cur.fetchall())

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

    if use_new_columns:
        for row in rows:
            for deck_str in [row[0], row[1]]:
                if deck_str and deck_str not in ("", "{}"):
                    try:
                        all_decks.append(json.loads(deck_str))
                    except json.JSONDecodeError:
                        pass
    else:
        for row in rows:
            if row[0]:
                try:
                    all_decks.append(json.loads(row[0]))
                except json.JSONDecodeError:
                    pass

    # Also get solo match reports
    try:
        cur.execute("""
            SELECT json_deck_data
            FROM solo_match_reports
            WHERE json_deck_data IS NOT NULL AND json_deck_data != '' AND json_deck_data != '{}'
        """)
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

    card_list.sort(key=lambda x: (x["percent_of_decks"], x["count"]), reverse=True)
    return jsonify(card_list)


@cards_bp.route("/elements")
def get_elements():
    """API endpoint for elemental winrates from all matches with deck data.

    Includes both current event matches and archived matches for lifetime stats.
    """
    card_elements = _load_card_elements()

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

    element_stats = {
        "Fire": {"wins": 0, "losses": 0},
        "Water": {"wins": 0, "losses": 0},
        "Earth": {"wins": 0, "losses": 0},
        "Air": {"wins": 0, "losses": 0},
    }
    # Stats for dominant element only (element with most cards)
    dominant_stats = {
        "Fire": {"wins": 0, "losses": 0},
        "Water": {"wins": 0, "losses": 0},
        "Earth": {"wins": 0, "losses": 0},
        "Air": {"wins": 0, "losses": 0},
    }
    # Stats for splash element (element with least cards, excluding mono-element decks)
    splash_stats = {
        "Fire": {"wins": 0, "losses": 0},
        "Water": {"wins": 0, "losses": 0},
        "Earth": {"wins": 0, "losses": 0},
        "Air": {"wins": 0, "losses": 0},
    }
    # Stats for element combinations
    combination_stats = {}  # {"Fire, Water": {"wins": 0, "losses": 0}, ...}

    sections = ["spellbook", "atlas", "sideboard"]
    # For dominant/splash, only count spellbook (no sites)
    spellbook_only = ["spellbook"]

    def get_deck_elements_detailed(deck_json):
        """Returns (elements_set, element_counts, dominant_element, splash_element, combo_key)."""
        elements = set()
        element_counts = Counter()  # For spellbook only (no sites)
        if not deck_json or deck_json in ("", "{}"):
            return elements, element_counts, None, None, None
        try:
            deck_data = json.loads(deck_json)
            deck = deck_data[0] if isinstance(deck_data, list) else deck_data
            # Count all elements for presence tracking
            for sec in sections:
                for card in deck.get(sec, []) or []:
                    card_name = (card.get("name") or "").lower()
                    if card_name in card_elements:
                        elements.update(card_elements[card_name])
            # Count only spellbook for dominant/splash calculation
            for sec in spellbook_only:
                for card in deck.get(sec, []) or []:
                    card_name = (card.get("name") or "").lower()
                    if card_name in card_elements:
                        card_els = card_elements[card_name]
                        qty = card.get("quantity", 1) or 1
                        for el in card_els:
                            element_counts[el] += qty
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            pass

        dominant = element_counts.most_common(1)[0][0] if element_counts else None
        # Splash is the least common element (only if 2+ elements)
        splash = None
        if len(element_counts) >= 2:
            splash = element_counts.most_common()[-1][0]
        # Combo key uses spellbook elements only (no sites)
        spellbook_elements = set(element_counts.keys())
        combo_key = ", ".join(sorted(spellbook_elements)) if spellbook_elements else None
        return elements, element_counts, dominant, splash, combo_key

    def get_deck_elements(deck_json):
        """Legacy function - returns just elements set."""
        elements, _, _, _, _ = get_deck_elements_detailed(deck_json)
        return elements

    def record_stats(deck_json, is_win):
        """Record stats for a deck in all tracking methods."""
        elements, counts, dominant, splash, combo = get_deck_elements_detailed(deck_json)

        # Original: count all elements present
        for element in elements:
            if element in element_stats:
                if is_win:
                    element_stats[element]["wins"] += 1
                else:
                    element_stats[element]["losses"] += 1

        # Dominant element only
        if dominant and dominant in dominant_stats:
            if is_win:
                dominant_stats[dominant]["wins"] += 1
            else:
                dominant_stats[dominant]["losses"] += 1

        # Splash element (least cards, only for multi-element decks)
        if splash and splash in splash_stats:
            if is_win:
                splash_stats[splash]["wins"] += 1
            else:
                splash_stats[splash]["losses"] += 1

        # Element combination
        if combo:
            if combo not in combination_stats:
                combination_stats[combo] = {"wins": 0, "losses": 0}
            if is_win:
                combination_stats[combo]["wins"] += 1
            else:
                combination_stats[combo]["losses"] += 1

    if use_new_columns:
        for row in rows:
            if row[0]:  # winner deck exists
                record_stats(row[0], is_win=True)
            if row[1]:  # loser deck exists
                record_stats(row[1], is_win=False)
    else:
        for row in rows:
            reporter_won = row[0]
            record_stats(row[1], is_win=bool(reporter_won))

    total_wins = sum(stats["wins"] for stats in element_stats.values())
    total_losses = sum(stats["losses"] for stats in element_stats.values())

    element_list = []
    for name in ["Fire", "Water", "Earth", "Air"]:
        stats = element_stats[name]
        total = stats["wins"] + stats["losses"]
        win_rate = (stats["wins"] / total * 100) if total > 0 else 50.0
        win_presence = (stats["wins"] / total_wins * 100) if total_wins > 0 else 0
        loss_presence = (stats["losses"] / total_losses * 100) if total_losses > 0 else 0
        element_list.append({
            "name": name,
            "wins": stats["wins"],
            "losses": stats["losses"],
            "total": total,
            "win_rate": round(win_rate, 1),
            "win_presence": round(win_presence, 1),
            "loss_presence": round(loss_presence, 1),
        })

    # Base response with public data
    response = {"elements": element_list}

    # Build dominant element list (public)
    dominant_list = []
    for name in ["Fire", "Water", "Earth", "Air"]:
        stats = dominant_stats[name]
        total = stats["wins"] + stats["losses"]
        win_rate = (stats["wins"] / total * 100) if total > 0 else 50.0
        dominant_list.append({
            "name": name,
            "wins": stats["wins"],
            "losses": stats["losses"],
            "total": total,
            "win_rate": round(win_rate, 1),
        })
    response["dominant"] = dominant_list

    # Admin-only data: splash element and combinations
    if is_admin():
        # Build splash element list (least common element in multi-element decks)
        splash_list = []
        for name in ["Fire", "Water", "Earth", "Air"]:
            stats = splash_stats[name]
            total = stats["wins"] + stats["losses"]
            win_rate = (stats["wins"] / total * 100) if total > 0 else 50.0
            splash_list.append({
                "name": name,
                "wins": stats["wins"],
                "losses": stats["losses"],
                "total": total,
                "win_rate": round(win_rate, 1),
            })
        response["splash"] = splash_list

        # Build combination list (sorted by total games descending)
        combo_list = []
        for combo, stats in combination_stats.items():
            total = stats["wins"] + stats["losses"]
            if total >= 3:  # Only show combos with at least 3 games
                win_rate = (stats["wins"] / total * 100) if total > 0 else 50.0
                combo_list.append({
                    "name": combo,
                    "wins": stats["wins"],
                    "losses": stats["losses"],
                    "total": total,
                    "win_rate": round(win_rate, 1),
                })
        combo_list.sort(key=lambda x: x["total"], reverse=True)
        response["combinations"] = combo_list

    return jsonify(response)


@cards_bp.route("/deck-composition")
def get_deck_composition():
    """API endpoint for deck element composition across all decks.

    Includes both current event matches and archived matches for lifetime stats.
    """
    if not is_admin():
        return jsonify({"error": "Forbidden"}), 403

    card_elements = _load_card_elements()

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

    element_combo_counter = Counter()
    total_decks = 0

    if use_new_columns:
        for row in rows:
            for deck_json in [row[0], row[1]]:
                if deck_json and deck_json not in ("", "{}"):
                    elements = get_deck_elements(deck_json)
                    if elements:
                        combo = ", ".join(sorted(elements))
                        element_combo_counter[combo] += 1
                        total_decks += 1
    else:
        for row in rows:
            deck_json = row[0]
            if deck_json and deck_json not in ("", "{}"):
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
