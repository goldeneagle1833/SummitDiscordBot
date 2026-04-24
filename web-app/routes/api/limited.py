"""Draft Sorcery integration API for limited arena runs."""

import logging
import sqlite3

from flask import Blueprint, jsonify, request

from utils.api_auth import require_api_key
from repositories.limited_repo import (
    get_active_arena_run,
    get_arena_run,
    get_latest_arena_run,
    get_limited_elo,
    get_matches_for_run,
)
from services.limited_service import (
    MAX_ARENA_LOSSES,
    MAX_ARENA_WINS,
    forfeit_arena_run,
    report_match,
    start_arena_run,
)

logger = logging.getLogger(__name__)

limited_bp = Blueprint("limited", __name__)


def _run_to_dict(run: dict) -> dict:
    """Convert a run dict to the API response format (exclude internal fields)."""
    result = {
        "run_id": run["run_id"],
        "deck_url": run["deck_url"],
        "wins": run["wins"],
        "losses": run["losses"],
        "status": run["status"],
        "starting_elo": run["starting_elo"],
        "created_at": run["created_at"],
    }
    if run.get("completed_at"):
        result["completed_at"] = run["completed_at"]
    return result


@limited_bp.route("/user/<user_id>/status", methods=["GET"])
@require_api_key
def get_user_status(user_id):
    """Get a player's current limited arena status."""
    try:
        uid = int(user_id)
    except ValueError:
        return jsonify({"success": False, "error": "Invalid user_id"}), 400

    try:
        active_run = get_active_arena_run(uid)
        elo = get_limited_elo(uid)

        if active_run:
            has_active = True
            can_queue = active_run["wins"] < MAX_ARENA_WINS and active_run["losses"] < MAX_ARENA_LOSSES
            run_data = _run_to_dict(active_run)
            match_history = get_matches_for_run(active_run["run_id"], uid)
        else:
            has_active = False
            can_queue = False
            latest = get_latest_arena_run(uid)
            run_data = _run_to_dict(latest) if latest else None
            match_history = get_matches_for_run(latest["run_id"], uid) if latest else []

        logger.info("GET status for user %s: has_active_run=%s, can_queue=%s", uid, has_active, can_queue)

        return jsonify({
            "success": True,
            "user_id": user_id,
            "has_active_run": has_active,
            "run": run_data,
            "match_history": match_history,
            "limited_elo": elo,
            "can_queue": can_queue,
        })

    except sqlite3.Error as e:
        logger.error("Database error in GET status for user %s: %s", user_id, e)
        return jsonify({"success": False, "error": "Database error"}), 500
    except Exception as e:
        logger.error("Unexpected error in GET status for user %s: %s", user_id, e)
        return jsonify({"success": False, "error": "Internal server error"}), 500


@limited_bp.route("/user/<user_id>/run", methods=["POST"])
@require_api_key
def post_user_run(user_id):
    """Start a new arena run or forfeit the current one."""
    try:
        uid = int(user_id)
    except ValueError:
        return jsonify({"success": False, "error": "Invalid user_id"}), 400

    body = request.get_json(silent=True) or {}

    try:
        if body.get("forfeit"):
            # Forfeit current active run
            try:
                summary = forfeit_arena_run(uid)
            except ValueError as e:
                return jsonify({"success": False, "error": str(e)}), 400

            latest = get_latest_arena_run(uid)
            elo = get_limited_elo(uid)

            logger.info("POST run forfeit for user %s: %s", uid, summary)

            return jsonify({
                "success": True,
                "action": "forfeited",
                "run": _run_to_dict(latest) if latest else None,
                "limited_elo": elo,
                "penalty_summary": summary,
            })

        else:
            # Start new run
            deck_url = body.get("deck_url")
            display_name = body.get("display_name")

            if not deck_url or not display_name:
                return jsonify({
                    "success": False,
                    "error": "deck_url and display_name are required to start a new run",
                }), 400

            try:
                run = start_arena_run(uid, display_name, deck_url)
            except ValueError as e:
                return jsonify({"success": False, "error": str(e)}), 400

            if run is None:
                return jsonify({"success": False, "error": "Failed to create run"}), 500

            elo = get_limited_elo(uid)

            logger.info("POST run created for user %s: run_id=%s", uid, run["run_id"])

            return jsonify({
                "success": True,
                "action": "created",
                "run": _run_to_dict(run),
                "limited_elo": elo,
            }), 201

    except sqlite3.Error as e:
        logger.error("Database error in POST run for user %s: %s", user_id, e)
        return jsonify({"success": False, "error": "Database error"}), 500
    except Exception as e:
        logger.error("Unexpected error in POST run for user %s: %s", user_id, e)
        return jsonify({"success": False, "error": "Internal server error"}), 500


@limited_bp.route("/report-match", methods=["POST"])
@require_api_key
def post_report_match():
    """Submit a limited match result from a 3rd party source.

    Both players must have active arena runs.
    """
    body = request.get_json(silent=True) or {}

    # Validate required fields
    winner_id = body.get("winner_id")
    loser_id = body.get("loser_id")
    winner_display_name = body.get("winner_display_name")
    loser_display_name = body.get("loser_display_name")

    if winner_id is None or loser_id is None or not winner_display_name or not loser_display_name:
        return jsonify({
            "success": False,
            "error": "winner_id, loser_id, winner_display_name, and loser_display_name are required",
        }), 400

    try:
        winner_id = int(winner_id)
        loser_id = int(loser_id)
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "winner_id and loser_id must be valid integers"}), 400

    if winner_id == loser_id:
        return jsonify({"success": False, "error": "winner_id and loser_id must be different"}), 400

    try:
        result = report_match(
            winner_id=winner_id,
            winner_display_name=winner_display_name,
            loser_id=loser_id,
            loser_display_name=loser_display_name,
            first_player=body.get("first_player"),
            match_time=body.get("match_time"),
            match_comment=body.get("match_comment"),
        )

        logger.info(
            "POST report-match: match_id=%d, winner=%s, loser=%s",
            result["match_id"], winner_id, loser_id,
        )

        return jsonify({"success": True, **result}), 201

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except sqlite3.Error as e:
        logger.error("Database error in POST report-match: %s", e)
        return jsonify({"success": False, "error": "Database error"}), 500
    except Exception as e:
        logger.error("Unexpected error in POST report-match: %s", e)
        return jsonify({"success": False, "error": "Internal server error"}), 500


@limited_bp.route("/user/<user_id>/end-run", methods=["POST"])
@require_api_key
def post_end_run(user_id):
    """End the current active run, applying remaining losses as ELO penalties."""
    try:
        uid = int(user_id)
    except ValueError:
        return jsonify({"success": False, "error": "Invalid user_id"}), 400

    try:
        active_run = get_active_arena_run(uid)
        if not active_run:
            return jsonify({"success": False, "error": "No active run to end"}), 400

        losses_applied = MAX_ARENA_LOSSES - active_run["losses"]

        try:
            summary = forfeit_arena_run(uid)
        except ValueError as e:
            return jsonify({"success": False, "error": str(e)}), 400

        latest = get_latest_arena_run(uid)
        elo = get_limited_elo(uid)

        logger.info("POST end-run for user %s: %d losses applied", uid, losses_applied)

        return jsonify({
            "success": True,
            "run": _run_to_dict(latest) if latest else None,
            "limited_elo": elo,
            "losses_applied": losses_applied,
            "penalty_summary": summary,
        })

    except sqlite3.Error as e:
        logger.error("Database error in POST end-run for user %s: %s", user_id, e)
        return jsonify({"success": False, "error": "Database error"}), 500
    except Exception as e:
        logger.error("Unexpected error in POST end-run for user %s: %s", user_id, e)
        return jsonify({"success": False, "error": "Internal server error"}), 500
