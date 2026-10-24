"""API routes for site-hosted brackets."""

import logging
from functools import wraps

from flask import Blueprint, jsonify, request, session

from repositories.brackets import BracketRepository
from repositories.user_profiles import UserProfileRepository
from services.brackets import BracketError, BracketService, is_community
from services.ticket_holders import TicketHolderError, is_configured, sync_roster
from utils.auth import is_admin, require_admin, require_auth
from utils.bracket_organizers import is_bracket_organizer

logger = logging.getLogger(__name__)

brackets_bp = Blueprint("brackets", __name__)
service = BracketService()


def _current_user_id() -> str:
    return str(session.get("user_id", ""))


def can_manage(bracket: dict | None) -> bool:
    """Admins run every bracket; an organizer runs the community ones they made."""
    if not bracket:
        return False
    if is_admin():
        return True
    user_id = _current_user_id()
    return bool(
        user_id
        and is_community(bracket)
        and str(bracket.get("created_by") or "") == user_id
        and is_bracket_organizer()
    )


def require_bracket_organizer(f):
    """Admins, or players with the Discord role that lets them run brackets."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_bracket_organizer():
            return jsonify({"success": False, "error": "Bracket organizer access required"}), 403
        return f(*args, **kwargs)

    decorated_function._auth_required = True
    return decorated_function


def require_bracket_manager(f):
    """Admins, or the organizer who created this (community) bracket."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        bracket = service.get_bracket_by_slug(kwargs.get("slug"))
        if not bracket:
            if is_admin():
                return f(*args, **kwargs)  # Lets the view give its own 404
            return jsonify({"success": False, "error": "Bracket not found"}), 404
        if not can_manage(bracket):
            return jsonify({"success": False, "error": "You can't manage this bracket"}), 403
        return f(*args, **kwargs)

    decorated_function._auth_required = True
    return decorated_function


def _own_match_refused(slug: str, match_no: int):
    """An organizer can't settle a match they are playing in; admins can."""
    if is_admin():
        return None
    bracket = service.get_bracket_by_slug(slug)
    match = BracketRepository().get_match(bracket["bracket_id"], int(match_no)) if bracket else None
    if match and _current_user_id() in (
        str(match.get("p1_user_id") or ""),
        str(match.get("p2_user_id") or ""),
    ):
        return (
            jsonify(
                {
                    "success": False,
                    "error": "You're playing in this match - report it like any other player",
                }
            ),
            403,
        )
    return None


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
        logger.error("Failed to list brackets: %s", e, exc_info=True)
        return jsonify({"success": False, "error": "Could not load brackets"}), 500


@brackets_bp.route("/brackets/<slug>", methods=["GET"])
def get_bracket(slug):
    detail = service.get_bracket_detail(
        slug, viewer_id=_current_user_id(), is_admin=is_admin()
    )
    if not detail:
        return jsonify({"success": False, "error": "Bracket not found"}), 404
    detail["viewer_can_manage"] = can_manage(detail["bracket"])
    return jsonify({"success": True, **detail}), 200


@brackets_bp.route("/brackets/marks", methods=["GET"])
def get_bracket_marks():
    """Postseason honours keyed by user_id, drawn beside player names."""
    try:
        return jsonify({"success": True, "marks": service.get_player_marks()}), 200
    except Exception as e:
        logger.error("Failed to load bracket marks: %s", e, exc_info=True)
        # A leaderboard should still render without its decorations.
        return jsonify({"success": True, "marks": {}}), 200


@brackets_bp.route("/brackets/player/<path:user_id>", methods=["GET"])
def get_player_postseason(user_id):
    try:
        return jsonify(
            {"success": True, "brackets": service.get_player_postseason(user_id)}
        ), 200
    except Exception as e:
        logger.error("Failed to load postseason for %s: %s", user_id, e, exc_info=True)
        return jsonify({"success": True, "brackets": []}), 200


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


@brackets_bp.route("/brackets/<slug>/decks", methods=["GET"])
def get_bracket_decks(slug):
    """Who has submitted a deck, and the ones the viewer is allowed to see."""
    roster = service.get_deck_roster(slug, viewer_id=_current_user_id(), is_admin=is_admin())
    if roster is None:
        return jsonify({"success": False, "error": "Bracket not found"}), 404
    return jsonify({"success": True, **roster}), 200


@brackets_bp.route("/brackets/<slug>/decks/<int:seed>", methods=["GET"])
def get_bracket_deck(slug, seed):
    try:
        result = service.get_deck(
            slug, seed, viewer_id=_current_user_id(), is_admin=is_admin()
        )
    except BracketError as e:
        return jsonify({"success": False, "error": str(e)}), 403
    return jsonify({"success": True, **result}), 200


@brackets_bp.route("/brackets/<slug>/deck", methods=["POST"])
@require_auth
def submit_bracket_deck(slug):
    """A player attaches their own decklist."""
    data = request.get_json() or {}
    try:
        result = service.submit_deck(slug, data.get("deck_url"), _current_user_id())
    except BracketError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, **result}), 200


@brackets_bp.route("/brackets/<slug>/matches/<int:match_no>/table", methods=["POST"])
@require_auth
def open_match_table(slug, match_no):
    """Open the Sorcery Online table for this pairing, both decks preloaded."""
    try:
        result = service.open_table(slug, match_no, _current_user_id())
    except BracketError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, **result}), 200


# -- Admin --------------------------------------------------------


@brackets_bp.route("/admin/brackets", methods=["GET"])
@require_bracket_organizer
def admin_list_brackets():
    """Every bracket for admins; an organizer (or ?mine=1) sees their own."""
    mine = not is_admin() or request.args.get("mine") == "1"
    brackets = service.list_brackets(
        include_drafts=True, organizer_id=_current_user_id() if mine else None
    )
    return jsonify({"success": True, "brackets": brackets}), 200


@brackets_bp.route("/brackets/organizer/search-players", methods=["GET"])
@require_bracket_organizer
def organizer_search_players():
    """Players an organizer can add to a bracket: site name and id only."""
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"success": False, "error": "Query must be at least 2 characters"}), 400
    users = [
        {
            "user_id": u.get("user_id"),
            "display_name": u.get("display_name"),
            "avatar": u.get("avatar"),
            "provider": u.get("provider"),
        }
        for u in UserProfileRepository().search_users(q, limit=10)
    ]
    return jsonify({"success": True, "users": users}), 200


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
@require_bracket_organizer
def admin_create_bracket():
    data = request.get_json() or {}
    # Organizers only make community brackets; an admin makes one by asking.
    kind = "community" if not is_admin() else (data.get("kind") or "official")
    try:
        result = service.create_bracket(
            name=data.get("name"),
            size=data.get("size", 16),
            source=data.get("source", "ticket_holders"),
            created_by=_current_user_id(),
            confirm_hours=int(data.get("confirm_hours", 48)),
            set_name=data.get("set_name"),
            format=data.get("format"),
            kind=kind,
        )
    except BracketError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Invalid bracket settings"}), 400
    return jsonify({"success": True, **result}), 201


@brackets_bp.route("/admin/brackets/<slug>", methods=["GET"])
@require_bracket_manager
def admin_get_bracket(slug):
    # An organizer runs the bracket but doesn't get to see hidden decklists.
    detail = service.get_bracket_detail(
        slug, include_drafts=True, viewer_id=_current_user_id(), is_admin=is_admin()
    )
    if not detail:
        return jsonify({"success": False, "error": "Bracket not found"}), 404
    return jsonify({"success": True, **detail}), 200


@brackets_bp.route("/admin/brackets/<slug>/preview", methods=["GET"])
@require_bracket_manager
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
@require_bracket_manager
def admin_update_bracket(slug):
    bracket, error = _resolve(slug)
    if error:
        return error

    data = request.get_json() or {}
    if not service.update_bracket(bracket["bracket_id"], data):
        return jsonify({"success": False, "error": "Nothing to update"}), 400
    return jsonify({"success": True}), 200


@brackets_bp.route("/admin/brackets/<slug>/entrants", methods=["PUT"])
@require_bracket_manager
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
@require_bracket_manager
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
@require_bracket_manager
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
@require_bracket_manager
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
@require_bracket_manager
def admin_unpublish(slug):
    bracket, error = _resolve(slug)
    if error:
        return error

    try:
        service.unpublish(bracket["bracket_id"])
    except BracketError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True}), 200


@brackets_bp.route("/admin/brackets/<slug>/swap", methods=["POST"])
@require_bracket_manager
def admin_swap_players(slug):
    """Re-pair a published bracket by trading two players' seats."""
    data = request.get_json() or {}
    try:
        result = service.swap_players(slug, int(data.get("seed")), int(data.get("with_seed")))
    except BracketError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "seed and with_seed are required"}), 400
    return jsonify({"success": True, **result}), 200


@brackets_bp.route("/admin/brackets/<slug>/top8", methods=["POST"])
@require_admin
def admin_publish_to_top8(slug):
    """Write (or rewrite) a finished bracket's event on the Top 8 page."""
    bracket, error = _resolve(slug)
    if error:
        return error

    try:
        result = service.publish_to_top8(bracket["bracket_id"])
    except BracketError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, **result}), 200


@brackets_bp.route("/admin/brackets/<slug>/matches/<int:match_no>/result", methods=["POST"])
@require_bracket_manager
def admin_set_result(slug, match_no):
    refused = _own_match_refused(slug, match_no)
    if refused:
        return refused
    data = request.get_json() or {}
    try:
        result = service.set_result(
            slug, match_no, data.get("winner_user_id"), _current_user_id()
        )
    except BracketError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, **result}), 200


@brackets_bp.route("/admin/brackets/<slug>/matches/<int:match_no>/reset", methods=["POST"])
@require_bracket_manager
def admin_reset_match(slug, match_no):
    refused = _own_match_refused(slug, match_no)
    if refused:
        return refused
    try:
        result = service.reset_match(slug, match_no)
    except BracketError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, **result}), 200


@brackets_bp.route("/admin/brackets/<slug>/decks", methods=["POST"])
@require_bracket_manager
def admin_submit_deck(slug):
    """Add a decklist on a player's behalf."""
    data = request.get_json() or {}
    seed = data.get("seed")
    if seed is None:
        return jsonify({"success": False, "error": "seed is required"}), 400

    try:
        result = service.submit_deck(
            slug, data.get("deck_url"), _current_user_id(), seed=int(seed), is_admin=True
        )
    except BracketError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Invalid seed"}), 400
    return jsonify({"success": True, **result}), 200


@brackets_bp.route("/admin/brackets/<slug>/decks/<int:seed>", methods=["DELETE"])
@require_bracket_manager
def admin_delete_deck(slug, seed):
    try:
        removed = service.delete_deck(slug, seed)
    except BracketError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    if not removed:
        return jsonify({"success": False, "error": "No deck to remove"}), 404
    return jsonify({"success": True}), 200


@brackets_bp.route("/admin/brackets/<slug>/matches/<int:match_no>/replay", methods=["POST"])
@require_bracket_manager
def admin_set_replay(slug, match_no):
    data = request.get_json() or {}
    try:
        result = service.set_replay(
            slug, match_no, data.get("replay_url"), _current_user_id()
        )
    except BracketError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, **result}), 200


@brackets_bp.route("/admin/brackets/<slug>/matches/<int:match_no>/replay", methods=["DELETE"])
@require_bracket_manager
def admin_clear_replay(slug, match_no):
    try:
        removed = service.clear_replay(slug, match_no)
    except BracketError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    if not removed:
        return jsonify({"success": False, "error": "No replay to remove"}), 404
    return jsonify({"success": True}), 200


@brackets_bp.route("/admin/brackets/<slug>", methods=["DELETE"])
@require_bracket_manager
def admin_delete_bracket(slug):
    bracket, error = _resolve(slug)
    if error:
        return error

    service.delete_bracket(bracket["bracket_id"])
    return jsonify({"success": True}), 200
