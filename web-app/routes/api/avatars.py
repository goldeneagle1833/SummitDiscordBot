"""Avatar API routes."""

import json
import logging
import os
import sqlite3
from collections import Counter
from urllib.parse import unquote

from flask import Blueprint, jsonify, request

from webapp_config import MATCH_RECORDS_DB_PATH, ALL_CARDS_PATH, ELO_DB_PATH, SEASON_FILTERS, AVATAR_IMAGES_DIR
from utils.formatting import generate_pseudonym
from utils.auth import is_admin

logger = logging.getLogger(__name__)

avatars_bp = Blueprint("avatars", __name__)


@avatars_bp.route("/avatars/image-files")
def get_avatar_image_files():
    """List available avatar image filenames."""
    if not AVATAR_IMAGES_DIR.exists():
        return jsonify([])
    files = sorted(
        f for f in os.listdir(AVATAR_IMAGES_DIR)
        if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
    )
    return jsonify(files)


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
            user_admin = is_admin()
            for row in cur.fetchall():
                active = bool(row[4])
                # Only admins can see active events
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

    # Append season date-range filters at the end
    for sf in SEASON_FILTERS:
        events.append({
            "event_id": sf["id"],
            "event_name": sf["name"],
            "start_date": sf["start_date"],
            "end_date": sf["end_date"],
            "is_active": False,
        })

    return jsonify({"events": events, "sources": sources})


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
        if isinstance(event_filter, str) and event_filter.startswith("season_"):
            # Season date-range filter - query both tables by timestamp
            start_date, end_date = _get_event_date_range(event_filter)
            if start_date and end_date:
                deck_where = ("((json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{}')"
                              " OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{}'))")
                try:
                    cur.execute(f"""
                        SELECT json_deck_data_winner, json_deck_data_loser
                        FROM match_records
                        WHERE {deck_where}
                          AND (source = 'Discord' OR source IS NULL)
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


def _collect_discord_rows_with_players(cur, event_filter):
    """Like _collect_discord_rows but also includes player IDs and names.

    Returns (rows, use_new_columns) where rows are tuples of
    (winner_deck_json, loser_deck_json, winner_id, winner_name, loser_id, loser_name).
    """
    all_rows = []
    use_new_columns = True

    deck_where = ("((json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{}')"
                  " OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{}'))")

    if event_filter in ("all", "current"):
        try:
            cur.execute(f"""
                SELECT json_deck_data_winner, json_deck_data_loser,
                       winner_id, winner_display_name, losser_id, losser_display_name
                FROM match_records
                WHERE {deck_where}
                  AND (source = 'Discord' OR source IS NULL)
            """)
            all_rows.extend(cur.fetchall())
        except sqlite3.OperationalError:
            use_new_columns = False
            return all_rows, use_new_columns

    if event_filter == "all" and use_new_columns:
        try:
            cur.execute(f"""
                SELECT json_deck_data_winner, json_deck_data_loser,
                       winner_id, winner_display_name, losser_id, losser_display_name
                FROM match_records_archive
                WHERE {deck_where}
            """)
            all_rows.extend(cur.fetchall())
        except sqlite3.OperationalError:
            logger.info("Archive table not found - continuing without archive data")
    elif event_filter not in ("all", "current") and use_new_columns:
        if isinstance(event_filter, str) and event_filter.startswith("season_"):
            start_date, end_date = _get_event_date_range(event_filter)
            if start_date and end_date:
                for table in ("match_records", "match_records_archive"):
                    try:
                        cur.execute(f"""
                            SELECT json_deck_data_winner, json_deck_data_loser,
                                   winner_id, winner_display_name, losser_id, losser_display_name
                            FROM {table}
                            WHERE {deck_where} AND timestamp >= ? AND timestamp <= ?
                              AND (source = 'Discord' OR source IS NULL)
                        """, (start_date, end_date))
                        all_rows.extend(cur.fetchall())
                    except sqlite3.OperationalError:
                        pass
        else:
            try:
                event_id = int(event_filter)
                cur.execute(f"""
                    SELECT json_deck_data_winner, json_deck_data_loser,
                           winner_id, winner_display_name, losser_id, losser_display_name
                    FROM match_records_archive
                    WHERE {deck_where} AND event_id = ?
                """, (event_id,))
                all_rows.extend(cur.fetchall())
            except (ValueError, sqlite3.OperationalError):
                pass

    return all_rows, use_new_columns


def _collect_external_rows_with_players(cur, source_filter, event_start=None, event_end=None):
    """Like _collect_external_rows but also includes player IDs and names."""
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

        query = f"""SELECT json_deck_data_winner, json_deck_data_loser,
                           winner_id, winner_display_name, losser_id, losser_display_name
                    FROM match_records WHERE {' AND '.join(where_parts)}"""
        cur.execute(query, params)
        rows = cur.fetchall()
    except sqlite3.OperationalError as e:
        logger.warning(f"Could not query match_records for external sources: {e}")

    return rows


def _tally_avatar_stats_with_players(rows, use_new_columns, avatar_stats, avatar_player_stats):
    """Process rows with player info into avatar stats and per-avatar player stats.

    Rows are (winner_deck_json, loser_deck_json, winner_id, winner_name, loser_id, loser_name).
    Mutates avatar_stats and avatar_player_stats in place.
    """
    if not use_new_columns:
        return

    for row in rows:
        winner_deck_str, loser_deck_str = row[0], row[1]
        winner_id, winner_name = str(row[2]) if row[2] else None, row[3]
        loser_id, loser_name = str(row[4]) if row[4] else None, row[5]

        name = _extract_avatar_from_deck(winner_deck_str)
        if name:
            if name not in avatar_stats:
                avatar_stats[name] = {"wins": 0, "losses": 0}
            avatar_stats[name]["wins"] += 1
            if winner_id:
                if name not in avatar_player_stats:
                    avatar_player_stats[name] = {}
                if winner_id not in avatar_player_stats[name]:
                    avatar_player_stats[name][winner_id] = {"wins": 0, "losses": 0, "name": winner_name or f"Player {winner_id}"}
                avatar_player_stats[name][winner_id]["wins"] += 1

        name = _extract_avatar_from_deck(loser_deck_str)
        if name:
            if name not in avatar_stats:
                avatar_stats[name] = {"wins": 0, "losses": 0}
            avatar_stats[name]["losses"] += 1
            if loser_id:
                if name not in avatar_player_stats:
                    avatar_player_stats[name] = {}
                if loser_id not in avatar_player_stats[name]:
                    avatar_player_stats[name][loser_id] = {"wins": 0, "losses": 0, "name": loser_name or f"Player {loser_id}"}
                avatar_player_stats[name][loser_id]["losses"] += 1


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

    # Only admins can query the active event
    if event_filter == "current" and not is_admin():
        event_filter = "all"

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
        # Per-avatar per-player stats: {avatar_name: {player_id: {"wins": N, "losses": N, "name": str}}}
        avatar_player_stats = {}

        # Collect Discord bot matches (unless source is a specific external source)
        if source_filter in ("all", "discord"):
            discord_rows, use_new_columns = _collect_discord_rows_with_players(cur, event_filter)
            _tally_avatar_stats_with_players(discord_rows, use_new_columns, avatar_stats, avatar_player_stats)

        # Collect external source matches (unless source is "discord")
        if source_filter != "discord":
            ext_rows = _collect_external_rows_with_players(cur, source_filter, event_start, event_end)
            _tally_avatar_stats_with_players(ext_rows, True, avatar_stats, avatar_player_stats)

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
            entry = {
                "name": name,
                "wins": stats["wins"],
                "losses": stats["losses"],
                "total": total,
                "win_rate": round(win_rate, 1),
            }
            # Find top player by most wins with this avatar
            players = avatar_player_stats.get(name, {})
            if players:
                top = max(players.values(), key=lambda p: (p["wins"], p["wins"] - p["losses"]))
                top_total = top["wins"] + top["losses"]
                entry["top_player"] = {
                    "name": top["name"],
                    "wins": top["wins"],
                    "losses": top["losses"],
                    "total": top_total,
                    "win_rate": round(top["wins"] / top_total * 100, 1) if top_total > 0 else 0,
                }
            avatar_list.append(entry)

    avatar_list.sort(key=lambda x: x["total"], reverse=True)
    return jsonify(avatar_list)


@avatars_bp.route("/avatar/<avatar_name>")
def get_avatar(avatar_name):
    """API endpoint for a specific avatar's stats and match history.

    Includes both current event matches and archived matches for lifetime stats.

    Supports optional query params:
      ?event=all (default) | current | <event_id>
      ?source=all (default) | discord | <source_name>
    """
    avatar_name = unquote(avatar_name)
    event_filter = request.args.get("event", "all")
    source_filter = request.args.get("source", "all")

    # Only admins can query the active event
    if event_filter == "current" and not is_admin():
        event_filter = "all"

    # Determine event date range for external match filtering
    event_start, event_end = None, None
    if event_filter not in ("all",):
        event_start, event_end = _get_event_date_range(event_filter)

    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()

        all_rows = []
        use_new_columns = True

        # Source filter clause for Discord matches
        discord_source_clause = "AND (source = 'Discord' OR source IS NULL)"

        # Query current match_records (Discord matches)
        if source_filter in ("all", "discord"):
            if event_filter in ("all", "current"):
                try:
                    cur.execute(f"""
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
                            rowid as match_id,
                            winner_went_first,
                            loser_went_first
                        FROM match_records
                        WHERE (json_deck_data_winner IS NOT NULL OR json_deck_data_loser IS NOT NULL)
                          {discord_source_clause}
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

            # Query archive for "all" or specific past event
            if use_new_columns:
                if event_filter == "all":
                    try:
                        cur.execute(f"""
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
                                rowid as match_id,
                                COALESCE(winner_went_first, first_player) as winner_went_first,
                                COALESCE(loser_went_first,
                                    CASE WHEN first_player = 'y' THEN 'n'
                                         WHEN first_player = 'n' THEN 'y'
                                         ELSE NULL END) as loser_went_first
                            FROM match_records_archive
                            WHERE json_deck_data_winner IS NOT NULL OR json_deck_data_loser IS NOT NULL
                            ORDER BY timestamp DESC
                        """)
                        all_rows.extend(cur.fetchall())
                    except sqlite3.OperationalError:
                        pass  # Archive table may not exist
                elif event_filter != "current":
                    if isinstance(event_filter, str) and event_filter.startswith("season_"):
                        # Season date-range filter - query both tables by timestamp
                        start_date, end_date = _get_event_date_range(event_filter)
                        if start_date and end_date:
                            select_cols = """
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
                                rowid as match_id,
                                winner_went_first,
                                loser_went_first
                            """
                            try:
                                cur.execute(f"""
                                    SELECT {select_cols}
                                    FROM match_records
                                    WHERE (json_deck_data_winner IS NOT NULL OR json_deck_data_loser IS NOT NULL)
                                      {discord_source_clause}
                                      AND timestamp >= ? AND timestamp <= ?
                                    ORDER BY timestamp DESC
                                """, (start_date, end_date))
                                all_rows.extend(cur.fetchall())
                            except sqlite3.OperationalError:
                                pass
                            try:
                                cur.execute(f"""
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
                                        rowid as match_id,
                                        COALESCE(winner_went_first, first_player) as winner_went_first,
                                        COALESCE(loser_went_first,
                                            CASE WHEN first_player = 'y' THEN 'n'
                                                 WHEN first_player = 'n' THEN 'y'
                                                 ELSE NULL END) as loser_went_first
                                    FROM match_records_archive
                                    WHERE (json_deck_data_winner IS NOT NULL OR json_deck_data_loser IS NOT NULL)
                                      AND timestamp >= ? AND timestamp <= ?
                                    ORDER BY timestamp DESC
                                """, (start_date, end_date))
                                all_rows.extend(cur.fetchall())
                            except sqlite3.OperationalError:
                                pass
                    else:
                        # Specific past event - query archive by event_id
                        try:
                            cur.execute(f"""
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
                                    rowid as match_id,
                                    COALESCE(winner_went_first, first_player) as winner_went_first,
                                    COALESCE(loser_went_first,
                                        CASE WHEN first_player = 'y' THEN 'n'
                                             WHEN first_player = 'n' THEN 'y'
                                             ELSE NULL END) as loser_went_first
                                FROM match_records_archive
                                WHERE (json_deck_data_winner IS NOT NULL OR json_deck_data_loser IS NOT NULL)
                                  AND event_id = ?
                                ORDER BY timestamp DESC
                            """, (int(event_filter),))
                            all_rows.extend(cur.fetchall())
                        except (sqlite3.OperationalError, ValueError):
                            pass

        # Query external source matches (non-Discord)
        if source_filter != "discord" and use_new_columns:
            try:
                params = []
                where_parts = [
                    "(json_deck_data_winner IS NOT NULL OR json_deck_data_loser IS NOT NULL)",
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

                cur.execute(f"""
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
                        rowid as match_id,
                        winner_went_first,
                        loser_went_first
                    FROM match_records
                    WHERE {' AND '.join(where_parts)}
                    ORDER BY timestamp DESC
                """, params)
                all_rows.extend(cur.fetchall())
            except sqlite3.OperationalError as e:
                logger.warning(f"Could not query external sources for avatar: {e}")

        rows = all_rows
        conn.close()
    except sqlite3.OperationalError:
        return jsonify({"error": "Database not found"}), 404

    wins_matches = []
    losses_matches = []
    total_wins = 0
    total_losses = 0

    # Per-player stats tracking: {player_id: {"wins": X, "losses": Y, "name": str}}
    player_stats = {}

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

                # Track per-player stats (winner used this avatar and won)
                pid = str(row[0])
                if pid not in player_stats:
                    player_stats[pid] = {"wins": 0, "losses": 0, "name": row[1]}
                player_stats[pid]["wins"] += 1

                # Track play/draw stats from cutoff date onward
                if row[4] >= cutoff_date:
                    # Use new columns if available, fall back to first_player
                    winner_went_first = row[14] if len(row) > 14 else None
                    loser_went_first = row[15] if len(row) > 15 else None
                    first_player = row[7]

                    # Determine if avatar (winner) was on play using symmetric logic
                    if winner_went_first is not None or loser_went_first is not None:
                        if winner_went_first is not None:
                            winner_on_play = 'y' in str(winner_went_first).lower()
                        elif loser_went_first is not None:
                            # If loser went first ('y'), winner was on draw
                            # If loser went second ('n'), winner was on play
                            winner_on_play = 'y' not in str(loser_went_first).lower()
                        else:
                            winner_on_play = False
                    elif first_player:
                        winner_on_play = 'y' in str(first_player).lower()
                    else:
                        winner_on_play = False

                    if winner_on_play:
                        play_wins += 1
                    else:
                        draw_wins += 1

            if avatar_in_loser:
                total_losses += 1
                losses_matches.append(match_obj.copy())

                # Track per-player stats (loser used this avatar and lost)
                pid = str(row[2])
                if pid not in player_stats:
                    player_stats[pid] = {"wins": 0, "losses": 0, "name": row[3]}
                player_stats[pid]["losses"] += 1

                # Track play/draw stats from cutoff date onward
                if row[4] >= cutoff_date:
                    # Use new columns if available, fall back to first_player
                    winner_went_first = row[14] if len(row) > 14 else None
                    loser_went_first = row[15] if len(row) > 15 else None
                    first_player = row[7]

                    # Determine if avatar (loser) was on play using symmetric logic
                    if winner_went_first is not None or loser_went_first is not None:
                        if loser_went_first is not None:
                            loser_on_play = 'y' in str(loser_went_first).lower()
                        elif winner_went_first is not None:
                            # If winner went first ('y'), loser was on draw
                            # If winner went second ('n'), loser was on play
                            loser_on_play = 'y' not in str(winner_went_first).lower()
                        else:
                            loser_on_play = False
                    elif first_player:
                        # If winner went first ('y'), loser was on draw (not on play)
                        # If winner went second ('n'), loser was on play
                        loser_on_play = 'y' not in str(first_player).lower()
                    else:
                        loser_on_play = False

                    if loser_on_play:
                        play_losses += 1
                    else:
                        draw_losses += 1
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

    result = {
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
    }

    # Include top players per ranking method: accuracy, winrate, total_wins
    if player_stats:
        min_games = 10
        qualified = []
        for pid, stats in player_stats.items():
            total = stats["wins"] + stats["losses"]
            if total >= min_games:
                wr = stats["wins"] / total * 100
                qualified.append({
                    "player_id": pid,
                    "name": stats["name"] or f"Player {pid}",
                    "wins": stats["wins"],
                    "losses": stats["losses"],
                    "total": total,
                    "win_rate": round(wr, 1),
                    "accuracy": round(wr * total, 1)
                })

        if qualified:
            top_by_accuracy = max(qualified, key=lambda p: p["accuracy"])
            top_by_winrate = max(qualified, key=lambda p: (p["win_rate"], p["total"]))
            top_by_wins = max(qualified, key=lambda p: (p["wins"], p["win_rate"]))
            result["top_players"] = {
                "accuracy": top_by_accuracy,
                "winrate": top_by_winrate,
                "total_wins": top_by_wins,
            }

    return jsonify(result)


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


@avatars_bp.route("/avatar/<avatar_name>/elo-matrix")
def get_avatar_elo_matrix(avatar_name):
    """Win rate matrix by ELO bracket for a specific avatar. Admin only.

    Rows = ELO bracket of the player using this avatar.
    Columns = ELO bracket of the opponent.
    Cells = win rate when row-bracket plays against column-bracket.
    """
    if not is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    avatar_name = unquote(avatar_name)
    source = request.args.get("source", "discord")

    if not MATCH_RECORDS_DB_PATH.exists() or not ELO_DB_PATH.exists():
        return jsonify({"avatar_name": avatar_name, "brackets": [], "matrix": []})

    # 1) Load player ELOs from the appropriate standings table
    elo_lookup = {}
    try:
        elo_conn = sqlite3.connect(str(ELO_DB_PATH))
        elo_cur = elo_conn.cursor()
        if source == "web":
            elo_cur.execute("SELECT user_id, paper_elo FROM paper_standings")
        else:
            elo_cur.execute("SELECT user_id, elo FROM overall_standings")
        for row in elo_cur.fetchall():
            elo_lookup[str(row[0])] = row[1] or 1500
        elo_conn.close()
    except sqlite3.OperationalError as e:
        logger.warning(f"Could not load ELO standings: {e}")
        return jsonify({"avatar_name": avatar_name, "brackets": [], "matrix": []})

    # 2) Collect match rows with player IDs and deck data
    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()

        event_filter = request.args.get("event", "all")
        if source in ("all", "discord"):
            rows, use_new = _collect_discord_rows_with_players(cur, event_filter)
        else:
            event_start, event_end = None, None
            if event_filter not in ("all", "current"):
                event_start, event_end = _get_event_date_range(event_filter)
            rows = _collect_external_rows_with_players(cur, source, event_start, event_end)
            use_new = True

        conn.close()
    except sqlite3.OperationalError as e:
        logger.error(f"Database error in elo-matrix: {e}")
        return jsonify({"avatar_name": avatar_name, "brackets": [], "matrix": []})

    if not use_new:
        return jsonify({"avatar_name": avatar_name, "brackets": [], "matrix": []})

    # 3) For each match, check if this avatar was used and record win/loss by ELO bracket pair
    def elo_bracket(elo):
        """Return the lower bound of the 100-point bracket (e.g. 1523 -> 1500)."""
        return (elo // 100) * 100

    # {(player_bracket, opponent_bracket): {"wins": n, "losses": n}}
    bracket_data = {}

    for row in rows:
        winner_deck_str, loser_deck_str = row[0], row[1]
        winner_id = str(row[2]) if row[2] else None
        loser_id = str(row[4]) if row[4] else None

        if not winner_id or not loser_id:
            continue

        winner_elo = elo_lookup.get(winner_id)
        loser_elo = elo_lookup.get(loser_id)
        if winner_elo is None or loser_elo is None:
            continue

        winner_bracket = elo_bracket(winner_elo)
        loser_bracket = elo_bracket(loser_elo)

        # Check if the winner used this avatar
        winner_avatar = _extract_avatar_from_deck(winner_deck_str)
        if winner_avatar and winner_avatar.lower() == avatar_name.lower():
            key = (winner_bracket, loser_bracket)
            if key not in bracket_data:
                bracket_data[key] = {"wins": 0, "losses": 0}
            bracket_data[key]["wins"] += 1

        # Check if the loser used this avatar
        loser_avatar = _extract_avatar_from_deck(loser_deck_str)
        if loser_avatar and loser_avatar.lower() == avatar_name.lower():
            key = (loser_bracket, winner_bracket)
            if key not in bracket_data:
                bracket_data[key] = {"wins": 0, "losses": 0}
            bracket_data[key]["losses"] += 1

    if not bracket_data:
        return jsonify({"avatar_name": avatar_name, "brackets": [], "matrix": []})

    # 4) Determine all brackets that appear and build sorted list
    all_brackets = set()
    for (pb, ob) in bracket_data:
        all_brackets.add(pb)
        all_brackets.add(ob)
    brackets = sorted(all_brackets)

    # 5) Build matrix: rows = player brackets (high to low), cols = opponent brackets
    matrix = []
    for pb in reversed(brackets):
        row_total_wins = 0
        row_total_losses = 0
        cells = []
        for ob in brackets:
            d = bracket_data.get((pb, ob), {"wins": 0, "losses": 0})
            wins, losses = d["wins"], d["losses"]
            total = wins + losses
            wr = round(wins / total * 100, 1) if total > 0 else None
            cells.append({"wins": wins, "losses": losses, "total": total, "win_rate": wr})
            row_total_wins += wins
            row_total_losses += losses
        row_total = row_total_wins + row_total_losses
        row_wr = round(row_total_wins / row_total * 100, 1) if row_total > 0 else None
        matrix.append({
            "player_bracket": pb,
            "cells": cells,
            "total": {"wins": row_total_wins, "losses": row_total_losses, "total": row_total, "win_rate": row_wr},
        })

    return jsonify({
        "avatar_name": avatar_name,
        "brackets": brackets,
        "matrix": matrix,
    })


@avatars_bp.route("/avatars/elo-breakdown")
def get_avatars_elo_breakdown():
    """Cross-avatar win rate breakdown by ELO bracket. Admin only.

    Returns each avatar's overall win rate per player-ELO bracket so admins
    can compare performance across avatars at each skill level.
    """
    if not is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    source = request.args.get("source", "discord")

    if not MATCH_RECORDS_DB_PATH.exists() or not ELO_DB_PATH.exists():
        return jsonify({"brackets": [], "avatars": []})

    # 1) Load player ELOs
    elo_lookup = {}
    try:
        elo_conn = sqlite3.connect(str(ELO_DB_PATH))
        elo_cur = elo_conn.cursor()
        if source == "web":
            elo_cur.execute("SELECT user_id, paper_elo FROM paper_standings")
        else:
            elo_cur.execute("SELECT user_id, elo FROM overall_standings")
        for row in elo_cur.fetchall():
            elo_lookup[str(row[0])] = row[1] or 1500
        elo_conn.close()
    except sqlite3.OperationalError as e:
        logger.warning(f"Could not load ELO standings: {e}")
        return jsonify({"brackets": [], "avatars": []})

    # 2) Collect all match rows with player IDs and deck data
    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()
        if source in ("all", "discord"):
            rows, use_new = _collect_discord_rows_with_players(cur, "all")
        else:
            rows = _collect_external_rows_with_players(cur, source)
            use_new = True
        conn.close()
    except sqlite3.OperationalError as e:
        logger.error(f"Database error in elo-breakdown: {e}")
        return jsonify({"brackets": [], "avatars": []})

    if not use_new:
        return jsonify({"brackets": [], "avatars": []})

    def elo_bracket(elo):
        return (elo // 100) * 100

    # 3) Tally: {avatar_name: {player_bracket: {"wins": n, "losses": n}}}
    avatar_bracket_data = {}

    for row in rows:
        winner_deck_str, loser_deck_str = row[0], row[1]
        winner_id = str(row[2]) if row[2] else None
        loser_id = str(row[4]) if row[4] else None

        if not winner_id or not loser_id:
            continue

        winner_elo = elo_lookup.get(winner_id)
        loser_elo = elo_lookup.get(loser_id)
        if winner_elo is None or loser_elo is None:
            continue

        winner_bracket = elo_bracket(winner_elo)
        loser_bracket = elo_bracket(loser_elo)

        winner_avatar = _extract_avatar_from_deck(winner_deck_str)
        if winner_avatar:
            abd = avatar_bracket_data.setdefault(winner_avatar, {})
            b = abd.setdefault(winner_bracket, {"wins": 0, "losses": 0})
            b["wins"] += 1

        loser_avatar = _extract_avatar_from_deck(loser_deck_str)
        if loser_avatar:
            abd = avatar_bracket_data.setdefault(loser_avatar, {})
            b = abd.setdefault(loser_bracket, {"wins": 0, "losses": 0})
            b["losses"] += 1

    if not avatar_bracket_data:
        return jsonify({"brackets": [], "avatars": []})

    # 4) Determine all brackets
    all_brackets = set()
    for bd in avatar_bracket_data.values():
        all_brackets.update(bd.keys())
    brackets = sorted(all_brackets)

    # 5) Build response per avatar
    min_games = 5
    avatars_result = []
    for avatar_name, bd in sorted(avatar_bracket_data.items()):
        total_wins = sum(d["wins"] for d in bd.values())
        total_losses = sum(d["losses"] for d in bd.values())
        total_games = total_wins + total_losses
        if total_games < 10:
            continue

        bracket_rates = []
        for brk in brackets:
            d = bd.get(brk, {"wins": 0, "losses": 0})
            t = d["wins"] + d["losses"]
            if t >= min_games:
                bracket_rates.append({"wins": d["wins"], "losses": d["losses"], "total": t, "win_rate": round(d["wins"] / t * 100, 1)})
            else:
                bracket_rates.append({"wins": d["wins"], "losses": d["losses"], "total": t, "win_rate": None})

        overall_wr = round(total_wins / total_games * 100, 1) if total_games > 0 else None
        avatars_result.append({
            "name": avatar_name,
            "bracket_rates": bracket_rates,
            "overall": {"wins": total_wins, "losses": total_losses, "total": total_games, "win_rate": overall_wr},
        })

    # 6) Compute per-bracket averages across all avatars (for comparison baseline)
    bracket_avgs = []
    for i, brk in enumerate(brackets):
        rates = [a["bracket_rates"][i]["win_rate"] for a in avatars_result if a["bracket_rates"][i]["win_rate"] is not None]
        bracket_avgs.append(round(sum(rates) / len(rates), 1) if rates else None)

    return jsonify({
        "brackets": brackets,
        "avatars": avatars_result,
        "bracket_averages": bracket_avgs,
    })


@avatars_bp.route("/avatars/elo-breakdown/matches")
def get_elo_breakdown_matches():
    """Return detailed match list for a specific avatar + player ELO bracket cell.

    Query params: avatar, bracket (lower bound e.g. 1500), source (discord/web).
    Admin only.
    """
    if not is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    avatar_name = request.args.get("avatar", "")
    try:
        bracket = int(request.args.get("bracket", "0"))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid bracket"}), 400
    source = request.args.get("source", "discord")

    if not avatar_name:
        return jsonify({"error": "Missing avatar parameter"}), 400

    if not MATCH_RECORDS_DB_PATH.exists() or not ELO_DB_PATH.exists():
        return jsonify({"matches": []})

    # 1) Load player ELOs
    elo_lookup = {}
    try:
        elo_conn = sqlite3.connect(str(ELO_DB_PATH))
        elo_cur = elo_conn.cursor()
        if source == "web":
            elo_cur.execute("SELECT user_id, paper_elo FROM paper_standings")
        else:
            elo_cur.execute("SELECT user_id, elo FROM overall_standings")
        for row in elo_cur.fetchall():
            elo_lookup[str(row[0])] = row[1] or 1500
        elo_conn.close()
    except sqlite3.OperationalError:
        return jsonify({"matches": []})

    def elo_bracket(elo):
        return (elo // 100) * 100

    # 2) Query all matches with full detail
    deck_where = (
        "((json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{}')"
        " OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{}'))"
    )

    all_rows = []
    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()
        source_filter = "(source = 'Discord' OR source IS NULL)" if source in ("all", "discord") else "source = ?"
        params = [] if source in ("all", "discord") else [source]

        for table in ("match_records", "match_records_archive"):
            try:
                # Detect available columns for this table
                cur.execute(f"PRAGMA table_info({table})")
                table_cols = {row[1] for row in cur.fetchall()}

                # Skip tables without new deck columns
                if "json_deck_data_winner" not in table_cols:
                    continue

                base_cols = "rowid, winner_id, losser_id, winner_display_name, losser_display_name, json_deck_data_winner, json_deck_data_loser, curiosa_url_winner, curiosa_url_loser, timestamp"
                optional = [
                    ("final_player1_life", "NULL"),
                    ("final_player2_life", "NULL"),
                    ("winner_went_first", "NULL"),
                    ("loser_went_first", "NULL"),
                    ("match_time", "NULL"),
                    ("winner_elo_change", "NULL"),
                    ("loser_elo_change", "NULL"),
                ]
                extra_cols = ", ".join(
                    col if col in table_cols else f"{fallback} as {col}"
                    for col, fallback in optional
                )

                # Build source filter - handle tables without source column
                if "source" not in table_cols:
                    tbl_source_filter = "1=1"
                    tbl_params = []
                else:
                    tbl_source_filter = source_filter
                    tbl_params = params

                cur.execute(
                    f"SELECT {base_cols}, {extra_cols} FROM {table} WHERE {deck_where} AND {tbl_source_filter}",
                    tbl_params,
                )
                all_rows.extend(cur.fetchall())
            except sqlite3.OperationalError as e:
                logger.warning(f"Could not query {table} for elo-breakdown matches: {e}")
        conn.close()
    except sqlite3.OperationalError:
        return jsonify({"matches": []})

    # 3) Filter to matches where the avatar was used by a player in the target bracket
    matches = []
    for row in all_rows:
        (match_id, winner_id, loser_id, winner_name, loser_name,
         w_deck_json, l_deck_json, w_url, l_url,
         timestamp, _life1, _life2, w_first, l_first, match_time,
         w_elo_change, l_elo_change) = row

        w_id_str = str(winner_id) if winner_id else None
        l_id_str = str(loser_id) if loser_id else None
        if not w_id_str or not l_id_str:
            continue

        w_elo = elo_lookup.get(w_id_str)
        l_elo = elo_lookup.get(l_id_str)
        if w_elo is None or l_elo is None:
            continue

        # Check winner side
        w_avatar = _extract_avatar_from_deck(w_deck_json)
        if w_avatar and w_avatar.lower() == avatar_name.lower() and elo_bracket(w_elo) == bracket:
            l_avatar = _extract_avatar_from_deck(l_deck_json)
            matches.append({
                "match_id": match_id,
                "result": "win",
                "player_name": winner_name,
                "player_id": w_id_str,
                "player_elo": w_elo,
                "player_avatar": w_avatar,
                "player_deck_url": w_url,
                "player_deck_json": w_deck_json or None,
                "opponent_name": loser_name,
                "opponent_id": l_id_str,
                "opponent_elo": l_elo,
                "opponent_avatar": l_avatar,
                "opponent_deck_url": l_url,
                "opponent_deck_json": l_deck_json or None,
                "timestamp": timestamp,
                "went_first": w_first == "y" if w_first else None,
                "match_time": match_time,
                "elo_change": w_elo_change,
            })

        # Check loser side
        l_avatar = _extract_avatar_from_deck(l_deck_json)
        if l_avatar and l_avatar.lower() == avatar_name.lower() and elo_bracket(l_elo) == bracket:
            if not w_avatar:
                w_avatar = _extract_avatar_from_deck(w_deck_json)
            matches.append({
                "match_id": match_id,
                "result": "loss",
                "player_name": loser_name,
                "player_id": l_id_str,
                "player_elo": l_elo,
                "player_avatar": l_avatar,
                "player_deck_url": l_url,
                "player_deck_json": l_deck_json or None,
                "opponent_name": winner_name,
                "opponent_id": w_id_str,
                "opponent_elo": w_elo,
                "opponent_avatar": w_avatar,
                "opponent_deck_url": w_url,
                "opponent_deck_json": w_deck_json or None,
                "timestamp": timestamp,
                "went_first": l_first == "y" if l_first else None,
                "match_time": match_time,
                "elo_change": l_elo_change,
            })

    # Sort by timestamp descending
    matches.sort(key=lambda m: m.get("timestamp") or "", reverse=True)

    return jsonify({
        "avatar": avatar_name,
        "bracket": bracket,
        "matches": matches,
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
        # Use winner_went_first/loser_went_first if available (new records),
        # otherwise derive from first_player (old records)
        try:
            cur.execute("""
                SELECT
                    COALESCE(winner_went_first, first_player) as winner_went_first,
                    COALESCE(loser_went_first,
                        CASE WHEN first_player = 'y' THEN 'n'
                             WHEN first_player = 'n' THEN 'y'
                             ELSE NULL END) as loser_went_first,
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

        # Use new columns if available (derive complementary values to maintain symmetry)
        if winner_went_first is not None or loser_went_first is not None:
            # Determine who went first from whichever column is available
            if winner_went_first is not None:
                winner_on_play = 'y' in str(winner_went_first).lower()
            elif loser_went_first is not None:
                # If loser went first ('y'), winner was on draw (loser_went_first='y' → winner_on_play=False)
                # If loser went second ('n'), winner was on play (loser_went_first='n' → winner_on_play=True)
                winner_on_play = 'y' not in str(loser_went_first).lower()
            else:
                continue  # Skip if both are None

            # Increment symmetrical counters (every win has a corresponding loss)
            if winner_on_play:
                play_wins += 1
                draw_losses += 1
            else:
                draw_wins += 1
                play_losses += 1
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


@avatars_bp.route("/avatar/<avatar_name>/matchups")
def get_avatar_matchups(avatar_name):
    """API endpoint for avatar vs avatar matchup statistics.

    Returns win/loss record and winrate for the specified avatar against all other avatars.

    Supports optional query params:
      ?event=all (default) | current | <event_id>
      ?source=all (default) | discord | <source_name>
    """
    avatar_name = unquote(avatar_name)
    event_filter = request.args.get("event", "all")
    source_filter = request.args.get("source", "all")

    # Only admins can query the active event
    if event_filter == "current" and not is_admin():
        event_filter = "all"

    # Determine event date range for external match filtering
    event_start, event_end = None, None
    if event_filter not in ("all",):
        event_start, event_end = _get_event_date_range(event_filter)

    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()

        all_rows = []
        use_new_columns = True

        # Collect Discord bot matches
        if source_filter in ("all", "discord"):
            discord_rows, use_new_columns = _collect_discord_rows(cur, event_filter)
            all_rows.extend(discord_rows)

        # Collect external source matches
        if source_filter != "discord" and use_new_columns:
            ext_rows = _collect_external_rows(cur, source_filter, event_start, event_end)
            all_rows.extend(ext_rows)

        conn.close()
    except sqlite3.OperationalError:
        return jsonify({"error": "Database not found"}), 404

    # Track matchup stats: {opponent_avatar: {"wins": X, "losses": Y}}
    matchup_stats = {}

    def extract_avatar_name(deck_json):
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
        for row in all_rows:
            winner_avatar = extract_avatar_name(row[0])
            loser_avatar = extract_avatar_name(row[1])

            # Match where our avatar won
            if winner_avatar == avatar_name and loser_avatar and loser_avatar != avatar_name:
                if loser_avatar not in matchup_stats:
                    matchup_stats[loser_avatar] = {"wins": 0, "losses": 0}
                matchup_stats[loser_avatar]["wins"] += 1

            # Match where our avatar lost
            elif loser_avatar == avatar_name and winner_avatar and winner_avatar != avatar_name:
                if winner_avatar not in matchup_stats:
                    matchup_stats[winner_avatar] = {"wins": 0, "losses": 0}
                matchup_stats[winner_avatar]["losses"] += 1
    else:
        # Old schema - can't reliably get opponent avatar without more info
        # Would need to query full match data with both players' decks
        pass

    # Convert to list format with winrate
    # Filter out matchups with less than 10 matches for statistical significance
    matchups = []
    for opponent, stats in matchup_stats.items():
        total = stats["wins"] + stats["losses"]
        if total >= 10:
            win_rate = (stats["wins"] / total) * 100
            matchups.append({
                "opponent": opponent,
                "wins": stats["wins"],
                "losses": stats["losses"],
                "total": total,
                "win_rate": round(win_rate, 1)
            })

    # Sort by total matches (most common matchups first)
    matchups.sort(key=lambda x: x["total"], reverse=True)

    return jsonify({
        "avatar_name": avatar_name,
        "matchups": matchups,
        "total_matchups": len(matchups)
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
