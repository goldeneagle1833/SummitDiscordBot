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


@leaderboard_bp.route("/leaderboard/paper")
def get_paper_leaderboard():
    """Get paper ELO leaderboard (web-reported matches only)."""
    try:
        service = LeaderboardService()
        leaderboard_data = service.get_paper_leaderboard()
        return jsonify(leaderboard_data)
    except Exception as e:
        logger.error(f"Error fetching paper leaderboard: {e}", exc_info=True)
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


@leaderboard_bp.route("/leaderboard/sources")
def get_leaderboard_sources():
    """Get all available match sources (Discord, external platforms, etc.)."""
    try:
        from repositories.matches import MatchRepository

        repo = MatchRepository()
        sources = repo.get_distinct_sources()
        return jsonify(sources)
    except Exception as e:
        logger.error(f"Error fetching leaderboard sources: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@leaderboard_bp.route("/leaderboard/source/<source>")
def get_source_leaderboard(source):
    """Get ELO leaderboard for a specific external source."""
    try:
        service = LeaderboardService()
        leaderboard_data = service.get_source_leaderboard(source)
        return jsonify(leaderboard_data)
    except Exception as e:
        logger.error(f"Error fetching source leaderboard: {e}", exc_info=True)
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

        # Normalize player_id (strip 'google_' prefix for Google OAuth users)
        player_id_str = str(player_id)
        if player_id_str.startswith("google_"):
            player_id = player_id_str[7:]  # Remove 'google_' prefix

        repo = EloRepository()
        # Keep as string to avoid overflow with large Google IDs
        stats = repo.get_player_event_elo(player_id, event_id)
        if stats:
            return jsonify(stats)
        return jsonify({"error": "No data found for this player in this event"}), 404
    except Exception as e:
        logger.error(f"Error fetching player event stats: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
