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


@players_bp.route("/deck-snapshot/<int:match_id>/<player_id>")
def deck_snapshot(match_id, player_id):
    """Get deck snapshot for a specific player in a match."""
    logged_in_user_id = session.get("user_id")
    is_owner = logged_in_user_id is not None and str(logged_in_user_id) == str(player_id)

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
    """Get comprehensive player stats and match history."""
    conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
    cur = conn.cursor()

    # Try new schema first, fallback to old
    try:
        cur.execute("""
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
                curiosa_url_loser
            FROM match_records
            WHERE winner_id = ? OR losser_id = ?
            ORDER BY timestamp DESC
        """, (player_id, player_id, player_id))
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        cur.execute("""
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
                rowid as match_id
            FROM match_records
            WHERE winner_id = ? OR losser_id = ?
            ORDER BY timestamp DESC
        """, (player_id, player_id, player_id))
        rows = cur.fetchall()

    conn.close()

    # Get solo match reports
    solo_rows = []
    try:
        solo_conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        solo_cur = solo_conn.cursor()

        try:
            player_id_int = int(player_id)
        except (ValueError, TypeError):
            player_id_int = None

        if player_id_int is not None:
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
                    CASE WHEN is_winner THEN NULL ELSE curiosa_link END
                FROM solo_match_reports
                WHERE reporter_id = ?
                ORDER BY report_date DESC
            """
            solo_cur.execute(query, (player_id_int,))
            solo_rows = solo_cur.fetchall()

        solo_conn.close()
    except Exception as e:
        logger.warning(f"Could not fetch solo_match_reports: {e}")

    all_rows = rows + solo_rows

    if not rows and not solo_rows:
        return jsonify({"error": "Player not found"}), 404

    # Get player name
    player_name = None
    if rows:
        first_match = rows[0]
        player_name = first_match[4] if first_match[0] else first_match[5]
    elif solo_rows:
        player_name = solo_rows[0][4]

    # Get player ELO
    player_elo = 1500
    rank = 0
    try:
        elo_conn = sqlite3.connect(str(ELO_DB_PATH))
        elo_cur = elo_conn.cursor()
        elo_cur.execute("SELECT elo FROM overall_standings WHERE user_id = ?", (player_id,))
        elo_row = elo_cur.fetchone()
        if elo_row:
            player_elo = elo_row[0]
            elo_cur.execute("SELECT COUNT(*) FROM overall_standings WHERE elo > ?", (player_elo,))
            rank = elo_cur.fetchone()[0] + 1
        elo_conn.close()
    except sqlite3.OperationalError:
        pass

    # Calculate stats
    total_matches = len(all_rows)
    wins = sum(1 for row in all_rows if row[0])
    losses = total_matches - wins
    win_rate = (wins / total_matches * 100) if total_matches > 0 else 0

    # First player stats
    first_player_matches = sum(1 for row in all_rows if row[1] and "y" in str(row[1]).lower())
    first_player_wins = sum(1 for row in all_rows if row[0] and row[1] and "y" in str(row[1]).lower())
    first_player_win_rate = (first_player_wins / first_player_matches * 100) if first_player_matches > 0 else 0

    # On the draw stats
    draw_matches = sum(1 for row in all_rows if row[1] and "y" not in str(row[1]).lower())
    draw_wins = sum(1 for row in all_rows if row[0] and row[1] and "y" not in str(row[1]).lower())
    draw_win_rate = (draw_wins / draw_matches * 100) if draw_matches > 0 else 0

    # Average match time
    match_times = [float(row[3]) for row in all_rows if row[3] and str(row[3]).replace(".", "").isdigit()]
    avg_match_time = sum(match_times) / len(match_times) if match_times else 0

    # Avatar stats
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

                avatar = deck_data.get("avatar", [])
                if not avatar or not avatar[0] or not avatar[0].get("name"):
                    continue

                avatar_name = avatar[0].get("name")

                if avatar_name not in avatar_stats:
                    avatar_stats[avatar_name] = {"wins": 0, "losses": 0}

                if did_win:
                    avatar_stats[avatar_name]["wins"] += 1
                else:
                    avatar_stats[avatar_name]["losses"] += 1
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                continue

    avatar_performance = []
    for name, stats in avatar_stats.items():
        total = stats["wins"] + stats["losses"]
        rate = (stats["wins"] / total * 100) if total > 0 else 0
        avatar_performance.append({
            "name": name,
            "wins": stats["wins"],
            "losses": stats["losses"],
            "win_rate": round(rate, 1),
        })
    avatar_performance.sort(key=lambda x: x["wins"] + x["losses"], reverse=True)

    # Opponent avatar stats
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
                    avatar = deck_data.get("avatar", [])
                    if avatar and avatar[0] and avatar[0].get("name"):
                        opponent_avatar_name = avatar[0].get("name")
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
        avatar_matchups.append({
            "opponent_avatar": name,
            "wins": stats["wins"],
            "losses": stats["losses"],
            "win_rate": round(rate, 1),
            "total_games": total,
        })
    avatar_matchups.sort(key=lambda x: x["total_games"], reverse=True)

    # Check ownership
    logged_in_user_id = session.get("user_id")
    is_owner = logged_in_user_id is not None and str(logged_in_user_id) == str(player_id)

    # API key grants owner-level access (for server-to-server calls)
    api_key = request.headers.get("X-API-Key")
    if api_key and api_key in VALID_API_KEYS:
        is_owner = True

    # Admins have full access to all player profiles
    if is_admin():
        is_owner = True

    # Build match history
    match_history = []
    sorted_rows = sorted(rows, key=lambda x: x[6] if x[6] else "", reverse=True)
    for row in sorted_rows[:50]:
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

        has_deck = False
        has_deck_json = False
        if player_deck_url_check and player_deck_url_check not in ("No URL provided", "Admin reported match", "{}", "", None):
            has_deck = True
        if player_deck_json and player_deck_json not in ("{}", "", None):
            has_deck = True
            has_deck_json = True
        elif old_curiosa_url and old_curiosa_url not in ("No URL provided", "Admin reported match", "{}", "", None):
            has_deck = True
        if old_json_deck_data and old_json_deck_data not in ("{}", "", None):
            has_deck = True
            if not has_deck_json:
                has_deck_json = True

        if is_owner:
            player_deck_url = winner_deck_url if did_win else loser_deck_url
            opponent_deck_url = loser_deck_url if did_win else winner_deck_url

        match_history.append({
            "match_id": row[12],
            "opponent": opponent_name,
            "opponent_id": opponent_id,
            "result": "Win" if did_win else "Loss",
            "elo_change": elo_change if elo_change else 0,
            "date": row[6],
            "first_player": "Play" if row[1] and "y" in str(row[1]).lower() else "Draw",
            "match_time": row[3] if row[3] else None,
            "replay_url": row[9] if row[9] else None,
            "player_deck_url": player_deck_url,
            "opponent_deck_url": opponent_deck_url,
            "has_deck": has_deck,
            "has_deck_json": has_deck_json,
        })

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

            if not player_deck_url or player_deck_url in ("No URL provided", "Admin reported match", "{}"):
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

            recent_decks.append({
                "url": player_deck_url,
                "avatar": avatar_name,
                "deck_name": deck_name,
                "date": row[6],
            })

            if len(recent_decks) >= 10:
                break

    # Recorded games (owner only)
    recorded_games = []
    sorted_solo_rows = sorted(solo_rows, key=lambda x: x[6] if x[6] else "", reverse=True)
    for row in sorted_solo_rows[:50]:
        did_win = row[0]
        opponent_name = row[5]
        deck_url = row[9]

        recorded_games.append({
            "report_id": row[12],
            "opponent": opponent_name,
            "result": "Win" if did_win else "Loss",
            "date": row[6],
            "first_player": "Play" if row[1] and "y" in str(row[1]).lower() else "Draw",
            "match_time": row[3] if row[3] else None,
            "deck_url": deck_url,
        })

    return jsonify({
        "id": player_id,
        "name": player_name,
        "elo": player_elo,
        "rank": rank,
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
    })
