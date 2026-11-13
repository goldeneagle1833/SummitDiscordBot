"""Menu new-content dots: what's new on each page, and what this person has seen."""

import logging

from flask import Blueprint, jsonify, request, session

from repositories.nav_seen import NavSeenRepository
from services.new_content import PAGE_SOURCES, get_new_content

nav_bp = Blueprint("nav", __name__)
logger = logging.getLogger(__name__)


@nav_bp.route("/nav/new-content", methods=["GET"])
def get_new_content():
    """Latest content time per menu page (cached site-wide) plus, when logged in,
    when this person last opened each page. Logged-out visitors track "seen"
    in their browser."""
    data = get_new_content()
    latest = data["latest"]
    seen = None
    user_id = session.get("user_id")
    if user_id is not None and latest:
        try:
            seen = NavSeenRepository().get_seen(str(user_id))
        except Exception:
            logger.warning("nav seen lookup failed", exc_info=True)
            seen = {}
    return jsonify({"latest": latest, "notes": data["notes"], "seen": seen})


@nav_bp.route("/nav/seen", methods=["POST"])
def mark_seen():
    """Record that the logged-in person opened these menu pages."""
    user_id = session.get("user_id")
    if user_id is None:
        return jsonify({"error": "Authentication required"}), 401
    data = request.get_json(silent=True) or {}
    pages = data.get("pages")
    if not isinstance(pages, list) or not pages:
        return jsonify({"error": "pages must be a non-empty list"}), 400
    pages = [p for p in dict.fromkeys(pages) if isinstance(p, str) and p in PAGE_SOURCES]
    if not pages:
        return jsonify({"error": "unknown page"}), 400
    seen_at = NavSeenRepository().mark_seen(str(user_id), pages)
    return jsonify({"success": True, "seen_at": seen_at, "pages": pages})
