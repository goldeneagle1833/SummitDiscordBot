"""Paper tournament finishes: profile badges from the Top 8 page's events.

GET /api/paper-finishes is what profiles read. The admin endpoints review how
each top cut result matched a Summit player and record the admin's calls
(link a name, mark "not this player", give one result to a player, switch an
event's badges on or off). See services/paper_finishes.py for the rules.
"""

import logging

from flask import Blueprint, jsonify, request, session

from repositories.audit import AuditRepository
from repositories.paper_links import PaperLinkRepository
from services import paper_finishes
from utils.auth import require_admin

logger = logging.getLogger(__name__)

paper_finishes_bp = Blueprint("paper_finishes", __name__)


def _admin():
    return session.get("user_id", 0), session.get("username", "API/localhost")


def _log(action, target_id=None, target_name=None, details=None):
    admin_id, admin_name = _admin()
    try:
        AuditRepository().log_action(
            admin_id, admin_name, action, target_id=target_id,
            target_name=target_name, details=details,
        )
    except Exception as e:
        logger.warning("Could not write audit entry for %s: %s", action, e)


def _body():
    return request.get_json(silent=True) or {}


@paper_finishes_bp.route("/paper-finishes", methods=["GET"])
def get_paper_finishes():
    """Every Summit player's paper tournament finishes, keyed by player id."""
    try:
        return jsonify({"success": True, "finishes": paper_finishes.get_finishes_by_player()}), 200
    except Exception as e:
        logger.error("Failed to load paper finishes: %s", e, exc_info=True)
        # Profiles should still render without their decorations.
        return jsonify({"success": True, "finishes": {}}), 200


@paper_finishes_bp.route("/paper-finishes/event/<folder>", methods=["GET"])
def get_event_profiles(folder):
    """The Summit profile each Top 8 entry of one event matched, for its page."""
    try:
        return jsonify({"success": True, "entries": paper_finishes.event_profiles(folder)}), 200
    except Exception as e:
        logger.error("Failed to load event profiles for %s: %s", folder, e, exc_info=True)
        return jsonify({"success": True, "entries": []}), 200


@paper_finishes_bp.route("/admin/paper-finishes", methods=["GET"])
@require_admin
def admin_paper_finishes():
    try:
        return jsonify({"success": True, **paper_finishes.admin_review()}), 200
    except Exception as e:
        logger.error("Failed to build paper finishes review: %s", e, exc_info=True)
        return jsonify({"success": False, "error": "Could not load the results"}), 500


@paper_finishes_bp.route("/admin/paper-finishes/link", methods=["POST"])
@require_admin
def link_paper_name():
    """Link a paper name to a player, or (status=rejected) mark it not them."""
    data = _body()
    paper_name = (data.get("paper_name") or "").strip()
    user_id = paper_finishes.bare_id(data.get("user_id"))
    key = paper_finishes.name_key(paper_name)
    if not key or not user_id:
        return jsonify({"success": False, "error": "paper_name and user_id are required"}), 400
    repo = PaperLinkRepository()
    if data.get("status") == "rejected":
        repo.reject_name(key, paper_name, user_id, set_by=str(_admin()[1]))
        _log("paper_name_rejected", target_id=user_id, target_name=paper_name)
    else:
        repo.link_name(key, paper_name, user_id, set_by=str(_admin()[1]))
        _log("paper_name_linked", target_id=user_id, target_name=paper_name)
    return jsonify({"success": True}), 200


@paper_finishes_bp.route("/admin/paper-finishes/unlink", methods=["POST"])
@require_admin
def unlink_paper_name():
    """Forget a link or a "not them", so the automatic rules apply again."""
    data = _body()
    key = paper_finishes.name_key(data.get("name_key") or data.get("paper_name"))
    user_id = paper_finishes.bare_id(data.get("user_id"))
    if not key or not user_id:
        return jsonify({"success": False, "error": "name_key and user_id are required"}), 400
    PaperLinkRepository().clear_name(key, user_id)
    _log("paper_name_unlinked", target_id=user_id, target_name=key)
    return jsonify({"success": True}), 200


@paper_finishes_bp.route("/admin/paper-finishes/assign", methods=["POST"])
@require_admin
def assign_paper_result():
    """Give one result to a player (user_id), to nobody (""), or clear (clear=true)."""
    data = _body()
    folder = (data.get("folder") or "").strip()
    deck_id = (data.get("deck_id") or "").strip()
    if not folder or not deck_id:
        return jsonify({"success": False, "error": "folder and deck_id are required"}), 400
    repo = PaperLinkRepository()
    if data.get("clear"):
        repo.clear_assignment(folder, deck_id)
        _log("paper_result_cleared", target_name=f"{folder} / {deck_id}")
    else:
        user_id = paper_finishes.bare_id(data.get("user_id"))
        repo.assign_result(folder, deck_id, user_id, set_by=str(_admin()[1]))
        _log("paper_result_assigned", target_id=user_id or None, target_name=f"{folder} / {deck_id}")
    return jsonify({"success": True}), 200


@paper_finishes_bp.route("/admin/paper-finishes/event", methods=["POST"])
@require_admin
def set_paper_event():
    """Switch an event's profile badges on or off."""
    data = _body()
    folder = (data.get("folder") or "").strip()
    if not folder or "awards_badges" not in data:
        return jsonify({"success": False, "error": "folder and awards_badges are required"}), 400
    PaperLinkRepository().set_event_awards(folder, bool(data["awards_badges"]), set_by=str(_admin()[1]))
    _log("paper_event_badges", target_name=folder, details="on" if data["awards_badges"] else "off")
    return jsonify({"success": True}), 200
