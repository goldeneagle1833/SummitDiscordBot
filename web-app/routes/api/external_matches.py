"""External match reporting API routes."""

import logging

from flask import Blueprint, jsonify, request

from services.external_match import ExternalMatchService
from utils.auth import require_api_key

logger = logging.getLogger(__name__)

external_matches_bp = Blueprint("external_matches", __name__)


@external_matches_bp.route("/report-external-match", methods=["POST"])
@require_api_key
def report_external_match():
    """
    API endpoint for external applications to report match results.
    Updates unified ELO in overall_standings and writes to match_records.
    Requires API key authentication.
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Request body must be JSON", "success": False}), 400

        # Validate required fields
        required = ["winner_id", "loser_id", "winner_deck_url", "loser_deck_url", "source"]
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({
                "error": f"Missing required fields: {', '.join(missing)}",
                "success": False,
            }), 400

        winner_id = str(data["winner_id"]).strip()
        loser_id = str(data["loser_id"]).strip()

        if winner_id == loser_id:
            return jsonify({
                "error": "winner_id and loser_id must be different",
                "success": False,
            }), 400

        winner_deck_url = str(data["winner_deck_url"]).strip()
        loser_deck_url = str(data["loser_deck_url"]).strip()
        source = str(data["source"]).strip()

        if not source:
            return jsonify({"error": "source cannot be empty", "success": False}), 400

        # Optional fields
        winner_name = str(data["winner_name"]).strip() if data.get("winner_name") else None
        loser_name = str(data["loser_name"]).strip() if data.get("loser_name") else None
        match_comment = str(data["match_comment"]).strip() if data.get("match_comment") else None

        winner_went_first = None
        if data.get("winner_went_first") is not None:
            winner_went_first = "y" if data["winner_went_first"] else "n"

        match_time = None
        if data.get("match_time") is not None:
            match_time = int(data["match_time"])

        # Process via service
        service = ExternalMatchService()
        result = service.report_match(
            winner_id=winner_id,
            loser_id=loser_id,
            winner_deck_url=winner_deck_url,
            loser_deck_url=loser_deck_url,
            source=source,
            winner_name=winner_name,
            loser_name=loser_name,
            winner_went_first=winner_went_first,
            match_time=match_time,
            match_comment=match_comment,
        )

        return jsonify({
            "success": True,
            "message": "External match recorded successfully",
            **result,
        })

    except ValueError as e:
        return jsonify({"error": f"Invalid data: {str(e)}", "success": False}), 400
    except Exception as e:
        logger.error(f"Error recording external match: {e}", exc_info=True)
        return jsonify({"error": "Internal server error", "success": False}), 500
