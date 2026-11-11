"""GET /api/standings: every ladder, bracket and series, and where you stand."""

import logging

from flask import Blueprint, jsonify, session

from services.standings_hub import get_service

logger = logging.getLogger(__name__)

standings_hub_bp = Blueprint("standings_hub", __name__)


@standings_hub_bp.route("/standings", methods=["GET"])
def get_standings_hub():
    """Public. A logged-in player also gets their own place in each system."""
    viewer = str(session.get("user_id") or "") or None
    try:
        return jsonify({"success": True, **get_service().get_hub(viewer)}), 200
    except Exception as e:
        logger.error("Standings hub failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": "Could not load standings"}), 500
