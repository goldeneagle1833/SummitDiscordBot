"""Draft Sorcery integration API for limited arena runs."""

import logging
import sqlite3

from flask import Blueprint, jsonify, request, session

from utils.api_auth import require_api_key
from repositories.limited_repo import (
    get_active_arena_run,
    get_all_archived_match_history,
    get_all_archived_runs_for_user,
    get_all_limited_match_history,
    get_all_runs_for_user,
    get_archived_arena_run,
    get_arena_run,
    get_latest_arena_run,
    get_limited_elo,
    get_matches_for_archived_run_with_decks,
    get_matches_for_run,
    get_matches_for_run_with_decks,
    get_latest_arena_run_from_archive,
    get_matches_for_archived_run,
    get_all_archived_matches_for_user,
    get_run_matchups,
)
from services.limited_service import (
    MAX_ARENA_LOSSES,
    MAX_ARENA_WINS,
    close_arena_run,
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
        is_archived = False

        if active_run:
            has_active = True
            can_queue = active_run["wins"] < MAX_ARENA_WINS and active_run["losses"] < MAX_ARENA_LOSSES
            run_data = _run_to_dict(active_run)
            match_history = get_matches_for_run(active_run["run_id"], uid)
        else:
            has_active = False
            can_queue = False
            latest = get_latest_arena_run(uid)
            if latest:
                run_data = _run_to_dict(latest)
                match_history = get_matches_for_run(latest["run_id"], uid)
            else:
                # No live data — fall back to archive tables (between events)
                archived = get_latest_arena_run_from_archive(uid)
                if archived:
                    is_archived = True
                    run_data = _run_to_dict(archived)
                    match_history = get_all_archived_matches_for_user(uid)
                else:
                    run_data = None
                    match_history = []

        logger.info(
            "GET status for user %s: has_active_run=%s, can_queue=%s, is_archived=%s",
            uid, has_active, can_queue, is_archived,
        )

        return jsonify({
            "success": True,
            "user_id": user_id,
            "has_active_run": has_active,
            "run": run_data,
            "match_history": match_history,
            "limited_elo": elo,
            "can_queue": can_queue,
            "is_archived": is_archived,
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
    logger.info(
        "POST run for user %s: content_type=%s body_keys=%s raw=%s",
        user_id,
        request.content_type,
        list(body.keys()) if body else "EMPTY",
        request.get_data(as_text=True)[:200],
    )

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


@limited_bp.route("/run/<int:run_id>/matchups", methods=["GET"])
def get_run_matchups_endpoint(run_id):
    """Get detailed matchups for an arena run. Public endpoint.

    Opponent deck URLs are only visible when the opponent's run is no longer active.
    """
    try:
        run = get_arena_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        # Check if the requesting user owns this run
        logged_in_user_id = session.get("user_id")
        run_owner_id = str(run["user_id"])
        is_run_owner = logged_in_user_id is not None and str(logged_in_user_id) == run_owner_id

        # Block access to active runs unless the viewer is the owner
        if run["status"] == "active" and not is_run_owner:
            return jsonify({"error": "Run is still in progress"}), 403

        matchups = get_run_matchups(run_id)
        return jsonify({
            "run_id": run_id,
            "user_id": run["user_id"],
            "user_display_name": run["user_display_name"],
            "deck_url": run["deck_url"],
            "wins": run["wins"],
            "losses": run["losses"],
            "status": run["status"],
            "matchups": matchups,
        })
    except Exception as e:
        logger.error("Error fetching run matchups for run %d: %s", run_id, e)
        return jsonify({"error": "Internal server error"}), 500


@limited_bp.route("/match-history", methods=["GET"])
@require_api_key
def get_match_history():
    """Get limited match history with deck links.

    Query params:
    - user_id: Return all runs and per-run match history for this user.
    - run_id: Return match history for a specific run (deck).
    - Neither: Return all match records globally.
    """
    user_id = request.args.get("user_id")
    run_id = request.args.get("run_id")

    try:
        if user_id and run_id:
            return jsonify({"success": False, "error": "Provide user_id or run_id, not both"}), 400

        if run_id:
            try:
                rid = int(run_id)
            except ValueError:
                return jsonify({"success": False, "error": "Invalid run_id"}), 400

            # Check live table first, then archive
            run = get_arena_run(rid)
            if run:
                matches = get_matches_for_run_with_decks(rid)
            else:
                run = get_archived_arena_run(rid)
                if run:
                    matches = get_matches_for_archived_run_with_decks(rid)

            if not run:
                return jsonify({"success": False, "error": "Run not found"}), 404

            return jsonify({
                "success": True,
                "run": _run_to_dict(run),
                "matches": matches,
            })

        if user_id:
            try:
                uid = int(user_id)
            except ValueError:
                return jsonify({"success": False, "error": "Invalid user_id"}), 400

            # Combine live runs and archived runs
            runs_with_matches = []

            for run in get_all_runs_for_user(uid):
                matches = get_matches_for_run_with_decks(run["run_id"])
                run_data = _run_to_dict(run)
                run_data["matches"] = matches
                runs_with_matches.append(run_data)

            for run in get_all_archived_runs_for_user(uid):
                matches = get_matches_for_archived_run_with_decks(run["run_id"])
                run_data = _run_to_dict(run)
                run_data["matches"] = matches
                runs_with_matches.append(run_data)

            return jsonify({
                "success": True,
                "user_id": user_id,
                "runs": runs_with_matches,
            })

        # No filters — return global match history (live + archived)
        matches = get_all_limited_match_history() + get_all_archived_match_history()
        matches.sort(key=lambda m: m["timestamp"], reverse=True)
        return jsonify({
            "success": True,
            "matches": matches,
        })

    except sqlite3.Error as e:
        logger.error("Database error in GET match-history: %s", e)
        return jsonify({"success": False, "error": "Database error"}), 500
    except Exception as e:
        logger.error("Unexpected error in GET match-history: %s", e)
        return jsonify({"success": False, "error": "Internal server error"}), 500


@limited_bp.route("/user/<user_id>/end-run", methods=["POST"])
@require_api_key
def post_end_run(user_id):
    """End the current active run (clean close, no ELO penalties)."""
    try:
        uid = int(user_id)
    except ValueError:
        return jsonify({"success": False, "error": "Invalid user_id"}), 400

    try:
        active_run = get_active_arena_run(uid)
        if not active_run:
            return jsonify({"success": False, "error": "No active run to end"}), 400

        try:
            summary = close_arena_run(uid)
        except ValueError as e:
            return jsonify({"success": False, "error": str(e)}), 400

        latest = get_latest_arena_run(uid)
        elo = get_limited_elo(uid)

        logger.info("POST end-run for user %s: run closed (no ELO penalty)", uid)

        return jsonify({
            "success": True,
            "run": _run_to_dict(latest) if latest else None,
            "limited_elo": elo,
            "summary": summary,
        })

    except sqlite3.Error as e:
        logger.error("Database error in POST end-run for user %s: %s", user_id, e)
        return jsonify({"success": False, "error": "Database error"}), 500
    except Exception as e:
        logger.error("Unexpected error in POST end-run for user %s: %s", user_id, e)
        return jsonify({"success": False, "error": "Internal server error"}), 500
