"""API routes for event deck management."""

import logging

from flask import Blueprint, jsonify, request

from repositories.events import EventRepository
from utils.auth import require_admin

logger = logging.getLogger(__name__)

events_bp = Blueprint("events", __name__)


@events_bp.route("/events/<event_folder>/reorder", methods=["POST"])
@require_admin
def reorder_event_decks(event_folder):
    """Reorder decks in an event's JSON file (admin only)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    table_type = data.get("table")
    if table_type not in ("top8", "all"):
        return jsonify({"success": False, "error": "table must be 'top8' or 'all'"}), 400

    new_order = data.get("order")
    if not isinstance(new_order, list) or not all(isinstance(i, int) for i in new_order):
        return jsonify({"success": False, "error": "order must be a list of integers"}), 400

    repo = EventRepository()
    result = repo.reorder_event_decks(event_folder, table_type, new_order)

    status = 200 if result.get("success") else 400
    return jsonify(result), status
