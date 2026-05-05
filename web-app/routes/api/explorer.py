"""Explorer Standings API routes."""

import json
import logging

from flask import Blueprint, jsonify, request

from repositories.explorer import ExplorerRepository
from utils.auth import require_admin, require_explorer_admin

logger = logging.getLogger(__name__)

explorer_bp = Blueprint("explorer", __name__)

DEFAULT_POINTS_CONFIG = {
    "participation": 10,
    "bonus_pathfinder": {"0": 5, "1": 4, "2": 3},
    "persecutor": {"1": 10, "2": 5, "3": 4, "4": 4, "5": 3, "6": 3, "7": 2, "8": 2},
    "trials_threshold": 10,
}


# ── Seasons ───────────────────────────────────────────────────────────────────


@explorer_bp.route("/seasons")
def get_seasons():
    """List all Explorer seasons. Public."""
    try:
        repo = ExplorerRepository()
        seasons = repo.get_all_seasons()
        for s in seasons:
            if s.get("points_config"):
                try:
                    s["points_config"] = json.loads(s["points_config"])
                except (json.JSONDecodeError, TypeError):
                    s["points_config"] = DEFAULT_POINTS_CONFIG
            else:
                s["points_config"] = DEFAULT_POINTS_CONFIG
        return jsonify(seasons)
    except Exception as e:
        logger.error(f"Error fetching explorer seasons: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@explorer_bp.route("/seasons", methods=["POST"])
@require_explorer_admin
def create_season():
    """Create a new Explorer season."""
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Season name is required"}), 400

    description = (data.get("description") or "").strip() or None
    points_config = data.get("points_config") or DEFAULT_POINTS_CONFIG
    points_config_json = json.dumps(points_config)

    try:
        repo = ExplorerRepository()
        season = repo.create_season(name, description, points_config_json)
        if season.get("points_config"):
            season["points_config"] = json.loads(season["points_config"])
        return jsonify({"success": True, "season": season}), 201
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            return jsonify({"error": f"Season '{name}' already exists"}), 409
        logger.error(f"Error creating explorer season: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@explorer_bp.route("/seasons/<int:season_id>", methods=["DELETE"])
@require_explorer_admin
def delete_season(season_id):
    """Delete a season and all its events/results."""
    try:
        repo = ExplorerRepository()
        if not repo.get_season(season_id):
            return jsonify({"error": "Season not found"}), 404
        repo.delete_season(season_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error deleting explorer season: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@explorer_bp.route("/seasons/<int:season_id>/events")
def get_season_events(season_id):
    """List all events in a season. Public."""
    try:
        repo = ExplorerRepository()
        if not repo.get_season(season_id):
            return jsonify({"error": "Season not found"}), 404
        events = repo.get_events_for_season(season_id)
        return jsonify(events)
    except Exception as e:
        logger.error(f"Error fetching season events: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ── Events ────────────────────────────────────────────────────────────────────


@explorer_bp.route("/events/preview", methods=["POST"])
@require_explorer_admin
def preview_event():
    """Fetch event data from carde.io and return a preview without saving."""
    data = request.get_json() or {}
    url = (data.get("url") or "").strip()
    season_id = data.get("season_id")

    if not url or not season_id:
        return jsonify({"error": "url and season_id are required"}), 400

    try:
        from services.explorer import ExplorerFetchError, ExplorerService
        repo = ExplorerRepository()

        service = ExplorerService()
        event_data = service.fetch_event_data(url)

        existing = repo.get_event_by_cardeio_id(event_data["cardeio_event_id"])
        if existing:
            return jsonify({"error": "Event already imported"}), 409

        return jsonify(event_data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        if "ExplorerFetchError" in type(e).__name__:
            return jsonify({"error": f"Failed to fetch event from carde.io: {e}"}), 502
        logger.error(f"Error previewing explorer event: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@explorer_bp.route("/events", methods=["POST"])
@require_explorer_admin
def save_event():
    """Import and save an event from a carde.io URL."""
    data = request.get_json() or {}
    url = (data.get("url") or "").strip()
    season_id = data.get("season_id")

    if not url or not season_id:
        return jsonify({"error": "url and season_id are required"}), 400

    try:
        from services.explorer import ExplorerFetchError, ExplorerService
        repo = ExplorerRepository()

        service = ExplorerService()
        event_data = service.fetch_event_data(url)

        existing = repo.get_event_by_cardeio_id(event_data["cardeio_event_id"])
        if existing:
            return jsonify({"error": "Event already imported"}), 409

        if not repo.get_season(season_id):
            return jsonify({"error": "Season not found"}), 404

        event = repo.create_event(
            season_id=season_id,
            cardeio_event_id=event_data["cardeio_event_id"],
            cardeio_swiss_phase_id=event_data["cardeio_swiss_phase_id"],
            cardeio_final_tournament_id=event_data.get("cardeio_final_tournament_id"),
            event_name=event_data["event_name"],
            event_date=event_data.get("event_date"),
            total_players=event_data.get("total_players"),
            play_format=event_data.get("play_format"),
            venue_name=event_data.get("venue_name"),
            source_url=url,
        )
        repo.save_results(event["id"], event_data["results"])

        return jsonify({
            "success": True,
            "event": {
                "id": event["id"],
                "event_name": event["event_name"],
                "total_players": event["total_players"],
            },
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        if "ExplorerFetchError" in type(e).__name__:
            return jsonify({"error": f"Failed to fetch event from carde.io: {e}"}), 502
        logger.error(f"Error saving explorer event: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@explorer_bp.route("/events/<int:event_id>", methods=["DELETE"])
@require_explorer_admin
def delete_event(event_id):
    """Remove an event and all its results."""
    try:
        repo = ExplorerRepository()
        if not repo.get_event(event_id):
            return jsonify({"error": "Event not found"}), 404
        repo.delete_event(event_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error deleting explorer event: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ── Leaderboard ───────────────────────────────────────────────────────────────


@explorer_bp.route("/leaderboard/<int:season_id>")
def get_leaderboard(season_id):
    """Compute and return the three-track season leaderboard. Public."""
    try:
        from services.explorer import ExplorerService
        repo = ExplorerRepository()
        if not repo.get_season(season_id):
            return jsonify({"error": "Season not found"}), 404
        service = ExplorerService()
        return jsonify(service.compute_leaderboard(season_id))
    except Exception as e:
        logger.error(f"Error computing explorer leaderboard: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ── Admins ────────────────────────────────────────────────────────────────────


@explorer_bp.route("/admins")
@require_admin
def get_admins():
    """List Explorer admins. Global admin only."""
    try:
        repo = ExplorerRepository()
        return jsonify(repo.get_explorer_admins())
    except Exception as e:
        logger.error(f"Error fetching explorer admins: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@explorer_bp.route("/admins", methods=["POST"])
@require_admin
def add_admin():
    """Add an Explorer admin. Global admin only."""
    data = request.get_json() or {}
    discord_user_id = (data.get("discord_user_id") or "").strip()
    display_name = (data.get("display_name") or "").strip() or None
    if not discord_user_id:
        return jsonify({"error": "discord_user_id is required"}), 400
    try:
        repo = ExplorerRepository()
        repo.add_explorer_admin(discord_user_id, display_name)
        return jsonify({"success": True}), 201
    except Exception as e:
        logger.error(f"Error adding explorer admin: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@explorer_bp.route("/admins/<discord_user_id>", methods=["DELETE"])
@require_admin
def remove_admin(discord_user_id):
    """Remove an Explorer admin. Global admin only."""
    try:
        repo = ExplorerRepository()
        removed = repo.remove_explorer_admin(discord_user_id)
        if not removed:
            return jsonify({"error": "Admin not found"}), 404
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error removing explorer admin: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
