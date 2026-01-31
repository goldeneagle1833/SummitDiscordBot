"""Leaderboard API routes."""

import logging
from flask import Blueprint, jsonify

from services.leaderboard import LeaderboardService

logger = logging.getLogger(__name__)

leaderboard_bp = Blueprint("leaderboard", __name__)


@leaderboard_bp.route("/leaderboard")
def get_leaderboard():
    """Get ELO leaderboard with win/loss records."""
    try:
        service = LeaderboardService()
        leaderboard_data = service.get_leaderboard()
        return jsonify(leaderboard_data)
    except Exception as e:
        logger.error(f"Error fetching leaderboard: {e}", exc_info=True)
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
