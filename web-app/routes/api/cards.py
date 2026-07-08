"""Card and element statistics API routes."""

import json
import os
import re
import logging
import sqlite3
from collections import Counter
from pathlib import Path

from flask import Blueprint, jsonify, current_app, request

from webapp_config import MATCH_RECORDS_DB_PATH, ALL_CARDS_PATH, CARD_IMAGES_DIR, ELO_DB_PATH, SEASON_FILTERS
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
        all_files = sorted(os.listdir(CARD_IMAGES_DIR))
        png_files = [f for f in all_files if f.lower().endswith(".png")]
        webp_files = [f for f in all_files if f.lower().endswith(".webp")]
        for filename in png_files + webp_files:
            base = re.sub(r"\.(png|jpg|jpeg|webp)$", "", filename, flags=re.IGNORECASE).lower()
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
    """API endpoint for live card popularity stats from all matches with deck data.

    Supports optional query param: ?source=discord|web (default: discord)
    """
    if not is_admin():
        return jsonify({"error": "Unauthorized"}), 403

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

    all_decks = []
    conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
    cur = conn.cursor()

    use_new_columns = True
    all_rows = []

    # Build source filter clause
    if source_filter == "discord":
        where_clause = "AND (source = 'Discord' OR source IS NULL)"
    elif source_filter == "web":
        where_clause = "AND source != 'Discord' AND source IS NOT NULL"
    else:
        where_clause = ""

    # Query current match_records
    try:
        cur.execute(f"""
            SELECT json_deck_data_winner, json_deck_data_loser
            FROM match_records
            WHERE ((json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{{}}')
               OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{{}}'))
            {where_clause}
        """)
        all_rows.extend(cur.fetchall())
    except sqlite3.OperationalError:
        use_new_columns = False
        cur.execute(f"""
            SELECT json_deck_data
            FROM match_records
            WHERE json_deck_data IS NOT NULL AND json_deck_data != '' AND json_deck_data != '{{}}'
            {where_clause}
        """)
        all_rows.extend(cur.fetchall())

    # Also query match_records_archive for lifetime stats
    if use_new_columns:
        try:
            cur.execute(f"""
                SELECT json_deck_data_winner, json_deck_data_loser
                FROM match_records_archive
                WHERE ((json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{{}}')
                   OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{{}}'))
                {where_clause}
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
        cur.execute(f"""
            SELECT json_deck_data
            FROM solo_match_reports
            WHERE json_deck_data IS NOT NULL AND json_deck_data != '' AND json_deck_data != '{{}}'
            {where_clause}
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


def _get_event_date_range(event_id):
    """Get start/end dates for an event. Returns (start_date, end_date) or (None, None)."""
    # Check season filters first (string IDs like "season_gothic_1")
    if isinstance(event_id, str) and event_id.startswith("season_"):
        for sf in SEASON_FILTERS:
            if sf["id"] == event_id:
                return sf["start_date"], sf["end_date"]
        return None, None

    try:
        conn = sqlite3.connect(str(ELO_DB_PATH))
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'")
        if not cur.fetchone():
            conn.close()
            return None, None
        if event_id == "current":
            cur.execute("SELECT start_date, end_date FROM events WHERE is_active = 1 LIMIT 1")
        else:
            cur.execute("SELECT start_date, end_date FROM events WHERE event_id = ?", (int(event_id),))
        row = cur.fetchone()
        conn.close()
        if row:
            return row[0], row[1]
    except (sqlite3.OperationalError, ValueError) as e:
        logger.warning(f"Could not get event date range: {e}")
    return None, None


@cards_bp.route("/elements/filters")
def get_element_filters():
    """Return available events for element page filtering."""
    events = []
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
                    continue
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

    # Append season date-range filters at the end
    for sf in SEASON_FILTERS:
        events.append({
            "event_id": sf["id"],
            "event_name": sf["name"],
            "start_date": sf["start_date"],
            "end_date": sf["end_date"],
            "is_active": False,
        })

    return jsonify({"events": events})


def _collect_element_rows(cur, source_filter, event_filter):
    """Collect deck data rows for element stats based on source and event filters.

    Returns (rows, use_new_columns).
    """
    all_rows = []
    use_new_columns = True

    deck_where = ("((json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{}')"
                  " OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{}'))")

    if source_filter == "discord":
        source_clause = "AND (source = 'Discord' OR source IS NULL)"
    elif source_filter == "web":
        source_clause = "AND source != 'Discord' AND source IS NOT NULL"
    else:
        source_clause = ""

    # For discord source: use event_id-based filtering on archive (same as avatars)
    if source_filter == "discord":
        if event_filter in ("all", "current"):
            try:
                cur.execute(f"""
                    SELECT json_deck_data_winner, json_deck_data_loser
                    FROM match_records
                    WHERE {deck_where} {source_clause}
                """)
                all_rows.extend(cur.fetchall())
            except sqlite3.OperationalError:
                try:
                    cur.execute("""
                        SELECT
                            CASE WHEN reporter_id = winner_id THEN 1 ELSE 0 END as reporter_won,
                            json_deck_data
                        FROM match_records
                        WHERE json_deck_data IS NOT NULL AND json_deck_data != '' AND json_deck_data != '{}'
                    """)
                    all_rows.extend(cur.fetchall())
                    use_new_columns = False
                except sqlite3.OperationalError:
                    pass

        # Archive: all events or specific past event
        if event_filter == "all" and use_new_columns:
            try:
                cur.execute(f"""
                    SELECT json_deck_data_winner, json_deck_data_loser
                    FROM match_records_archive
                    WHERE {deck_where}
                """)
                all_rows.extend(cur.fetchall())
            except sqlite3.OperationalError:
                pass
        elif event_filter not in ("all", "current") and use_new_columns:
            if isinstance(event_filter, str) and event_filter.startswith("season_"):
                # Season date-range filter - query both tables by timestamp
                start_date, end_date = _get_event_date_range(event_filter)
                if start_date and end_date:
                    try:
                        cur.execute(f"""
                            SELECT json_deck_data_winner, json_deck_data_loser
                            FROM match_records
                            WHERE {deck_where} {source_clause}
                              AND timestamp >= ? AND timestamp <= ?
                        """, (start_date, end_date))
                        all_rows.extend(cur.fetchall())
                    except sqlite3.OperationalError:
                        pass
                    try:
                        cur.execute(f"""
                            SELECT json_deck_data_winner, json_deck_data_loser
                            FROM match_records_archive
                            WHERE {deck_where}
                              AND timestamp >= ? AND timestamp <= ?
                        """, (start_date, end_date))
                        all_rows.extend(cur.fetchall())
                    except sqlite3.OperationalError:
                        pass
            else:
                try:
                    cur.execute(f"""
                        SELECT json_deck_data_winner, json_deck_data_loser
                        FROM match_records_archive
                        WHERE event_id = ?
                          AND {deck_where}
                    """, (int(event_filter),))
                    all_rows.extend(cur.fetchall())
                except (sqlite3.OperationalError, ValueError):
                    pass

    elif source_filter == "web":
        # Web/paper matches - filter by date range for specific events
        event_start, event_end = None, None
        if event_filter not in ("all",):
            event_start, event_end = _get_event_date_range(event_filter)

        params = []
        where_parts = [
            deck_where,
            "source != 'Discord'",
            "source IS NOT NULL",
        ]
        if event_start:
            where_parts.append("timestamp >= ?")
            params.append(event_start)
        if event_end:
            where_parts.append("timestamp <= ?")
            params.append(event_end)

        try:
            query = f"SELECT json_deck_data_winner, json_deck_data_loser FROM match_records WHERE {' AND '.join(where_parts)}"
            cur.execute(query, params)
            all_rows.extend(cur.fetchall())
        except sqlite3.OperationalError:
            pass

    return all_rows, use_new_columns


@cards_bp.route("/elements")
def get_elements():
    """API endpoint for elemental winrates from all matches with deck data.

    Includes both current event matches and archived matches for lifetime stats.
    Supports optional query params:
      ?source=discord|web (default: discord)
      ?event=all|current|<event_id> (default: all)
    """
    source_filter = request.args.get("source", "discord")
    event_filter = request.args.get("event", "all")
    card_elements = _load_card_elements()

    # Only admins can query the active event
    if event_filter == "current" and not is_admin():
        event_filter = "all"

    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()

        rows, use_new_columns = _collect_element_rows(cur, source_filter, event_filter)

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


@cards_bp.route("/card/<card_name>")
def get_card_stats(card_name):
    """API endpoint for individual card detail: metadata + match stats.

    Public endpoint — returns card info from card pool JSON and win/loss stats
    from match history. Stats will be null if the card has no recorded matches.
    """
    from urllib.parse import unquote
    card_name = unquote(card_name)

    card_image_lookup = _build_card_image_lookup()

    # Load card metadata from All_Cards_Array.json
    card_meta = {}
    try:
        with open(ALL_CARDS_PATH, "r", encoding="utf-8") as f:
            all_cards = json.load(f)
            for c in all_cards:
                if c.get("name", "").lower() == card_name.lower():
                    guardian = c.get("guardian", {}) or {}
                    sets = c.get("sets", []) or []
                    card_meta = {
                        "name": c.get("name", card_name),
                        "element": c.get("elements", None),
                        "type": guardian.get("type", None),
                        "rarity": guardian.get("rarity", None),
                        "set": sets[0].get("name") if sets else None,
                        "threshold": guardian.get("threshold", None),
                        "cost": guardian.get("cost", None),
                        "power": guardian.get("power", None),
                        "defense": guardian.get("defense", None),
                        "text": guardian.get("text", None) or guardian.get("rule_text", None),
                    }
                    break
    except Exception as e:
        logger.warning(f"Could not load card metadata for {card_name}: {e}")

    # Gather match stats
    card_stats = {"wins": 0, "losses": 0}
    sections = ["spellbook", "atlas", "sideboard"]

    def process_deck(deck_str, is_winner):
        if not deck_str or deck_str in ("", "{}"):
            return
        try:
            deck_data = json.loads(deck_str)
            deck = deck_data[0] if isinstance(deck_data, list) else deck_data
            for sec in sections:
                for card in deck.get(sec, []) or []:
                    if card.get("name") == card_name:
                        if is_winner:
                            card_stats["wins"] += 1
                        else:
                            card_stats["losses"] += 1
                        return
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            pass

    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()
        deck_where = ("(json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{}')"
                      " OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{}')")
        for table in ("match_records", "match_records_archive"):
            try:
                cur.execute(f"SELECT json_deck_data_winner, json_deck_data_loser FROM {table} WHERE {deck_where}")
                for row in cur.fetchall():
                    process_deck(row[0], is_winner=True)
                    process_deck(row[1], is_winner=False)
            except sqlite3.OperationalError:
                pass
        conn.close()
    except sqlite3.OperationalError:
        pass

    total = card_stats["wins"] + card_stats["losses"]
    image = _find_card_image(card_name, card_image_lookup)

    # Use name from metadata if found (preserves correct casing), else use URL param
    resolved_name = card_meta.get("name", card_name)

    if not card_meta and total == 0:
        return jsonify({"error": f"Card '{card_name}' not found"}), 404

    return jsonify({
        "name": resolved_name,
        "element": card_meta.get("element"),
        "type": card_meta.get("type"),
        "rarity": card_meta.get("rarity"),
        "set": card_meta.get("set"),
        "threshold": card_meta.get("threshold"),
        "cost": card_meta.get("cost"),
        "power": card_meta.get("power"),
        "defense": card_meta.get("defense"),
        "text": card_meta.get("text"),
        "image": image,
        "wins": card_stats["wins"] if total > 0 else None,
        "losses": card_stats["losses"] if total > 0 else None,
        "total_matches": total if total > 0 else None,
        "win_rate": round(card_stats["wins"] / total * 100, 1) if total > 0 else None,
    })


@cards_bp.route("/card/<card_name>/popularity")
def get_card_popularity(card_name):
    """API endpoint for card popularity over time.

    Returns daily counts of how many decks played this card.
    """
    if not is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    from urllib.parse import unquote
    from datetime import datetime, timedelta
    from collections import defaultdict

    card_name = unquote(card_name)

    # Check if database exists
    if not MATCH_RECORDS_DB_PATH.exists():
        logger.warning(f"Database not found at {MATCH_RECORDS_DB_PATH}")
        return jsonify({
            "card_name": card_name,
            "timeline": [],
            "total_days": 0,
        })

    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()

        all_rows = []
        use_new_columns = True

        # Query current match_records with timestamps
        try:
            cur.execute("""
                SELECT json_deck_data_winner, json_deck_data_loser, timestamp
                FROM match_records
                WHERE (json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{}')
                   OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{}')
            """)
            all_rows.extend(cur.fetchall())
        except sqlite3.OperationalError as e:
            logger.warning(f"Failed to query new columns format: {e}")
            try:
                cur.execute("""
                    SELECT json_deck_data, '', timestamp
                    FROM match_records
                    WHERE json_deck_data IS NOT NULL AND json_deck_data != '' AND json_deck_data != '{}'
                """)
                all_rows.extend(cur.fetchall())
                use_new_columns = False
            except sqlite3.OperationalError as e2:
                logger.error(f"Failed to query match_records: {e2}")
                conn.close()
                return jsonify({
                    "card_name": card_name,
                    "timeline": [],
                    "total_days": 0,
                })

        # Also query match_records_archive for historical data
        if use_new_columns:
            try:
                cur.execute("""
                    SELECT json_deck_data_winner, json_deck_data_loser, timestamp
                    FROM match_records_archive
                    WHERE (json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{}')
                       OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' and json_deck_data_loser != '{}')
                """)
                all_rows.extend(cur.fetchall())
            except sqlite3.OperationalError:
                logger.info("Archive table not found or error querying - continuing without archive data")

        rows = all_rows
        conn.close()
    except sqlite3.OperationalError as e:
        logger.error(f"Database error: {e}")
        return jsonify({
            "card_name": card_name,
            "timeline": [],
            "total_days": 0,
        })
    except Exception as e:
        logger.error(f"Unexpected error in get_card_popularity: {e}")
        return jsonify({
            "card_name": card_name,
            "timeline": [],
            "total_days": 0,
        })

    # Count card appearances by date
    daily_counts = defaultdict(int)
    daily_deck_totals = defaultdict(int)
    sections = ["spellbook", "atlas", "sideboard"]

    def has_deck_data(deck_str):
        return deck_str and deck_str not in ("", "{}")

    def check_card_in_deck(deck_str):
        """Check if card is in deck."""
        if not deck_str or deck_str in ("", "{}"):
            return False
        try:
            deck_data = json.loads(deck_str)
            deck = deck_data[0] if isinstance(deck_data, list) else deck_data
            for sec in sections:
                for card in deck.get(sec, []) or []:
                    name = card.get("name")
                    if name and name == card_name:
                        return True
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            pass
        return False

    for row in rows:
        match_date = row[2] if len(row) > 2 else None
        if not match_date:
            continue

        # Parse date (handle various formats)
        try:
            # Try ISO format first
            date_obj = datetime.fromisoformat(match_date.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            try:
                # Try common formats
                date_obj = datetime.strptime(match_date, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    date_obj = datetime.strptime(match_date, "%Y-%m-%d")
                except ValueError:
                    continue

        # Get just the date (no time)
        date_key = date_obj.strftime("%Y-%m-%d")

        # Check both decks if using new columns
        if use_new_columns:
            if has_deck_data(row[0]):
                daily_deck_totals[date_key] += 1
                if check_card_in_deck(row[0]):
                    daily_counts[date_key] += 1
            if has_deck_data(row[1]):
                daily_deck_totals[date_key] += 1
                if check_card_in_deck(row[1]):
                    daily_counts[date_key] += 1
        else:
            if has_deck_data(row[0]):
                daily_deck_totals[date_key] += 1
                if check_card_in_deck(row[0]):
                    daily_counts[date_key] += 1

    # Convert to timeline format (sorted by date)
    timeline = []
    for date_str, count in sorted(daily_counts.items()):
        timeline.append({
            "date": date_str,
            "count": count,
        })

    # Fill in missing dates with 0 counts (for better visualization)
    if timeline:
        start_date = datetime.strptime(timeline[0]["date"], "%Y-%m-%d")
        end_date = datetime.strptime(timeline[-1]["date"], "%Y-%m-%d")

        # Create a complete timeline
        complete_timeline = []
        current_date = start_date
        date_counts = {item["date"]: item["count"] for item in timeline}

        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            complete_timeline.append({
                "date": date_str,
                "count": date_counts.get(date_str, 0),
            })
            current_date += timedelta(days=1)

        timeline = complete_timeline

    # Build daily totals for normalization
    if timeline:
        daily_totals_list = [daily_deck_totals.get(item["date"], 0) for item in timeline]
    else:
        daily_totals_list = []

    return jsonify({
        "card_name": card_name,
        "timeline": timeline,
        "total_days": len(timeline),
        "daily_totals": daily_totals_list,
    })


@cards_bp.route("/cards/popularity")
def get_all_cards_popularity():
    """API endpoint for all cards' popularity over time.

    Returns daily counts for every card in a single response.
    Supports optional query param: ?source=discord|web (default: discord)
    Admin only.
    """
    if not is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    source_filter = request.args.get("source", "discord")

    from datetime import datetime, timedelta
    from collections import defaultdict

    if not MATCH_RECORDS_DB_PATH.exists():
        return jsonify({"cards": {}})

    # Build source filter clause
    if source_filter == "discord":
        where_clause = "AND (source = 'Discord' OR source IS NULL)"
    elif source_filter == "web":
        where_clause = "AND source != 'Discord' AND source IS NOT NULL"
    else:
        where_clause = ""

    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()

        all_rows = []
        use_new_columns = True

        try:
            cur.execute(f"""
                SELECT json_deck_data_winner, json_deck_data_loser, timestamp
                FROM match_records
                WHERE ((json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{{}}')
                   OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{{}}'))
                {where_clause}
            """)
            all_rows.extend(cur.fetchall())
        except sqlite3.OperationalError:
            try:
                cur.execute(f"""
                    SELECT json_deck_data, '', timestamp
                    FROM match_records
                    WHERE json_deck_data IS NOT NULL AND json_deck_data != '' AND json_deck_data != '{{}}'
                    {where_clause}
                """)
                all_rows.extend(cur.fetchall())
                use_new_columns = False
            except sqlite3.OperationalError:
                conn.close()
                return jsonify({"cards": {}})

        if use_new_columns:
            try:
                cur.execute(f"""
                    SELECT json_deck_data_winner, json_deck_data_loser, timestamp
                    FROM match_records_archive
                    WHERE ((json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{{}}')
                       OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{{}}'))
                    {where_clause}
                """)
                all_rows.extend(cur.fetchall())
            except sqlite3.OperationalError:
                pass

        conn.close()
    except sqlite3.OperationalError:
        return jsonify({"cards": {}})

    # {card_name: {date_str: count}}
    card_daily_counts = defaultdict(lambda: defaultdict(int))
    # {date_str: total_decks} for normalization
    daily_deck_totals = defaultdict(int)
    sections = ["spellbook", "atlas", "sideboard"]

    def extract_card_names(deck_str):
        """Extract all unique card names from a deck."""
        if not deck_str or deck_str in ("", "{}"):
            return set()
        try:
            deck_data = json.loads(deck_str)
            deck = deck_data[0] if isinstance(deck_data, list) else deck_data
            names = set()
            for sec in sections:
                for card in deck.get(sec, []) or []:
                    name = card.get("name")
                    if name:
                        names.add(name)
            return names
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            return set()

    def has_deck_data(deck_str):
        """Check if a deck string contains valid data."""
        return deck_str and deck_str not in ("", "{}")

    for row in all_rows:
        match_date = row[2] if len(row) > 2 else None
        if not match_date:
            continue

        try:
            date_obj = datetime.fromisoformat(match_date.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            try:
                date_obj = datetime.strptime(match_date, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    date_obj = datetime.strptime(match_date, "%Y-%m-%d")
                except ValueError:
                    continue

        date_key = date_obj.strftime("%Y-%m-%d")

        if use_new_columns:
            if has_deck_data(row[0]):
                daily_deck_totals[date_key] += 1
                for name in extract_card_names(row[0]):
                    card_daily_counts[name][date_key] += 1
            if has_deck_data(row[1]):
                daily_deck_totals[date_key] += 1
                for name in extract_card_names(row[1]):
                    card_daily_counts[name][date_key] += 1
        else:
            if has_deck_data(row[0]):
                daily_deck_totals[date_key] += 1
                for name in extract_card_names(row[0]):
                    card_daily_counts[name][date_key] += 1

    # Find global date range
    all_dates = set()
    for counts in card_daily_counts.values():
        all_dates.update(counts.keys())

    if not all_dates:
        return jsonify({"cards": {}})

    sorted_dates = sorted(all_dates)
    start_date = datetime.strptime(sorted_dates[0], "%Y-%m-%d")
    end_date = datetime.strptime(sorted_dates[-1], "%Y-%m-%d")

    complete_dates = []
    current_date = start_date
    while current_date <= end_date:
        complete_dates.append(current_date.strftime("%Y-%m-%d"))
        current_date += timedelta(days=1)

    # Build response per card
    result = {}
    for card_name, daily in card_daily_counts.items():
        timeline = [{"date": d, "count": daily.get(d, 0)} for d in complete_dates]
        result[card_name] = timeline

    # Build daily totals for normalization
    totals = [daily_deck_totals.get(d, 0) for d in complete_dates]

    return jsonify({"cards": result, "dates": complete_dates, "daily_totals": totals})


@cards_bp.route("/deck-composition")
def get_deck_composition():
    """API endpoint for deck element composition across all decks.

    Includes both current event matches and archived matches for lifetime stats.
    Supports optional query params:
      ?source=discord|web (default: discord)
      ?event=all|current|<event_id> (default: all)
    """
    if not is_admin():
        return jsonify({"error": "Forbidden"}), 403

    source_filter = request.args.get("source", "discord")
    event_filter = request.args.get("event", "all")
    card_elements = _load_card_elements()

    # Only admins can query the active event
    if event_filter == "current" and not is_admin():
        event_filter = "all"

    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()

        rows, use_new_columns = _collect_element_rows(cur, source_filter, event_filter)

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
