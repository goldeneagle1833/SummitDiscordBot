"""Paper tournament finishes: profile badges from the Top 8 page's events.

GET /api/paper-finishes is what profiles read. The admin endpoints review how
each top cut result matched a Summit player and record the admin's calls
(link a name, mark "not this player", give one result to a player, switch an
event's badges on or off). See services/paper_finishes.py for the rules.
"""

import datetime
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


def _manual_fields(data):
    """(fields, error) for a hand-entered result from the request body."""
    user_id = paper_finishes.bare_id(data.get("user_id"))
    event = (data.get("event") or "").strip()
    event_date = (data.get("event_date") or "").strip() or None
    avatar = (data.get("avatar") or "").strip() or None
    try:
        place = int(data.get("place") or 1)
    except (TypeError, ValueError):
        place = 0
    if not user_id or not event:
        return None, "Pick a player and type the event name"
    if place not in paper_finishes.MANUAL_PLACES:
        return None, "Pick a placement"
    if len(event) > 120 or (avatar and len(avatar) > 60):
        return None, "Event or avatar name is too long"
    if event_date:
        try:
            datetime.date.fromisoformat(event_date)
        except ValueError:
            return None, "Date must look like 2026-11-01"
    return {"user_id": user_id, "event": event, "event_date": event_date, "place": place, "avatar": avatar}, None


@paper_finishes_bp.route("/admin/paper-finishes/manual", methods=["POST"])
@require_admin
def add_manual_result():
    """Add a result by hand for an event that is not on the Top 8 page."""
    fields, error = _manual_fields(_body())
    if error:
        return jsonify({"success": False, "error": error}), 400
    new_id = PaperLinkRepository().add_manual_finish(**fields, set_by=str(_admin()[1]))
    _log("paper_manual_added", target_id=fields["user_id"], target_name=fields["event"],
         details=paper_finishes.finish_label(fields["place"]))
    return jsonify({"success": True, "id": new_id}), 200


@paper_finishes_bp.route("/admin/paper-finishes/manual/<int:finish_id>", methods=["PUT"])
@require_admin
def edit_manual_result(finish_id):
    fields, error = _manual_fields(_body())
    if error:
        return jsonify({"success": False, "error": error}), 400
    if not PaperLinkRepository().update_manual_finish(finish_id, **fields, set_by=str(_admin()[1])):
        return jsonify({"success": False, "error": "That result no longer exists"}), 404
    _log("paper_manual_edited", target_id=fields["user_id"], target_name=fields["event"],
         details=paper_finishes.finish_label(fields["place"]))
    return jsonify({"success": True}), 200


@paper_finishes_bp.route("/admin/paper-finishes/manual/<int:finish_id>", methods=["DELETE"])
@require_admin
def delete_manual_result(finish_id):
    if not PaperLinkRepository().delete_manual_finish(finish_id):
        return jsonify({"success": False, "error": "That result no longer exists"}), 404
    _log("paper_manual_removed", target_name=str(finish_id))
    return jsonify({"success": True}), 200


# -- badges-only events from sorcerytcg.com ---------------------------------

BADGE_ONLY_CUTS = (2, 4, 8, 16, 32, 64, 128)


def _top_cut(value):
    try:
        cut = int(value)
    except (TypeError, ValueError):
        return None
    return cut if cut in BADGE_ONLY_CUTS else None


@paper_finishes_bp.route("/admin/paper-finishes/badge-only", methods=["POST"])
@require_admin
def import_badge_only_event():
    """Read a sorcerytcg.com event's standings for profile badges only.

    No decks are fetched and nothing goes on the Top 8 page. Importing an
    event that is already here reads its standings again and keeps the
    name and cut an admin set, unless new ones are given.
    """
    from services.curiosa import CuriosaService

    data = _body()
    event_url = (data.get("event_url") or "").strip()
    event_id = CuriosaService.get_event_id_from_url(event_url) if event_url else None
    if not event_id:
        return jsonify({"success": False, "error": "Paste a sorcerytcg.com event link (sorcerytcg.com/events/...)"}), 400
    name = (data.get("name") or "").strip()
    if len(name) > 120:
        return jsonify({"success": False, "error": "Event name is too long"}), 400
    top_cut = None
    if data.get("top_cut") not in (None, "", "auto"):
        top_cut = _top_cut(data.get("top_cut"))
        if not top_cut:
            return jsonify({"success": False, "error": "Pick a top cut size"}), 400

    folder = paper_finishes.top8_event_ids().get(event_id)
    if folder:
        return jsonify({
            "success": False,
            "error": f'This event is already on the Top 8 page as "{folder}", so it gives badges from there.',
        }), 409

    try:
        discovery = CuriosaService().fetch_event_deck_ids(event_url, with_decks=False)
    except Exception as e:
        logger.warning("Badges-only import of %s failed: %s", event_url, e)
        return jsonify({"success": False, "error": f"Could not read the event from sorcerytcg.com: {e}"}), 502

    standings = [
        {k: p.get(k) for k in ("registration_id", "display_name", "username", "standing", "wins", "losses", "draws")}
        for p in discovery.get("match_history") or []
    ]
    if not standings:
        return jsonify({"success": False, "error": "No standings found for this event yet (has it been played?)."}), 422

    repo = PaperLinkRepository()
    existing = next((e for e in repo.get_badge_only_events() if e["event_id"] == event_id), None)
    name = name or (existing or {}).get("name") or discovery.get("event_name") or "Imported event"
    top_cut = top_cut or (existing or {}).get("top_cut") or discovery.get("top_cut_size") or 8
    event_date = (existing or {}).get("event_date") or discovery.get("event_date")
    repo.save_badge_only_event(
        event_id, event_url, name, event_date, top_cut, standings, set_by=str(_admin()[1]),
    )
    _log("paper_badge_only_resynced" if existing else "paper_badge_only_imported",
         target_name=name, details=f"{event_id}, top {top_cut}")
    return jsonify({
        "success": True,
        "event_id": event_id,
        "name": name,
        "event_date": event_date,
        "top_cut": top_cut,
        "players": len(standings),
        "updated": bool(existing),
    }), 200


@paper_finishes_bp.route("/admin/paper-finishes/badge-only/<event_id>", methods=["PUT"])
@require_admin
def edit_badge_only_event(event_id):
    """Change a badges-only event's name, date or top cut size."""
    data = _body()
    name = (data.get("name") or "").strip()
    event_date = (data.get("event_date") or "").strip() or None
    top_cut = _top_cut(data.get("top_cut"))
    if not name or len(name) > 120:
        return jsonify({"success": False, "error": "Type the event name"}), 400
    if not top_cut:
        return jsonify({"success": False, "error": "Pick a top cut size"}), 400
    if event_date:
        try:
            datetime.date.fromisoformat(event_date)
        except ValueError:
            return jsonify({"success": False, "error": "Date must look like 2026-11-01"}), 400
    if not PaperLinkRepository().update_badge_only_event(event_id, name, event_date, top_cut, set_by=str(_admin()[1])):
        return jsonify({"success": False, "error": "That event is not here any more"}), 404
    _log("paper_badge_only_edited", target_name=name, details=f"{event_id}, top {top_cut}")
    return jsonify({"success": True}), 200


@paper_finishes_bp.route("/admin/paper-finishes/badge-only/<event_id>", methods=["DELETE"])
@require_admin
def delete_badge_only_event(event_id):
    """Remove a badges-only event and the badges it gave."""
    if not PaperLinkRepository().delete_badge_only_event(event_id, paper_finishes.badge_only_folder(event_id)):
        return jsonify({"success": False, "error": "That event is not here any more"}), 404
    _log("paper_badge_only_removed", target_name=event_id)
    return jsonify({"success": True}), 200
