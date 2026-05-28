"""API routes for event deck management."""

import logging

from flask import Blueprint, jsonify, request

from repositories.events import EventRepository
from utils.auth import is_admin, require_admin
from utils.formatting import format_event_name

logger = logging.getLogger(__name__)

events_bp = Blueprint("events", __name__)


@events_bp.route("/top-8-events")
def list_top8_events():
    """Return all top-8 event folders with metadata."""
    try:
        repo = EventRepository()
        events = repo.get_all_events()
        return jsonify({"events": events, "is_admin": is_admin()})
    except Exception as e:
        logger.exception("Error listing events: %s", e)
        return jsonify({"error": "Failed to load events"}), 500


@events_bp.route("/events/<event_folder>")
def get_event_detail(event_folder: str):
    """Return deck tables, card stats, and element charts for a single event."""
    try:
        repo = EventRepository()
        decks = repo.get_event_decks(event_folder)
        if decks is None:
            return jsonify({"error": "Event not found"}), 404

        stats = repo.get_event_stats(event_folder)
        element_stats = repo.get_event_element_stats(event_folder)
        description = repo.get_event_description(event_folder)

        return jsonify({
            "event_name": format_event_name(event_folder),
            "event_folder": event_folder,
            "description": description,
            "top8_decks": decks["top8_decks"],
            "all_decks": decks["all_decks"],
            "card_data": stats["card_data"] if stats else [],
            "element_stats": element_stats,
            "is_admin": is_admin(),
        })
    except Exception as e:
        logger.exception("Error loading event %s: %s", event_folder, e)
        return jsonify({"error": "Failed to load event data"}), 500


@events_bp.route("/events/<event_folder>/metadata", methods=["PUT"])
@require_admin
def update_event_metadata(event_folder):
    """Update display name and/or star rating for an event (admin only)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    name = data.get("name")
    rating = data.get("rating")
    description = data.get("description")

    if name is not None and (not isinstance(name, str) or not name.strip()):
        return jsonify({"success": False, "error": "Name must be a non-empty string"}), 400

    if rating is not None:
        if not isinstance(rating, int) or rating < 1 or rating > 3:
            return jsonify({"success": False, "error": "Rating must be 1, 2, or 3"}), 400

    if description is not None and not isinstance(description, str):
        return jsonify({"success": False, "error": "Description must be a string"}), 400

    repo = EventRepository()
    result = repo.update_event_metadata(
        event_folder,
        name=name.strip() if name else None,
        rating=rating,
        description=description.strip() if description else description,
    )

    status = 200 if result.get("success") else 400
    return jsonify(result), status


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


@events_bp.route("/events/reorder", methods=["POST"])
@require_admin
def reorder_events_list():
    """Reorder the events listing page (admin only)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    folder_order = data.get("order")
    if not isinstance(folder_order, list) or not all(isinstance(f, str) for f in folder_order):
        return jsonify({"success": False, "error": "order must be a list of folder name strings"}), 400

    repo = EventRepository()
    result = repo.save_event_order(folder_order)

    status = 200 if result.get("success") else 400
    return jsonify(result), status
