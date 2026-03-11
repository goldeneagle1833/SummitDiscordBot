"""Game recording API routes."""

import logging
import sqlite3

from flask import Blueprint, jsonify, request, session

from webapp_config import MATCH_RECORDS_DB_PATH
from services.curiosa import CuriosaService
from utils.auth import require_auth

logger = logging.getLogger(__name__)

games_bp = Blueprint("games", __name__)


@games_bp.route("/record-game", methods=["POST"])
@require_auth
def record_game():
    """
    API endpoint for users to record personal match results (non-ELO).
    Directly inserts into solo_match_reports table.
    Requires session login or API key.
    """
    user_id = session.get("user_id")
    if user_id is None:
        # API key auth - get user_id from request body for server-to-server calls
        data = request.get_json() or {}
        user_id = data.get("user_id")
        if user_id is None:
            return jsonify({"error": "user_id required for API key auth", "success": False}), 400

    # Normalize user_id (strip 'google_' prefix for Google OAuth users)
    user_id_str = str(user_id)
    if user_id_str.startswith("google_"):
        user_id = user_id_str[7:]  # Remove 'google_' prefix

    username = session.get("username", "Unknown User")

    try:
        data = request.get_json()

        required = ["deck_url", "opponent_avatar", "did_win", "went_first"]
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({
                "error": f"Missing required fields: {', '.join(missing)}",
                "success": False,
            }), 400

        deck_url = str(data["deck_url"]).strip()
        opponent_avatar = str(data["opponent_avatar"]).strip()
        did_win = bool(data["did_win"])
        went_first = "y" if data["went_first"] else "n"
        match_time = int(data.get("match_time", 0))
        match_comment = str(data.get("match_comment", "")).strip()

        opponent_name = opponent_avatar

        # Fetch deck data from Curiosa API
        curiosa_service = CuriosaService()
        json_deck_data = curiosa_service.fetch_deck_data(deck_url)
        if json_deck_data != "{}":
            logger.info("Successfully fetched deck data for recorded game")
        else:
            logger.warning(f"Could not fetch deck data from Curiosa for URL: {deck_url}")

        try:
            conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
            cur = conn.cursor()

            cur.execute(
                """INSERT INTO solo_match_reports
                   (reporter_id, reporter_name, opponent_name, is_winner,
                    first_player, match_time, curiosa_link, match_comment,
                    report_date, json_deck_data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)""",
                (
                    user_id,  # Keep as string to avoid overflow with large Google IDs
                    username,
                    opponent_name,
                    did_win,
                    went_first,
                    match_time,
                    deck_url,
                    match_comment,
                    json_deck_data,
                ),
            )

            report_id = cur.lastrowid
            conn.commit()
            conn.close()

            return jsonify({
                "success": True,
                "report_id": report_id,
                "message": "Game recorded successfully",
            })

        except sqlite3.Error as e:
            logger.error(f"Database error recording game: {e}", exc_info=True)
            return jsonify({"error": "Failed to save to database", "success": False}), 500

    except ValueError as e:
        return jsonify({"error": f"Invalid data: {str(e)}", "success": False}), 400
    except Exception as e:
        logger.error(f"Error recording game: {e}", exc_info=True)
        return jsonify({"error": "Internal server error", "success": False}), 500


@games_bp.route("/delete-recorded-game/<int:report_id>", methods=["DELETE"])
@require_auth
def delete_recorded_game(report_id):
    """
    API endpoint to delete a recorded game (solo_match_report).
    Only the owner of the report can delete it.
    Requires session login or API key.
    """
    user_id = session.get("user_id")
    if user_id is None:
        # API key auth - get user_id from query param or body
        user_id = request.args.get("user_id")
        if user_id is None:
            return jsonify({"error": "user_id required for API key auth", "success": False}), 400

    # Normalize user_id (strip 'google_' prefix for Google OAuth users)
    user_id_str = str(user_id)
    if user_id_str.startswith("google_"):
        user_id = user_id_str[7:]  # Remove 'google_' prefix

    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()
        cur.execute(
            "SELECT reporter_id FROM solo_match_reports WHERE rowid = ?",
            (report_id,),
        )
        row = cur.fetchone()

        if not row:
            conn.close()
            return jsonify({"error": "Recorded game not found", "success": False}), 404

        # Compare as strings to avoid overflow with large IDs
        if str(row[0]) != str(user_id):
            conn.close()
            return jsonify({
                "error": "You can only delete your own recorded games",
                "success": False,
            }), 403

        cur.execute("DELETE FROM solo_match_reports WHERE rowid = ?", (report_id,))
        conn.commit()
        conn.close()

        return jsonify({
            "success": True,
            "message": "Recorded game deleted successfully",
        })

    except Exception as e:
        logger.error(f"Error deleting recorded game: {e}", exc_info=True)
        return jsonify({"error": "Internal server error", "success": False}), 500


@games_bp.route("/update-match-deck", methods=["PUT"])
@require_auth
def update_match_deck():
    """
    API endpoint to update a player's deck URL/data for an existing match.
    Only the winner or loser of the match can update their own deck.
    Works for both bot (match_records) and web (match_reports_web) matches.
    """
    user_id = session.get("user_id")
    if user_id is None:
        data = request.get_json() or {}
        user_id = data.get("user_id")
        if user_id is None:
            return jsonify({"error": "user_id required for API key auth", "success": False}), 400

    # Keep original user_id (with google_ prefix) for web match lookups
    original_user_id = str(user_id)

    # Normalize user_id (strip 'google_' prefix for bot match lookups)
    user_id_normalized = original_user_id
    if original_user_id.startswith("google_"):
        user_id_normalized = original_user_id[7:]

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body required", "success": False}), 400

        match_id = data.get("match_id")
        deck_url = data.get("deck_url", "").strip()
        source = data.get("source", "bot")

        if not match_id:
            return jsonify({"error": "match_id is required", "success": False}), 400
        if not deck_url:
            return jsonify({"error": "deck_url is required", "success": False}), 400
        if source not in ("bot", "web"):
            return jsonify({"error": "source must be 'bot' or 'web'", "success": False}), 400

        # Fetch deck data from Curiosa API
        curiosa_service = CuriosaService()
        json_deck_data = curiosa_service.fetch_deck_data(deck_url)
        if json_deck_data == "{}":
            logger.warning(f"Could not fetch deck data from Curiosa for URL: {deck_url}")

        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()

        try:
            if source == "web":
                # Web matches use TEXT match_id and original_user_id (with google_ prefix)
                cur.execute(
                    "SELECT winner_id, losser_id FROM match_reports_web WHERE match_id = ?",
                    (str(match_id),),
                )
                row = cur.fetchone()
                if not row:
                    conn.close()
                    return jsonify({"error": "Match not found", "success": False}), 404

                winner_id, loser_id = str(row[0]), str(row[1])
                if original_user_id == winner_id:
                    is_winner = True
                elif original_user_id == loser_id:
                    is_winner = False
                else:
                    conn.close()
                    return jsonify({"error": "You can only update your own deck", "success": False}), 403

                if is_winner:
                    cur.execute(
                        "UPDATE match_reports_web SET curiosa_url_winner = ?, json_deck_data_winner = ? WHERE match_id = ?",
                        (deck_url, json_deck_data, str(match_id)),
                    )
                else:
                    cur.execute(
                        "UPDATE match_reports_web SET curiosa_url_loser = ?, json_deck_data_loser = ? WHERE match_id = ?",
                        (deck_url, json_deck_data, str(match_id)),
                    )
            else:
                # Bot matches use INTEGER rowid and normalized user_id
                cur.execute(
                    "SELECT winner_id, losser_id FROM match_records WHERE rowid = ?",
                    (int(match_id),),
                )
                row = cur.fetchone()
                if not row:
                    conn.close()
                    return jsonify({"error": "Match not found", "success": False}), 404

                winner_id, loser_id = str(row[0]), str(row[1])
                if user_id_normalized == winner_id:
                    is_winner = True
                elif user_id_normalized == loser_id:
                    is_winner = False
                else:
                    conn.close()
                    return jsonify({"error": "You can only update your own deck", "success": False}), 403

                if is_winner:
                    cur.execute(
                        "UPDATE match_records SET curiosa_url_winner = ?, json_deck_data_winner = ? WHERE rowid = ?",
                        (deck_url, json_deck_data, int(match_id)),
                    )
                else:
                    cur.execute(
                        "UPDATE match_records SET curiosa_url_loser = ?, json_deck_data_loser = ? WHERE rowid = ?",
                        (deck_url, json_deck_data, int(match_id)),
                    )

            conn.commit()
            conn.close()

            return jsonify({
                "success": True,
                "message": "Deck updated successfully",
                "fetched_deck_data": json_deck_data != "{}",
            })

        except sqlite3.Error as e:
            conn.close()
            logger.error(f"Database error updating match deck: {e}", exc_info=True)
            return jsonify({"error": "Failed to update database", "success": False}), 500

    except ValueError as e:
        return jsonify({"error": f"Invalid data: {str(e)}", "success": False}), 400
    except Exception as e:
        logger.error(f"Error updating match deck: {e}", exc_info=True)
        return jsonify({"error": "Internal server error", "success": False}), 500
