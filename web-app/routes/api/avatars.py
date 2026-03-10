"""Avatar API routes."""

import json
import logging
import sqlite3
from collections import Counter
from urllib.parse import unquote

from flask import Blueprint, jsonify, request

from webapp_config import MATCH_RECORDS_DB_PATH, ALL_CARDS_PATH, ELO_DB_PATH
from utils.formatting import generate_pseudonym
from utils.auth import is_admin

logger = logging.getLogger(__name__)

avatars_bp = Blueprint("avatars", __name__)


@avatars_bp.route("/avatars/filters")
def get_avatar_filters():
    """Return available events and sources for avatar page filtering."""
    events = []
    sources = []

    # Get events from elo.db
    try:
        conn = sqlite3.connect(str(ELO_DB_PATH))
        cur = conn.cursor()
        cur.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='events'
        """)
        if cur.fetchone():
            cur.execute("""
                SELECT event_id, event_name, start_date, end_date, is_active
                FROM events
                ORDER BY start_date DESC
            """)
            for row in cur.fetchall():
                events.append({
                    "event_id": row[0],
                    "event_name": row[1],
                    "start_date": row[2],
                    "end_date": row[3],
                    "is_active": bool(row[4]),
                })
        conn.close()
    except sqlite3.OperationalError as e:
        logger.warning(f"Could not query events: {e}")

    # Get sources from match_records (unified table)
    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT source FROM match_records WHERE source IS NOT NULL ORDER BY source"
        )
        sources = [row[0] for row in cur.fetchall()]
        conn.close()
    except sqlite3.OperationalError as e:
        logger.warning(f"Could not query sources: {e}")

    return jsonify({"events": events, "sources": sources})


def _get_event_date_range(event_id):
    """Get start/end dates for an event. Returns (start_date, end_date) or (None, None)."""
    try:
        conn = sqlite3.connect(str(ELO_DB_PATH))
        cur = conn.cursor()
        cur.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='events'
        """)
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


def _extract_avatar_from_deck(deck_str):
    """Extract avatar name from JSON deck data string."""
    if not deck_str or deck_str in ("", "{}"):
        return None
    try:
        deck_data = json.loads(deck_str)
        avatar = deck_data.get("avatar", [{}])
        name = avatar[0].get("name", "Unknown") if avatar else "Unknown"
        return name if name and name != "Unknown" else None
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        return None


def _collect_discord_rows(cur, event_filter):
    """Collect deck data rows from Discord match tables based on event filter.

    Returns (rows, use_new_columns) where rows are tuples of
    (winner_deck_json, loser_deck_json) for new columns or
    (reporter_won, deck_json) for legacy format.
    """
    all_rows = []
    use_new_columns = True

    if event_filter in ("all", "current"):
        # Query current match_records (Discord-only to avoid double-counting with external)
        try:
            cur.execute("""
                SELECT json_deck_data_winner, json_deck_data_loser
                FROM match_records
                WHERE ((json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{}')
                   OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{}'))
                  AND (source = 'Discord' OR source IS NULL)
            """)
            all_rows.extend(cur.fetchall())
        except sqlite3.OperationalError as e:
            logger.warning(f"Failed to query new columns format: {e}")
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
            except sqlite3.OperationalError as e2:
                logger.error(f"Failed to query match_records: {e2}")

    # Query archive for "all" or specific past event
    if event_filter == "all" and use_new_columns:
        try:
            cur.execute("""
                SELECT json_deck_data_winner, json_deck_data_loser
                FROM match_records_archive
                WHERE (json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{}')
                   OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{}')
            """)
            all_rows.extend(cur.fetchall())
        except sqlite3.OperationalError:
            logger.info("Archive table not found - continuing without archive data")
    elif event_filter not in ("all", "current") and use_new_columns:
        # Specific past event - query archive by event_id
        try:
            cur.execute("""
                SELECT json_deck_data_winner, json_deck_data_loser
                FROM match_records_archive
                WHERE event_id = ?
                  AND ((json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{}')
                    OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{}'))
            """, (int(event_filter),))
            all_rows.extend(cur.fetchall())
        except (sqlite3.OperationalError, ValueError):
            pass

    return all_rows, use_new_columns


def _collect_external_rows(cur, source_filter, event_start=None, event_end=None):
    """Collect deck data rows from match_records for non-Discord sources.

    Returns rows as tuples of (winner_deck_json, loser_deck_json).
    """
    rows = []
    try:
        params = []
        where_parts = [
            "((json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{}')"
            " OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{}'))",
            "source != 'Discord'",
            "source IS NOT NULL",
        ]

        if source_filter not in ("all", "discord"):
            where_parts.append("source = ?")
            params.append(source_filter)

        if event_start:
            where_parts.append("timestamp >= ?")
            params.append(event_start)
        if event_end:
            where_parts.append("timestamp <= ?")
            params.append(event_end)

        query = f"SELECT json_deck_data_winner, json_deck_data_loser FROM match_records WHERE {' AND '.join(where_parts)}"
        cur.execute(query, params)
        rows = cur.fetchall()
    except sqlite3.OperationalError as e:
        logger.warning(f"Could not query match_records for external sources: {e}")

    return rows


def _tally_avatar_stats(rows, use_new_columns=True):
    """Process deck data rows into avatar win/loss stats dict."""
    avatar_stats = {}

    if use_new_columns:
        for row in rows:
            winner_deck_str = row[0]
            loser_deck_str = row[1]

            name = _extract_avatar_from_deck(winner_deck_str)
            if name:
                if name not in avatar_stats:
                    avatar_stats[name] = {"wins": 0, "losses": 0}
                avatar_stats[name]["wins"] += 1

            name = _extract_avatar_from_deck(loser_deck_str)
            if name:
                if name not in avatar_stats:
                    avatar_stats[name] = {"wins": 0, "losses": 0}
                avatar_stats[name]["losses"] += 1
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
                if not avatar_name or avatar_name == "Unknown":
                    continue
                if avatar_name not in avatar_stats:
                    avatar_stats[avatar_name] = {"wins": 0, "losses": 0}
                if reporter_won:
                    avatar_stats[avatar_name]["wins"] += 1
                else:
                    avatar_stats[avatar_name]["losses"] += 1
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                continue

    return avatar_stats


@avatars_bp.route("/avatars")
def get_all_avatars():
    """API endpoint for global avatar stats from all matches with deck data.

    Supports optional query params:
      ?event=all (default) | current | <event_id>
      ?source=all (default) | discord | <source_name>
    """
    event_filter = request.args.get("event", "all")
    source_filter = request.args.get("source", "all")

    if not MATCH_RECORDS_DB_PATH.exists():
        logger.warning(f"Database not found at {MATCH_RECORDS_DB_PATH}")
        return jsonify([])

    # Determine event date range for external match filtering
    event_start, event_end = None, None
    if event_filter not in ("all",):
        event_start, event_end = _get_event_date_range(event_filter)

    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()

        avatar_stats = {}

        # Collect Discord bot matches (unless source is a specific external source)
        if source_filter in ("all", "discord"):
            discord_rows, use_new_columns = _collect_discord_rows(cur, event_filter)
            discord_stats = _tally_avatar_stats(discord_rows, use_new_columns)
            for name, stats in discord_stats.items():
                if name not in avatar_stats:
                    avatar_stats[name] = {"wins": 0, "losses": 0}
                avatar_stats[name]["wins"] += stats["wins"]
                avatar_stats[name]["losses"] += stats["losses"]

        # Collect external source matches (unless source is "discord")
        if source_filter != "discord":
            ext_rows = _collect_external_rows(cur, source_filter, event_start, event_end)
            ext_stats = _tally_avatar_stats(ext_rows, use_new_columns=True)
            for name, stats in ext_stats.items():
                if name not in avatar_stats:
                    avatar_stats[name] = {"wins": 0, "losses": 0}
                avatar_stats[name]["wins"] += stats["wins"]
                avatar_stats[name]["losses"] += stats["losses"]

        conn.close()
    except sqlite3.OperationalError as e:
        logger.error(f"Database error: {e}")
        return jsonify([])
    except Exception as e:
        logger.error(f"Unexpected error in get_all_avatars: {e}")
        return jsonify([])

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

    # Stats for play/draw win rates (from 2/7/2026 onward)
    cutoff_date = "2026-02-07"
    play_wins = 0
    play_losses = 0
    draw_wins = 0
    draw_losses = 0

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

                # Track play/draw stats from cutoff date onward
                if row[4] >= cutoff_date:
                    # Avatar won on the play if first_player is "y" (winner went first)
                    # Avatar won on the draw if first_player is not "y" (winner went second)
                    if row[7] and "y" in str(row[7]).lower():
                        play_wins += 1
                    else:
                        draw_wins += 1

            if avatar_in_loser:
                total_losses += 1
                losses_matches.append(match_obj.copy())

                # Track play/draw stats from cutoff date onward
                if row[4] >= cutoff_date:
                    # Avatar lost on the play if first_player is not "y" (winner went second, loser went first)
                    # Avatar lost on the draw if first_player is "y" (winner went first, loser went second)
                    if row[7] and "y" in str(row[7]).lower():
                        draw_losses += 1
                    else:
                        play_losses += 1
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

                        # Track play/draw stats from cutoff date onward
                        if row[4] >= cutoff_date:
                            if row[7] and "y" in str(row[7]).lower():
                                play_wins += 1
                            else:
                                draw_wins += 1
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                continue

    total_matches = total_wins + total_losses
    win_rate = (total_wins / total_matches * 100) if total_matches > 0 else 0

    # Calculate play/draw win rates (from 2/7/2026 onward)
    play_total = play_wins + play_losses
    draw_total = draw_wins + draw_losses
    play_win_rate = (play_wins / play_total * 100) if play_total > 0 else 0
    draw_win_rate = (draw_wins / draw_total * 100) if draw_total > 0 else 0

    return jsonify({
        "name": avatar_name,
        "total_matches": total_matches,
        "wins": total_wins,
        "losses": total_losses,
        "win_rate": round(win_rate, 1),
        "wins_matches": wins_matches[:100],
        "losses_matches": losses_matches[:100],
        "play_stats": {
            "wins": play_wins,
            "losses": play_losses,
            "total": play_total,
            "win_rate": round(play_win_rate, 1)
        },
        "draw_stats": {
            "wins": draw_wins,
            "losses": draw_losses,
            "total": draw_total,
            "win_rate": round(draw_win_rate, 1)
        }
    })


@avatars_bp.route("/avatar/<avatar_name>/popularity")
def get_avatar_popularity(avatar_name):
    """API endpoint for avatar popularity over time.

    Returns daily counts of how many matches used this avatar.
    """
    if not is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    from datetime import datetime, timedelta
    from collections import defaultdict

    avatar_name = unquote(avatar_name)

    if not MATCH_RECORDS_DB_PATH.exists():
        logger.warning(f"Database not found at {MATCH_RECORDS_DB_PATH}")
        return jsonify({"avatar_name": avatar_name, "timeline": [], "total_days": 0})

    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()

        all_rows = []
        use_new_columns = True

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
                return jsonify({"avatar_name": avatar_name, "timeline": [], "total_days": 0})

        if use_new_columns:
            try:
                cur.execute("""
                    SELECT json_deck_data_winner, json_deck_data_loser, timestamp
                    FROM match_records_archive
                    WHERE (json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{}')
                       OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{}')
                """)
                all_rows.extend(cur.fetchall())
            except sqlite3.OperationalError:
                pass

        conn.close()
    except sqlite3.OperationalError as e:
        logger.error(f"Database error: {e}")
        return jsonify({"avatar_name": avatar_name, "timeline": [], "total_days": 0})

    daily_counts = defaultdict(int)
    daily_deck_totals = defaultdict(int)

    def has_deck_data(deck_str):
        return deck_str and deck_str not in ("", "{}")

    def check_avatar_in_deck(deck_str):
        """Check if avatar matches in deck data."""
        if not deck_str or deck_str in ("", "{}"):
            return False
        try:
            deck_data = json.loads(deck_str)
            deck = deck_data[0] if isinstance(deck_data, list) else deck_data
            avatar = deck.get("avatar", [{}])
            name = avatar[0].get("name", "") if avatar else ""
            return name.lower() == avatar_name.lower()
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            return False

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
                if check_avatar_in_deck(row[0]):
                    daily_counts[date_key] += 1
            if has_deck_data(row[1]):
                daily_deck_totals[date_key] += 1
                if check_avatar_in_deck(row[1]):
                    daily_counts[date_key] += 1
        else:
            if has_deck_data(row[0]):
                daily_deck_totals[date_key] += 1
                if check_avatar_in_deck(row[0]):
                    daily_counts[date_key] += 1

    timeline = []
    for date_str, count in sorted(daily_counts.items()):
        timeline.append({"date": date_str, "count": count})

    if timeline:
        start_date = datetime.strptime(timeline[0]["date"], "%Y-%m-%d")
        end_date = datetime.strptime(timeline[-1]["date"], "%Y-%m-%d")
        complete_timeline = []
        current_date = start_date
        date_counts = {item["date"]: item["count"] for item in timeline}
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            complete_timeline.append({"date": date_str, "count": date_counts.get(date_str, 0)})
            current_date += timedelta(days=1)
        timeline = complete_timeline

    # Build daily totals for normalization
    if timeline:
        daily_totals_list = [daily_deck_totals.get(item["date"], 0) for item in timeline]
    else:
        daily_totals_list = []

    return jsonify({"avatar_name": avatar_name, "timeline": timeline, "total_days": len(timeline), "daily_totals": daily_totals_list})


@avatars_bp.route("/avatars/popularity")
def get_all_avatars_popularity():
    """API endpoint for all avatars' popularity over time.

    Returns daily counts for every avatar in a single response.
    Admin only.
    """
    if not is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    from datetime import datetime, timedelta
    from collections import defaultdict

    if not MATCH_RECORDS_DB_PATH.exists():
        return jsonify({"avatars": {}})

    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()

        all_rows = []
        use_new_columns = True

        try:
            cur.execute("""
                SELECT json_deck_data_winner, json_deck_data_loser, timestamp
                FROM match_records
                WHERE (json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{}')
                   OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{}')
            """)
            all_rows.extend(cur.fetchall())
        except sqlite3.OperationalError:
            try:
                cur.execute("""
                    SELECT json_deck_data, '', timestamp
                    FROM match_records
                    WHERE json_deck_data IS NOT NULL AND json_deck_data != '' AND json_deck_data != '{}'
                """)
                all_rows.extend(cur.fetchall())
                use_new_columns = False
            except sqlite3.OperationalError:
                conn.close()
                return jsonify({"avatars": {}})

        if use_new_columns:
            try:
                cur.execute("""
                    SELECT json_deck_data_winner, json_deck_data_loser, timestamp
                    FROM match_records_archive
                    WHERE (json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{}')
                       OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{}')
                """)
                all_rows.extend(cur.fetchall())
            except sqlite3.OperationalError:
                pass

        conn.close()
    except sqlite3.OperationalError:
        return jsonify({"avatars": {}})

    # {avatar_name: {date_str: count}}
    avatar_daily_counts = defaultdict(lambda: defaultdict(int))
    # {date_str: total_decks} for normalization
    daily_deck_totals = defaultdict(int)

    def extract_avatar_name(deck_str):
        if not deck_str or deck_str in ("", "{}"):
            return None
        try:
            deck_data = json.loads(deck_str)
            deck = deck_data[0] if isinstance(deck_data, list) else deck_data
            avatar = deck.get("avatar", [{}])
            name = avatar[0].get("name", "") if avatar else ""
            return name if name else None
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            return None

    def has_deck_data(deck_str):
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
                name = extract_avatar_name(row[0])
                if name:
                    avatar_daily_counts[name][date_key] += 1
            if has_deck_data(row[1]):
                daily_deck_totals[date_key] += 1
                name = extract_avatar_name(row[1])
                if name:
                    avatar_daily_counts[name][date_key] += 1
        else:
            if has_deck_data(row[0]):
                daily_deck_totals[date_key] += 1
                name = extract_avatar_name(row[0])
                if name:
                    avatar_daily_counts[name][date_key] += 1

    # Find global date range
    all_dates = set()
    for counts in avatar_daily_counts.values():
        all_dates.update(counts.keys())

    if not all_dates:
        return jsonify({"avatars": {}})

    sorted_dates = sorted(all_dates)
    start_date = datetime.strptime(sorted_dates[0], "%Y-%m-%d")
    end_date = datetime.strptime(sorted_dates[-1], "%Y-%m-%d")

    # Build complete date list
    complete_dates = []
    current_date = start_date
    while current_date <= end_date:
        complete_dates.append(current_date.strftime("%Y-%m-%d"))
        current_date += timedelta(days=1)

    # Build response per avatar
    result = {}
    for avatar_name, daily in avatar_daily_counts.items():
        timeline = [{"date": d, "count": daily.get(d, 0)} for d in complete_dates]
        result[avatar_name] = timeline

    # Build daily totals for normalization
    totals = [daily_deck_totals.get(d, 0) for d in complete_dates]

    return jsonify({"avatars": result, "dates": complete_dates, "daily_totals": totals})


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


@avatars_bp.route("/avatars/play-draw-stats")
def get_play_draw_stats():
    """API endpoint for overall on-the-play vs on-the-draw win rates.

    Returns aggregate stats from all matches from 2/7/2026 onward.
    """
    cutoff_date = "2026-02-07"

    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()

        all_rows = []
        use_new_columns = True

        # Query current match_records with date filter
        try:
            cur.execute("""
                SELECT
                    winner_went_first,
                    loser_went_first,
                    first_player,
                    timestamp
                FROM match_records
                WHERE timestamp >= ?
            """, (cutoff_date,))
            all_rows.extend(cur.fetchall())
        except sqlite3.OperationalError:
            # Fallback to old schema
            try:
                cur.execute("""
                    SELECT
                        first_player,
                        NULL as loser_went_first,
                        first_player,
                        timestamp
                    FROM match_records
                    WHERE timestamp >= ?
                """, (cutoff_date,))
                all_rows.extend(cur.fetchall())
                use_new_columns = False
            except sqlite3.OperationalError as e:
                logger.error(f"Failed to query match_records: {e}")
                conn.close()
                return jsonify({"error": "Database error"}), 500

        # Query archive table with date filter
        if use_new_columns:
            try:
                cur.execute("""
                    SELECT
                        winner_went_first,
                        loser_went_first,
                        first_player,
                        timestamp
                    FROM match_records_archive
                    WHERE timestamp >= ?
                """, (cutoff_date,))
                all_rows.extend(cur.fetchall())
            except sqlite3.OperationalError:
                pass  # Archive may not exist

        conn.close()
    except sqlite3.OperationalError as e:
        logger.error(f"Database error: {e}")
        return jsonify({"error": "Database error"}), 500

    # Count play/draw wins and losses
    play_wins = 0
    play_losses = 0
    draw_wins = 0
    draw_losses = 0

    for row in all_rows:
        winner_went_first = row[0] if len(row) > 0 else None
        loser_went_first = row[1] if len(row) > 1 else None
        first_player = row[2] if len(row) > 2 else None

        # Use new columns if available
        if winner_went_first is not None or loser_went_first is not None:
            # Winner on play
            if winner_went_first and "y" in str(winner_went_first).lower():
                play_wins += 1
            # Winner on draw
            elif winner_went_first and "n" in str(winner_went_first).lower():
                draw_wins += 1

            # Loser on play
            if loser_went_first and "y" in str(loser_went_first).lower():
                play_losses += 1
            # Loser on draw
            elif loser_went_first and "n" in str(loser_went_first).lower():
                draw_losses += 1
        # Fallback to old first_player column
        elif first_player:
            fp_lower = str(first_player).lower()
            if "y" in fp_lower:
                # Winner went first
                play_wins += 1
                draw_losses += 1
            else:
                # Loser went first
                play_losses += 1
                draw_wins += 1

    play_total = play_wins + play_losses
    draw_total = draw_wins + draw_losses
    play_win_rate = (play_wins / play_total * 100) if play_total > 0 else 0
    draw_win_rate = (draw_wins / draw_total * 100) if draw_total > 0 else 0

    return jsonify({
        "cutoff_date": cutoff_date,
        "play_stats": {
            "wins": play_wins,
            "losses": play_losses,
            "total": play_total,
            "win_rate": round(play_win_rate, 1)
        },
        "draw_stats": {
            "wins": draw_wins,
            "losses": draw_losses,
            "total": draw_total,
            "win_rate": round(draw_win_rate, 1)
        }
    })


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
