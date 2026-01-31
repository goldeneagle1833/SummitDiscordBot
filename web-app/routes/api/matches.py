"""Match history API routes."""

import logging
from flask import Blueprint, jsonify, request

from services.match import MatchService

logger = logging.getLogger(__name__)

matches_bp = Blueprint("matches", __name__)


@matches_bp.route("/match-history/available-dates")
def available_dates():
    """Get dates that have match data."""
    try:
        service = MatchService()
        dates = service.get_available_dates()
        return jsonify(dates)
    except Exception as e:
        logger.error(f"Error fetching available dates: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@matches_bp.route("/match-history")
def match_history():
    """Get match history, optionally filtered by date."""
    try:
        selected_date = request.args.get("date")
        service = MatchService()
        matches = service.get_match_history(date=selected_date)
        return jsonify(matches)
    except Exception as e:
        logger.error(f"Error fetching match history: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
