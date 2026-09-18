"""API routes for site-hosted brackets."""

import logging

from flask import Blueprint, jsonify, request, session

from repositories.brackets import BracketRepository
from services.brackets import BracketError, BracketService
from services.ticket_holders import TicketHolderError, is_configured, sync_roster
from utils.auth import require_admin, require_auth

logger = logging.getLogger(__name__)

brackets_bp = Blueprint("brackets", __name__)
service = BracketService()


def _current_user_id() -> str:
    return str(session.get("user_id", ""))


def _resolve(slug: str):
    """Look up a bracket by slug, or return a 404 response."""
    bracket = service.get_bracket_by_slug(slug)
    if not bracket:
        return None, (jsonify({"success": False, "error": "Bracket not found"}), 404)
    return bracket, None


# -- Public reads -------------------------------------------------


@brackets_bp.route("/brackets", methods=["GET"])
def list_brackets():
    try:
        return jsonify({"success": True, "brackets": service.list_brackets()}), 200
    except Exception as e:
        logger.error(f"Failed to list brackets: {e}")
        return jsonify({"success": False, "error": "Could not load brackets"}), 500


@brackets_bp.route("/brackets/<slug>", methods=["GET"])
def get_bracket(slug):
    detail = service.get_bracket_detail(slug)
    if not detail:
        return jsonify({"success": False, "error": "Bracket not found"}), 404

    # Tell the viewer what, if anything, this match needs from them.
    user_id = _current_user_id()
    if user_id:
        for round_data in detail["rounds"]:
            for match in round_data["matches"]:
                match["viewer_is_player"] = user_id in (
                    str(match.get("p1_user_id") or ""),
                    str(match.get("p2_user_id") or ""),
                )
                match["viewer_can_report"] = (
                    match["viewer_is_player"]
                    and match["state"] == "pending"
                    and match["playable"]
                )
                match["viewer_can_confirm"] = (
                    match["viewer_is_player"]
                    and match["state"] == "reported"
                    and str(match.get("reported_by") or "") != user_id
                )

    return jsonify({"success": True, **detail}), 200


# -- Player actions -----------------------------------------------


@brackets_bp.route("/brackets/my-matches", methods=["GET"])
@require_auth
def my_matches():
    matches = service.get_player_open_matches(_current_user_id())
    return jsonify({"success": True, "matches": matches}), 200


@brackets_bp.route("/brackets/<slug>/matches/<int:match_no>/report", methods=["POST"])
@require_auth
def report_match(slug, match_no):
    data = request.get_json() or {}
    winner_user_id = data.get("winner_user_id")
    if not winner_user_id:
        return jsonify({"success": False, "error": "winner_user_id is required"}), 400

    try:
        result = service.report_result(slug, match_no, _current_user_id(), winner_user_id)
    except BracketError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, **result}), 200


@brackets_bp.route("/brackets/<slug>/matches/<int:match_no>/confirm", methods=["POST"])
@require_auth
def confirm_match(slug, match_no):
    data = request.get_json() or {}
    agree = data.get("agree", True)

    try:
        result = service.confirm_result(slug, match_no, _current_user_id(), bool(agree))
    except BracketError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, **result}), 200


# -- Admin --------------------------------------------------------


@brackets_bp.route("/admin/brackets", methods=["GET"])
@require_admin
def admin_list_brackets():
    return jsonify({"success": True, "brackets": service.list_brackets(include_drafts=True)}), 200


@brackets_bp.route("/admin/brackets/seed-pool", methods=["GET"])
@require_admin
def admin_seed_pool():
    source = request.args.get("source", "ticket_holders")
    pool = service.get_seed_pool(source)
    pool["ticket_sync_configured"] = is_configured()
    return jsonify({"success": True, **pool}), 200


@brackets_bp.route("/admin/brackets/sync-tickets", methods=["POST"])
@require_admin
def admin_sync_tickets():
    try:
        result = sync_roster(BracketRepository())
    except TicketHolderError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, **result}), 200


@brackets_bp.route("/admin/brackets", methods=["POST"])
@require_admin
def admin_create_bracket():
    data = request.get_json() or {}
    try:
        result = service.create_bracket(
            name=data.get("name"),
            size=data.get("size", 16),
            source=data.get("source", "ticket_holders"),
            created_by=_current_user_id(),
            confirm_hours=int(data.get("confirm_hours", 48)),
        )
    except BracketError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Invalid bracket settings"}), 400
    return jsonify({"success": True, **result}), 201


@brackets_bp.route("/admin/brackets/<slug>", methods=["GET"])
@require_admin
def admin_get_bracket(slug):
    detail = service.get_bracket_detail(slug, include_drafts=True)
    if not detail:
        return jsonify({"success": False, "error": "Bracket not found"}), 404
    return jsonify({"success": True, **detail}), 200


@brackets_bp.route("/admin/brackets/<slug>/preview", methods=["GET"])
@require_admin
def admin_preview_bracket(slug):
    """The tree this draft's current seeding would produce, unsaved."""
    bracket, error = _resolve(slug)
    if error:
        return error

    try:
        result = service.preview(bracket["bracket_id"])
    except BracketError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, **result}), 200


@brackets_bp.route("/admin/brackets/<slug>", methods=["PATCH"])
@require_admin
def admin_update_bracket(slug):
    bracket, error = _resolve(slug)
    if error:
        return error

    data = request.get_json() or {}
    if not service.update_bracket(bracket["bracket_id"], data):
        return jsonify({"success": False, "error": "Nothing to update"}), 400
    return jsonify({"success": True}), 200


@brackets_bp.route("/admin/brackets/<slug>/entrants", methods=["PUT"])
@require_admin
def admin_set_entrants(slug):
    bracket, error = _resolve(slug)
    if error:
        return error

    data = request.get_json() or {}
    try:
        result = service.set_entrants(bracket["bracket_id"], data.get("entrants") or [])
    except BracketError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, **result}), 200


@brackets_bp.route("/admin/brackets/<slug>/shuffle", methods=["POST"])
@require_admin
def admin_shuffle(slug):
    bracket, error = _resolve(slug)
    if error:
        return error

    try:
        result = service.shuffle_seeds(bracket["bracket_id"])
    except BracketError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, **result}), 200


@brackets_bp.route("/admin/brackets/<slug>/move", methods=["POST"])
@require_admin
def admin_move_entrant(slug):
    bracket, error = _resolve(slug)
    if error:
        return error

    data = request.get_json() or {}
    try:
        result = service.move_entrant(
            bracket["bracket_id"], int(data.get("seed")), int(data.get("to_seed"))
        )
    except BracketError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "seed and to_seed are required"}), 400
    return jsonify({"success": True, **result}), 200


@brackets_bp.route("/admin/brackets/<slug>/publish", methods=["POST"])
@require_admin
def admin_publish(slug):
    bracket, error = _resolve(slug)
    if error:
        return error

    try:
        result = service.publish(bracket["bracket_id"])
    except BracketError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, **result}), 200


@brackets_bp.route("/admin/brackets/<slug>/unpublish", methods=["POST"])
@require_admin
def admin_unpublish(slug):
    bracket, error = _resolve(slug)
    if error:
        return error

    try:
        service.unpublish(bracket["bracket_id"])
    except BracketError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True}), 200


@brackets_bp.route("/admin/brackets/<slug>/matches/<int:match_no>/result", methods=["POST"])
@require_admin
def admin_set_result(slug, match_no):
    data = request.get_json() or {}
    try:
        result = service.set_result(
            slug, match_no, data.get("winner_user_id"), _current_user_id()
        )
    except BracketError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, **result}), 200


@brackets_bp.route("/admin/brackets/<slug>/matches/<int:match_no>/reset", methods=["POST"])
@require_admin
def admin_reset_match(slug, match_no):
    try:
        result = service.reset_match(slug, match_no)
    except BracketError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, **result}), 200


@brackets_bp.route("/admin/brackets/<slug>", methods=["DELETE"])
@require_admin
def admin_delete_bracket(slug):
    bracket, error = _resolve(slug)
    if error:
        return error

    service.delete_bracket(bracket["bracket_id"])
    return jsonify({"success": True}), 200
