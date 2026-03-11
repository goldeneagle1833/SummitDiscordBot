"""Player API routes."""

import json
import logging
import sqlite3

from flask import Blueprint, jsonify, session, request

from webapp_config import MATCH_RECORDS_DB_PATH, ELO_DB_PATH, VALID_API_KEYS
from services.match import MatchService
from utils.auth import is_admin

logger = logging.getLogger(__name__)

players_bp = Blueprint("players", __name__)


def _extract_deck_info(deck_json):
    """Extract avatar name and element list from a deck JSON string."""
    avatar_name = None
    elements = []
    if not deck_json or deck_json in ("{}", ""):
        return avatar_name, elements
    try:
        deck_data = json.loads(deck_json)
        avatar_list = deck_data.get("avatar", [])
        if avatar_list:
            for av in avatar_list:
                if av and av.get("type") == "Avatar" and av.get("name"):
                    avatar_name = av.get("name")
                    break
            if not avatar_name and avatar_list[0] and avatar_list[0].get("name"):
                avatar_name = avatar_list[0].get("name")
        elements_set = set()
        for section in ["spellbook", "sideboard"]:
            for card in deck_data.get(section, []) or []:
                card_elements = card.get("elements", "")
                if card_elements and card_elements != "None":
                    for el in card_elements.split(","):
                        el = el.strip()
                        if el in ("Earth", "Fire", "Water", "Air"):
                            elements_set.add(el)
        elements = sorted(elements_set)
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        pass
    return avatar_name, elements


@players_bp.route("/deck-snapshot/<int:match_id>/<player_id>")
def deck_snapshot(match_id, player_id):
    """Get deck snapshot for a specific player in a match."""
    # Normalize player_id (strip 'google_' prefix for Google OAuth users)
    player_id_str = str(player_id)
    if player_id_str.startswith("google_"):
        player_id = player_id_str[7:]  # Remove 'google_' prefix

    # Normalize logged_in_user_id for comparison
    logged_in_user_id = session.get("user_id")
    if logged_in_user_id is not None:
        logged_in_id_str = str(logged_in_user_id)
        if logged_in_id_str.startswith("google_"):
            logged_in_id_str = logged_in_id_str[7:]  # Remove 'google_' prefix
        is_owner = str(logged_in_id_str) == str(player_id)
    else:
        is_owner = False

    # API key grants access (for server-to-server calls)
    api_key = request.headers.get("X-API-Key")
    if api_key and api_key in VALID_API_KEYS:
        is_owner = True

    # Admins have full access
    if is_admin():
        is_owner = True

    if not is_owner:
        return jsonify({"error": "Unauthorized"}), 403

    try:
        service = MatchService()
        result = service.get_deck_snapshot(match_id, player_id)

        if result is None:
            return jsonify({"error": "Match not found"}), 404

        if "error" in result:
            if "not found" in result["error"].lower():
                return jsonify(result), 404
            return jsonify(result), 400

        return jsonify(result)
    except Exception as e:
        logger.error(f"Error fetching deck snapshot: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@players_bp.route("/player/<player_id>")
def player_api(player_id):
    """Get comprehensive player stats and match history.

    Query parameters:
    - event: Filter by event. Values: 'lifetime' (default), 'current', or event_id (int)
    - source: ELO source filter. Values: 'web', 'bot', or 'auto' (default)
    """
    # Store original player_id (with google_ prefix if present)
    original_player_id = str(player_id)

    # Get source parameter (web, bot, or auto)
    # Default to "bot" for now since all matches are in match_records table
    source = request.args.get("source", "bot")

    # Validate source parameter
    if source not in ("web", "bot"):
        return jsonify({"error": "Invalid source parameter. Must be 'web' or 'bot'"}), 400

    # Normalize player_id for INTEGER-based tables (match_records, overall_standings)
    # Strip 'google_' prefix for these legacy tables
    player_id_normalized = original_player_id
    if original_player_id.startswith("google_"):
        player_id_normalized = original_player_id[7:]  # Remove 'google_' prefix

    # Keep player_id as string to avoid overflow with large Google OAuth IDs
    # SQLite's type affinity will handle string-to-integer comparison automatically
    # Validate that it's numeric (but don't convert to int)
    try:
        int(player_id_normalized)  # Validate numeric format
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid player ID"}), 400

    event_filter = request.args.get("event", "lifetime")

    conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
    cur = conn.cursor()

    # Count matches in both tables to determine available sources
    has_web_matches = False
    has_bot_matches = False

    # Check for web matches (match_reports_web table with TEXT IDs)
    try:
        cur.execute(
            """
            SELECT COUNT(*) FROM match_reports_web
            WHERE winner_id = ? OR losser_id = ?
            """,
            (original_player_id, original_player_id),
        )
        web_count = cur.fetchone()[0]
        has_web_matches = web_count > 0
    except sqlite3.OperationalError:
        # Table may not exist yet
        pass

    # Check for bot matches (match_records table with INTEGER IDs)
    try:
        cur.execute(
            """
            SELECT COUNT(*) FROM match_records
            WHERE winner_id = ? OR losser_id = ?
            """,
            (player_id_normalized, player_id_normalized),
        )
        bot_count = cur.fetchone()[0]
        has_bot_matches = bot_count > 0
    except sqlite3.OperationalError:
        pass

    # Determine which tables to query based on event filter and source
    include_current_matches = True  # From match_records or match_reports_web table
    include_archived_matches = True  # From match_records_archive table
    archive_event_id = None  # Specific event to filter in archive

    if event_filter == "current":
        # Only current event matches (from match_records or match_reports_web table)
        include_archived_matches = False
    elif event_filter != "lifetime":
        # Specific past event - only from archive with that event_id
        try:
            archive_event_id = int(event_filter)
            include_current_matches = False
        except (ValueError, TypeError):
            pass  # Invalid event_id, fall back to lifetime

    rows = []

    # Choose player ID and table based on source
    if source == "web":
        # Use original_player_id (with google_ prefix) for TEXT-based match_reports_web table
        query_player_id = original_player_id
    else:  # bot
        # Use normalized player_id (without google_ prefix) for INTEGER-based match_records table
        query_player_id = player_id_normalized

    # Query current matches if needed
    if include_current_matches and source == "web":
        # Query match_reports_web table (web-based matches)
        try:
            cur.execute(
                """
                SELECT
                    CASE WHEN winner_id = ? THEN 1 ELSE 0 END as did_win,
                    first_player,
                    json_deck_data,
                    match_time,
                    winner_display_name,
                    losser_display_name,
                    timestamp,
                    winner_elo_change,
                    loser_elo_change,
                    curiosa_url,
                    winner_id,
                    losser_id,
                    match_id,
                    json_deck_data_winner,
                    json_deck_data_loser,
                    curiosa_url_winner,
                    curiosa_url_loser,
                    winner_went_first,
                    loser_went_first,
                    match_type
                FROM match_reports_web
                WHERE winner_id = ? OR losser_id = ?
                ORDER BY timestamp DESC
            """,
                (query_player_id, query_player_id, query_player_id),
            )
            rows = cur.fetchall()
        except sqlite3.OperationalError:
            # Table may not exist yet
            rows = []
    elif include_current_matches:
        # Query match_records table (bot-based matches)
        # Try new schema first, fallback to old
        try:
            cur.execute(
                """
                SELECT
                    CASE WHEN winner_id = ? THEN 1 ELSE 0 END as did_win,
                    first_player,
                    json_deck_data,
                    match_time,
                    winner_display_name,
                    losser_display_name,
                    timestamp,
                    winner_elo_change,
                    loser_elo_change,
                    curiosa_url,
                    winner_id,
                    losser_id,
                    rowid as match_id,
                    json_deck_data_winner,
                    json_deck_data_loser,
                    curiosa_url_winner,
                    curiosa_url_loser,
                    winner_went_first,
                    loser_went_first,
                    match_type
                FROM match_records
                WHERE winner_id = ? OR losser_id = ?
                ORDER BY timestamp DESC
            """,
                (query_player_id, query_player_id, query_player_id),
            )
            rows = cur.fetchall()
        except sqlite3.OperationalError:
            # Fallback: try without new columns but with deck columns
            try:
                cur.execute(
                    """
                    SELECT
                        CASE WHEN winner_id = ? THEN 1 ELSE 0 END as did_win,
                        first_player,
                        json_deck_data,
                        match_time,
                        winner_display_name,
                        losser_display_name,
                        timestamp,
                        winner_elo_change,
                        loser_elo_change,
                        curiosa_url,
                        winner_id,
                        losser_id,
                        rowid as match_id,
                        json_deck_data_winner,
                        json_deck_data_loser,
                        curiosa_url_winner,
                        curiosa_url_loser,
                        NULL as winner_went_first,
                        NULL as loser_went_first,
                        NULL as match_type
                    FROM match_records
                    WHERE winner_id = ? OR losser_id = ?
                    ORDER BY timestamp DESC
                """,
                    (query_player_id, query_player_id, query_player_id),
                )
                rows = cur.fetchall()
            except sqlite3.OperationalError:
                # Final fallback: minimal columns for very old schema
                cur.execute(
                    """
                    SELECT
                        CASE WHEN winner_id = ? THEN 1 ELSE 0 END as did_win,
                        first_player,
                        json_deck_data,
                        match_time,
                        winner_display_name,
                        losser_display_name,
                        timestamp,
                        winner_elo_change,
                        loser_elo_change,
                        curiosa_url,
                        winner_id,
                        losser_id,
                        rowid as match_id,
                        NULL as json_deck_data_winner,
                        NULL as json_deck_data_loser,
                        NULL as curiosa_url_winner,
                        NULL as curiosa_url_loser,
                        NULL as winner_went_first,
                        NULL as loser_went_first,
                        NULL as match_type
                    FROM match_records
                    WHERE winner_id = ? OR losser_id = ?
                    ORDER BY timestamp DESC
                """,
                    (query_player_id, query_player_id, query_player_id),
                )
                rows = cur.fetchall()
            rows = cur.fetchall()

    # Also check archive table for historical matches (if needed based on filter)
    # Note: Archive is only available for bot matches (match_records_archive)
    archived_rows = []
    if include_archived_matches and source == "bot":
        # Build the WHERE clause based on event filter
        if archive_event_id is not None:
            event_filter_clause = " AND event_id = ?"
            query_params = (query_player_id, query_player_id, query_player_id, archive_event_id)
        else:
            event_filter_clause = ""
            query_params = (query_player_id, query_player_id, query_player_id)

        try:
            cur.execute(
                f"""
                SELECT
                    CASE WHEN winner_id = ? THEN 1 ELSE 0 END as did_win,
                    first_player,
                    json_deck_data,
                    match_time,
                    winner_display_name,
                    losser_display_name,
                    timestamp,
                    winner_elo_change,
                    loser_elo_change,
                    curiosa_url,
                    winner_id,
                    losser_id,
                    original_match_id as match_id,
                    json_deck_data_winner,
                    json_deck_data_loser,
                    curiosa_url_winner,
                    curiosa_url_loser,
                    winner_went_first,
                    loser_went_first,
                    NULL as match_type
                FROM match_records_archive
                WHERE (winner_id = ? OR losser_id = ?){event_filter_clause}
                ORDER BY timestamp DESC
            """,
                query_params,
            )
            archived_rows = cur.fetchall()
        except sqlite3.OperationalError:
            # Try without new columns
            try:
                cur.execute(
                    f"""
                    SELECT
                        CASE WHEN winner_id = ? THEN 1 ELSE 0 END as did_win,
                        first_player,
                        json_deck_data,
                        match_time,
                        winner_display_name,
                        losser_display_name,
                        timestamp,
                        winner_elo_change,
                        loser_elo_change,
                        curiosa_url,
                        winner_id,
                        losser_id,
                        original_match_id as match_id,
                        json_deck_data_winner,
                        json_deck_data_loser,
                        curiosa_url_winner,
                        curiosa_url_loser,
                        NULL as winner_went_first,
                        NULL as loser_went_first,
                        NULL as match_type
                    FROM match_records_archive
                    WHERE (winner_id = ? OR losser_id = ?){event_filter_clause}
                    ORDER BY timestamp DESC
                """,
                    query_params,
                )
                archived_rows = cur.fetchall()
            except sqlite3.OperationalError:
                pass  # Archive table may not exist

    conn.close()

    # Combine current and archived matches
    rows = list(rows) + list(archived_rows)

    # Get solo match reports (bot-only)
    solo_rows = []
    if source == "bot":
        try:
            solo_conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
            solo_cur = solo_conn.cursor()

            query = """
                SELECT
                    is_winner,
                    first_player,
                    json_deck_data,
                    match_time,
                    CASE WHEN is_winner THEN reporter_name ELSE opponent_name END,
                    CASE WHEN is_winner THEN opponent_name ELSE reporter_name END,
                    report_date,
                    0,
                    0,
                    curiosa_link,
                    CASE WHEN is_winner THEN reporter_id ELSE 0 END,
                    CASE WHEN is_winner THEN 0 ELSE reporter_id END,
                    rowid,
                    CASE WHEN is_winner THEN json_deck_data ELSE NULL END,
                    CASE WHEN is_winner THEN NULL ELSE json_deck_data END,
                    CASE WHEN is_winner THEN curiosa_link ELSE NULL END,
                    CASE WHEN is_winner THEN NULL ELSE curiosa_link END,
                    NULL as winner_went_first,
                    NULL as loser_went_first
                FROM solo_match_reports
                WHERE reporter_id = ?
                ORDER BY report_date DESC
            """
            solo_cur.execute(query, (query_player_id,))
            solo_rows = solo_cur.fetchall()

            solo_conn.close()
        except Exception as e:
            logger.warning(f"Could not fetch solo_match_reports: {e}")

    all_rows = rows + solo_rows

    # Get player ELO and name from ELO database first
    player_elo = 1500
    event_elo = 1500
    rank = 0
    player_name_from_elo = None
    displayed_elo = 1500  # The ELO to display based on filter
    displayed_rank = 0
    paper_elo = 1500  # Always fetch both for toggle
    online_elo = 1500

    try:
        elo_conn = sqlite3.connect(str(ELO_DB_PATH))
        elo_cur = elo_conn.cursor()

        # Choose ELO columns based on source
        if source == "web":
            # Query paper ELO columns (web-based matches)
            try:
                elo_cur.execute(
                    "SELECT paper_elo, user_display_name, paper_event_elo, elo FROM overall_standings WHERE user_id = ?",
                    (player_id_normalized,),
                )
                elo_row = elo_cur.fetchone()
                if elo_row:
                    player_elo = elo_row[0] if elo_row[0] else 1500
                    player_name_from_elo = elo_row[1]
                    event_elo = elo_row[2] if elo_row[2] else 1500
                    paper_elo = player_elo
                    online_elo = elo_row[3] if elo_row[3] else 1500
                    # Calculate rank based on paper_elo
                    elo_cur.execute(
                        "SELECT COUNT(*) FROM overall_standings WHERE paper_elo > ?", (player_elo,)
                    )
                    rank = elo_cur.fetchone()[0] + 1
            except sqlite3.OperationalError:
                # paper_elo column may not exist, fall back to elo
                elo_cur.execute(
                    "SELECT elo, user_display_name, event_elo FROM overall_standings WHERE user_id = ?",
                    (player_id_normalized,),
                )
                elo_row = elo_cur.fetchone()
                if elo_row:
                    player_elo = elo_row[0]
                    player_name_from_elo = elo_row[1]
                    event_elo = elo_row[2] if elo_row[2] else 1500
                    online_elo = player_elo
                    elo_cur.execute(
                        "SELECT COUNT(*) FROM overall_standings WHERE elo > ?", (player_elo,)
                    )
                    rank = elo_cur.fetchone()[0] + 1
        else:  # bot
            # Query legacy ELO columns (bot-based matches)
            elo_cur.execute(
                "SELECT elo, user_display_name, event_elo, paper_elo FROM overall_standings WHERE user_id = ?",
                (player_id_normalized,),
            )
            elo_row = elo_cur.fetchone()
            if elo_row:
                player_elo = elo_row[0]
                player_name_from_elo = elo_row[1]
                event_elo = elo_row[2] if elo_row[2] else 1500
                online_elo = player_elo
                paper_elo = elo_row[3] if len(elo_row) > 3 and elo_row[3] else 1500
                elo_cur.execute(
                    "SELECT COUNT(*) FROM overall_standings WHERE elo > ?", (player_elo,)
                )
                rank = elo_cur.fetchone()[0] + 1

        # Determine displayed ELO/rank based on filter
        if event_filter == "lifetime":
            displayed_elo = player_elo
            displayed_rank = rank
        elif event_filter == "current":
            displayed_elo = event_elo
            # For current event, calculate rank among event participants
            try:
                if source == "web":
                    elo_cur.execute(
                        "SELECT COUNT(*) FROM overall_standings WHERE paper_event_elo > ? AND paper_event_elo != 1500",
                        (event_elo,),
                    )
                else:
                    elo_cur.execute(
                        "SELECT COUNT(*) FROM overall_standings WHERE event_elo > ? AND event_elo != 1500",
                        (event_elo,),
                    )
                displayed_rank = elo_cur.fetchone()[0] + 1
            except sqlite3.OperationalError:
                displayed_rank = 0
        elif archive_event_id is not None:
            # Get ELO from archived event standings (bot-only for now)
            try:
                elo_cur.execute(
                    "SELECT final_event_elo, final_rank FROM event_standings_archive WHERE event_id = ? AND user_id = ?",
                    (archive_event_id, player_id_normalized),
                )
                archive_row = elo_cur.fetchone()
                if archive_row:
                    displayed_elo = archive_row[0]
                    displayed_rank = archive_row[1]
            except sqlite3.OperationalError:
                pass  # Table may not exist

        elo_conn.close()
    except sqlite3.OperationalError:
        pass

    # Player not found if no matches AND not in ELO database
    if not rows and not solo_rows and not player_name_from_elo:
        return jsonify({"error": "Player not found"}), 404

    # Get player name - prefer from matches, fallback to ELO database
    player_name = None
    if rows:
        first_match = rows[0]
        player_name = first_match[4] if first_match[0] else first_match[5]
    elif solo_rows:
        player_name = solo_rows[0][4]
    elif player_name_from_elo:
        player_name = player_name_from_elo

    # Calculate stats
    total_matches = len(all_rows)
    wins = sum(1 for row in all_rows if row[0])
    losses = total_matches - wins
    win_rate = (wins / total_matches * 100) if total_matches > 0 else 0

    # First player stats (on the play)
    # Only count matches from 2/7/2026 onward (when play/draw tracking became reliable)
    # New columns: winner_went_first (index 17), loser_went_first (index 18)
    # did_win (index 0): 1 if viewed player is winner, 0 if loser
    # timestamp is at index 6
    play_draw_cutoff = "2026-02-07"
    play_draw_rows = [
        row for row in all_rows
        if row[6] and str(row[6]) >= play_draw_cutoff
    ]

    def player_was_on_play(row):
        did_win = row[0]
        # Try new columns first (indices 17 and 18)
        winner_went_first = row[17] if len(row) > 17 else None
        loser_went_first = row[18] if len(row) > 18 else None

        # Use new columns if available
        if winner_went_first is not None or loser_went_first is not None:
            if did_win:
                # Player is the winner - check if winner went first
                return winner_went_first and "y" in str(winner_went_first).lower()
            else:
                # Player is the loser - check if loser went first
                return loser_went_first and "y" in str(loser_went_first).lower()

        # Fallback to old first_player column (for historical data)
        first_player = row[1]
        if not first_player:
            return False
        fp_lower = str(first_player).lower()
        # Winner went first
        if "y" in fp_lower:
            return did_win  # Player was on play only if they won
        else:
            # Loser went first
            return not did_win  # Player was on play only if they lost

    first_player_matches = sum(1 for row in play_draw_rows if player_was_on_play(row))
    first_player_wins = sum(1 for row in play_draw_rows if row[0] and player_was_on_play(row))
    first_player_win_rate = (
        (first_player_wins / first_player_matches * 100)
        if first_player_matches > 0
        else 0
    )

    # On the draw stats
    def player_was_on_draw(row):
        did_win = row[0]
        # Try new columns first (indices 17 and 18)
        winner_went_first = row[17] if len(row) > 17 else None
        loser_went_first = row[18] if len(row) > 18 else None

        # Use new columns if available
        if winner_went_first is not None or loser_went_first is not None:
            if did_win:
                # Player is the winner - on draw if winner did NOT go first
                return winner_went_first and "n" in str(winner_went_first).lower()
            else:
                # Player is the loser - on draw if loser did NOT go first
                return loser_went_first and "n" in str(loser_went_first).lower()

        # Fallback to old first_player column (for historical data)
        first_player = row[1]
        if not first_player:
            return False
        fp_lower = str(first_player).lower()
        # Winner went first
        if "y" in fp_lower:
            return not did_win  # Player was on draw only if they lost
        else:
            # Loser went first
            return did_win  # Player was on draw only if they won

    draw_matches = sum(1 for row in play_draw_rows if player_was_on_draw(row))
    draw_wins = sum(1 for row in play_draw_rows if row[0] and player_was_on_draw(row))
    draw_win_rate = (draw_wins / draw_matches * 100) if draw_matches > 0 else 0

    # Average match time
    match_times = [
        float(row[3])
        for row in all_rows
        if row[3] and str(row[3]).replace(".", "").isdigit()
    ]
    avg_match_time = sum(match_times) / len(match_times) if match_times else 0

    # Avatar stats - only count the main avatar (type: "Avatar"), exclude sideboard
    avatar_stats = {}
    for row in all_rows:
        did_win = row[0]
        winner_json = row[13] if len(row) > 13 else None
        loser_json = row[14] if len(row) > 14 else None

        deck_json = winner_json if did_win else loser_json
        if not deck_json or deck_json == "{}":
            deck_json = row[2]

        if deck_json and deck_json != "{}":
            try:
                deck_data = json.loads(deck_json)
                if not deck_data or not deck_data.get("avatar"):
                    continue

                avatar_list = deck_data.get("avatar", [])
                if not avatar_list:
                    continue

                # Find the main avatar - must have type "Avatar" (not sideboard avatars)
                # For Imposter decks, this ensures we only count Imposter, not the extra avatars
                main_avatar_name = None
                for av in avatar_list:
                    if av and av.get("type") == "Avatar" and av.get("name"):
                        main_avatar_name = av.get("name")
                        break

                # Fallback: if no type field, use first avatar with a name
                if (
                    not main_avatar_name
                    and avatar_list[0]
                    and avatar_list[0].get("name")
                ):
                    main_avatar_name = avatar_list[0].get("name")

                if not main_avatar_name:
                    continue

                if main_avatar_name not in avatar_stats:
                    avatar_stats[main_avatar_name] = {"wins": 0, "losses": 0}

                if did_win:
                    avatar_stats[main_avatar_name]["wins"] += 1
                else:
                    avatar_stats[main_avatar_name]["losses"] += 1
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                continue

    avatar_performance = []
    for name, stats in avatar_stats.items():
        total = stats["wins"] + stats["losses"]
        rate = (stats["wins"] / total * 100) if total > 0 else 0
        avatar_performance.append(
            {
                "name": name,
                "wins": stats["wins"],
                "losses": stats["losses"],
                "win_rate": round(rate, 1),
            }
        )
    avatar_performance.sort(key=lambda x: x["wins"] + x["losses"], reverse=True)

    # Opponent avatar stats - only count main avatar (type: "Avatar"), exclude sideboard
    opponent_avatar_stats = {}
    for row in all_rows:
        did_win = row[0]
        winner_json = row[13] if len(row) > 13 else None
        loser_json = row[14] if len(row) > 14 else None
        opponent_name = row[5] if did_win else row[4]
        opponent_id = row[11] if did_win else row[10] if len(row) > 10 else None

        opponent_avatar_name = None
        opponent_deck_json = loser_json if did_win else winner_json

        if opponent_deck_json and opponent_deck_json != "{}":
            try:
                deck_data = json.loads(opponent_deck_json)
                if deck_data and deck_data.get("avatar"):
                    avatar_list = deck_data.get("avatar", [])
                    # Find the main avatar - must have type "Avatar"
                    for av in avatar_list:
                        if av and av.get("type") == "Avatar" and av.get("name"):
                            opponent_avatar_name = av.get("name")
                            break
                    # Fallback: if no type field, use first avatar with a name
                    if (
                        not opponent_avatar_name
                        and avatar_list
                        and avatar_list[0]
                        and avatar_list[0].get("name")
                    ):
                        opponent_avatar_name = avatar_list[0].get("name")
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                pass

        if not opponent_avatar_name and opponent_name and opponent_id == 0:
            if "Opponent (" in opponent_name:
                try:
                    start = opponent_name.find("(") + 1
                    end = opponent_name.find(")")
                    if start > 0 and end > start:
                        opponent_avatar_name = opponent_name[start:end].strip()
                except (IndexError, ValueError):
                    pass
            else:
                opponent_avatar_name = opponent_name

        if not opponent_avatar_name:
            continue

        if opponent_avatar_name not in opponent_avatar_stats:
            opponent_avatar_stats[opponent_avatar_name] = {"wins": 0, "losses": 0}

        if did_win:
            opponent_avatar_stats[opponent_avatar_name]["wins"] += 1
        else:
            opponent_avatar_stats[opponent_avatar_name]["losses"] += 1

    avatar_matchups = []
    for name, stats in opponent_avatar_stats.items():
        total = stats["wins"] + stats["losses"]
        rate = (stats["wins"] / total * 100) if total > 0 else 0
        avatar_matchups.append(
            {
                "opponent_avatar": name,
                "wins": stats["wins"],
                "losses": stats["losses"],
                "win_rate": round(rate, 1),
                "total_games": total,
            }
        )
    avatar_matchups.sort(key=lambda x: x["total_games"], reverse=True)

    # Check ownership
    # Normalize logged_in_user_id for comparison (strip 'google_' prefix if present)
    logged_in_user_id = session.get("user_id")
    if logged_in_user_id is not None:
        logged_in_id_str = str(logged_in_user_id)
        if logged_in_id_str.startswith("google_"):
            logged_in_id_str = logged_in_id_str[7:]  # Remove 'google_' prefix
        # Compare as strings to avoid overflow with large IDs
        is_owner = logged_in_id_str == str(player_id_normalized)
    else:
        is_owner = False

    # API key grants owner-level access (for server-to-server calls)
    api_key = request.headers.get("X-API-Key")
    if api_key and api_key in VALID_API_KEYS:
        is_owner = True

    # Admins have full access to all player profiles
    if is_admin():
        is_owner = True

    # Build match history with pagination
    match_history = []
    sorted_rows = sorted(rows, key=lambda x: x[6] if x[6] else "", reverse=True)

    # Get pagination parameters
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    # Validate pagination parameters
    page = max(1, page)  # Ensure page is at least 1
    per_page = min(max(10, per_page), 100)  # Limit per_page between 10 and 100

    # Calculate pagination
    total_matches = len(sorted_rows)
    total_pages = (total_matches + per_page - 1) // per_page if total_matches > 0 else 1
    page = min(page, total_pages)  # Ensure page doesn't exceed total pages

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_rows = sorted_rows[start_idx:end_idx]

    for row in paginated_rows:
        did_win = row[0]
        opponent_name = row[5] if did_win else row[4]
        opponent_id = str(row[11]) if did_win else str(row[10])
        elo_change = row[7] if did_win else row[8]

        player_deck_url = None
        opponent_deck_url = None

        winner_deck_url = row[15] if len(row) > 15 else None
        loser_deck_url = row[16] if len(row) > 16 else None
        winner_json = row[13] if len(row) > 13 else None
        loser_json = row[14] if len(row) > 14 else None
        old_curiosa_url = row[9]
        old_json_deck_data = row[2]

        player_deck_url_check = winner_deck_url if did_win else loser_deck_url
        player_deck_json = winner_json if did_win else loser_json

        # Only count deck as submitted if the player-specific columns have data.
        # We intentionally do NOT use old_curiosa_url or old_json_deck_data because
        # those legacy columns belong to whoever reported the match, not necessarily
        # the player being viewed. This prevents showing the opponent's deck submission
        # status on your profile.
        has_deck = False
        has_deck_json = False
        if player_deck_url_check and player_deck_url_check not in (
            "No URL provided",
            "Admin reported match",
            "{}",
            "",
            None,
        ):
            has_deck = True
        if player_deck_json and player_deck_json not in ("{}", "", None):
            has_deck = True
            has_deck_json = True

        # Extract avatar name and deck elements from deck JSON
        player_avatar_name, deck_elements = _extract_deck_info(player_deck_json)

        opponent_deck_json = loser_json if did_win else winner_json
        opponent_avatar_name, opponent_elements = _extract_deck_info(opponent_deck_json)

        if is_owner:
            player_deck_url = winner_deck_url if did_win else loser_deck_url
            opponent_deck_url = loser_deck_url if did_win else winner_deck_url

        # Determine if this player was on the play for this match
        # New columns: winner_went_first (index 17), loser_went_first (index 18)
        winner_went_first = row[17] if len(row) > 17 else None
        loser_went_first = row[18] if len(row) > 18 else None

        if winner_went_first is not None or loser_went_first is not None:
            # Use new explicit columns
            if did_win:
                player_on_play = (
                    winner_went_first and "y" in str(winner_went_first).lower()
                )
            else:
                player_on_play = (
                    loser_went_first and "y" in str(loser_went_first).lower()
                )
        else:
            # Fallback to old first_player column
            first_player_val = row[1]
            if first_player_val:
                fp_lower = str(first_player_val).lower()
                if "y" in fp_lower:
                    # Winner went first
                    player_on_play = did_win
                else:
                    # Loser went first
                    player_on_play = not did_win
            else:
                player_on_play = None

        match_history.append(
            {
                "match_id": row[12],
                "opponent": opponent_name,
                "opponent_id": opponent_id,
                "result": "Win" if did_win else "Loss",
                "elo_change": elo_change if elo_change else 0,
                "date": row[6],
                "first_player": "Play"
                if player_on_play
                else "Draw"
                if player_on_play is False
                else None,
                "match_time": row[3] if row[3] else None,
                "replay_url": row[9] if row[9] else None,
                "player_deck_url": player_deck_url,
                "opponent_deck_url": opponent_deck_url,
                "has_deck": has_deck,
                "has_deck_json": has_deck_json,
                "match_type": row[19] if len(row) > 19 and row[19] else "ranked",
                "player_avatar": player_avatar_name,
                "deck_elements": deck_elements,
                "opponent_avatar": opponent_avatar_name,
                "opponent_elements": opponent_elements,
            }
        )

    # Recent decks (owner only)
    recent_decks = []
    if is_owner:
        seen_urls = set()
        for row in all_rows:
            did_win = row[0]
            winner_deck_url = row[15] if len(row) > 15 else row[9]
            loser_deck_url = row[16] if len(row) > 16 else None
            winner_json = row[13] if len(row) > 13 else row[2]
            loser_json = row[14] if len(row) > 14 else None

            player_deck_url = winner_deck_url if did_win else loser_deck_url
            player_deck_json = winner_json if did_win else loser_json

            if not player_deck_url or player_deck_url in (
                "No URL provided",
                "Admin reported match",
                "{}",
            ):
                continue

            if player_deck_url in seen_urls:
                continue

            seen_urls.add(player_deck_url)

            avatar_name = "Unknown"
            deck_name = "Unnamed Deck"
            if player_deck_json and player_deck_json not in ("", "{}"):
                try:
                    deck_data = json.loads(player_deck_json)
                    if deck_data.get("avatar") and len(deck_data["avatar"]) > 0:
                        avatar_name = deck_data["avatar"][0].get("name", "Unknown")
                    if deck_data.get("name"):
                        deck_name = deck_data["name"]
                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    pass

            recent_decks.append(
                {
                    "url": player_deck_url,
                    "avatar": avatar_name,
                    "deck_name": deck_name,
                    "date": row[6],
                }
            )

            if len(recent_decks) >= 10:
                break

    # Recorded games (owner only)
    recorded_games = []
    sorted_solo_rows = sorted(
        solo_rows, key=lambda x: x[6] if x[6] else "", reverse=True
    )
    for row in sorted_solo_rows[:50]:
        did_win = row[0]
        opponent_name = row[5]
        deck_url = row[9]

        recorded_games.append(
            {
                "report_id": row[12],
                "opponent": opponent_name,
                "result": "Win" if did_win else "Loss",
                "date": row[6],
                "first_player": "Play"
                if row[1] and "y" in str(row[1]).lower()
                else "Draw",
                "match_time": row[3] if row[3] else None,
                "deck_url": deck_url,
            }
        )

    return jsonify(
        {
            "id": player_id_normalized,
            "name": player_name,
            "elo": player_elo,
            "event_elo": event_elo,
            "displayed_elo": displayed_elo,
            "rank": rank,
            "displayed_rank": displayed_rank,
            "event_filter": event_filter,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
            "on_play_wins": first_player_wins,
            "on_play_matches": first_player_matches,
            "on_play_win_rate": round(first_player_win_rate, 1),
            "on_draw_wins": draw_wins,
            "on_draw_matches": draw_matches,
            "on_draw_win_rate": round(draw_win_rate, 1),
            "avg_match_time": round(avg_match_time, 1),
            "avatar_performance": avatar_performance if is_owner else [],
            "avatar_matchups": avatar_matchups if is_owner else [],
            "recent_decks": recent_decks if is_owner else [],
            "matches": match_history,
            "recorded_games": recorded_games if is_owner else [],
            "is_owner": is_owner,
            "pagination": {
                "current_page": page,
                "per_page": per_page,
                "total_matches": total_matches,
                "total_pages": total_pages,
                "has_previous": page > 1,
                "has_next": page < total_pages,
            },
            # Dual ELO system fields
            "elo_source": source,
            "has_web_matches": has_web_matches,
            "has_bot_matches": has_bot_matches,
            "paper_elo": paper_elo,
            "online_elo": online_elo,
        }
    )
