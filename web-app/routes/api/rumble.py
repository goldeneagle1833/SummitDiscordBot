"""Rumble API routes."""

import logging

from flask import Blueprint, jsonify, request

from repositories.matches import MatchRepository

logger = logging.getLogger(__name__)

rumble_bp = Blueprint("rumble", __name__)


@rumble_bp.route("/rumble")
def get_rumble():
    """Return rumble standings and recent matches."""
    try:
        repo = MatchRepository()
        limit = request.args.get("limit", 50, type=int)
        standings = repo.get_rumble_standings()
        matches = repo.get_rumble_matches(limit=limit)
        return jsonify({
            "standings": standings,
            "matches": matches,
            "total_matches": sum(p["wins"] + p["losses"] for p in standings) // 2 if standings else 0,
        })
    except Exception as e:
        logger.error(f"Error fetching rumble data: {e}")
        return jsonify({"error": str(e)}), 500
