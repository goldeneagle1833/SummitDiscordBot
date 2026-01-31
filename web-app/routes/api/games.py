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
                    int(user_id),
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

        if int(row[0]) != int(user_id):
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
