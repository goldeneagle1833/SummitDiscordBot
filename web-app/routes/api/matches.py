"""Match history API routes."""

import logging
import re
from flask import Blueprint, jsonify, request

from services.match import MatchService
from utils.auth import require_api_key

logger = logging.getLogger(__name__)

matches_bp = Blueprint("matches", __name__)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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


@matches_bp.route("/matches/date-range")
@require_api_key
def matches_date_range():
    """Get matches between two dates (inclusive).

    Query params:
        start_date (required): YYYY-MM-DD
        end_date (required): YYYY-MM-DD
    """
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    if not start_date or not end_date:
        return jsonify({"error": "start_date and end_date query params are required"}), 400

    if not _DATE_RE.match(start_date) or not _DATE_RE.match(end_date):
        return jsonify({"error": "Dates must be in YYYY-MM-DD format"}), 400

    if start_date > end_date:
        return jsonify({"error": "start_date must be before or equal to end_date"}), 400

    try:
        service = MatchService()
        matches = service.get_matches_by_date_range(start_date, end_date)
        return jsonify({
            "start_date": start_date,
            "end_date": end_date,
            "total_matches": len(matches),
            "matches": matches,
        })
    except Exception as e:
        logger.error(f"Error fetching matches by date range: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


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
