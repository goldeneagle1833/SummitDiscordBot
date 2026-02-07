"""Leaderboard API routes."""

import logging
from flask import Blueprint, jsonify

from services.leaderboard import LeaderboardService

logger = logging.getLogger(__name__)

leaderboard_bp = Blueprint("leaderboard", __name__)


@leaderboard_bp.route("/leaderboard")
def get_leaderboard():
    """Get lifetime ELO leaderboard with win/loss records."""
    try:
        service = LeaderboardService()
        leaderboard_data = service.get_leaderboard()
        return jsonify(leaderboard_data)
    except Exception as e:
        logger.error(f"Error fetching leaderboard: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@leaderboard_bp.route("/leaderboard/event")
def get_event_leaderboard():
    """Get current event ELO leaderboard."""
    try:
        service = LeaderboardService()
        event_data = service.get_event_leaderboard()
        return jsonify(event_data)
    except Exception as e:
        logger.error(f"Error fetching event leaderboard: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@leaderboard_bp.route("/leaderboard/combined")
def get_combined_leaderboard():
    """Get both lifetime and event leaderboards."""
    try:
        service = LeaderboardService()
        combined_data = service.get_combined_leaderboard()
        return jsonify(combined_data)
    except Exception as e:
        logger.error(f"Error fetching combined leaderboard: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@leaderboard_bp.route("/elo-distribution")
def get_elo_distribution():
    """Get ELO distribution across bands."""
    try:
        service = LeaderboardService()
        distribution = service.get_elo_distribution()
        return jsonify(distribution)
    except Exception as e:
        logger.error(f"Error fetching ELO distribution: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@leaderboard_bp.route("/events")
def get_events():
    """Get all events for ELO filtering."""
    try:
        from repositories.elo import EloRepository

        repo = EloRepository()
        events = repo.get_all_events()
        active_event = repo.get_active_event()
        return jsonify(
            {
                "events": events,
                "active_event": active_event,
            }
        )
    except Exception as e:
        logger.error(f"Error fetching events: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@leaderboard_bp.route("/player/<player_id>/event/<int:event_id>")
def get_player_event_stats(player_id, event_id):
    """Get a player's stats for a specific past event."""
    try:
        from repositories.elo import EloRepository

        repo = EloRepository()
        stats = repo.get_player_event_elo(int(player_id), event_id)
        if stats:
            return jsonify(stats)
        return jsonify({"error": "No data found for this player in this event"}), 404
    except Exception as e:
        logger.error(f"Error fetching player event stats: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
