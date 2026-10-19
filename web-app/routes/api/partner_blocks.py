"""Partner (Play Sorcery Online) read access to player block lists.

Players manage their block list on their Summit profile. These endpoints let
a partner server read those blocks so it can keep blocked players apart,
the same way the Summit bot's matchmaking does. Read only; reasons are never
shared.
"""

import logging

from flask import Blueprint, jsonify, request

from repositories.blocked_users_repo import BlockedUsersRepository
from repositories.elo import EloRepository
from repositories.user_profiles import UserProfileRepository
from utils.api_auth import require_integration_api_key

logger = logging.getLogger(__name__)

partner_blocks_bp = Blueprint("partner_blocks", __name__)

MAX_ID_LENGTH = 64


def _clean_id(value) -> str | None:
    user_id = str(value or "").strip()
    if not user_id or len(user_id) > MAX_ID_LENGTH:
        return None
    return user_id


def _name_resolver():
    profile_repo = UserProfileRepository()
    elo_repo = EloRepository()
    cache: dict[str, str] = {}

    def resolve(uid: str) -> str:
        if uid not in cache:
            profile = profile_repo.get_by_user_id(uid)
            if profile:
                cache[uid] = profile["display_name"]
            else:
                cache[uid] = elo_repo.get_display_name(uid) or uid
        return cache[uid]

    return resolve


@partner_blocks_bp.route("/blocks/check", methods=["GET"])
@require_integration_api_key
def check_block():
    """Whether either of two players has blocked the other.

    Query params: user_a, user_b (Discord user IDs).
    """
    user_a = _clean_id(request.args.get("user_a"))
    user_b = _clean_id(request.args.get("user_b"))
    if not user_a or not user_b:
        return jsonify({"success": False, "error": "user_a and user_b are required"}), 400

    try:
        result = BlockedUsersRepository().get_block_between(user_a, user_b)
    except Exception as e:
        logger.error(f"Error checking block pair: {e}", exc_info=True)
        return jsonify({"success": False, "error": "Could not check blocks"}), 500

    return jsonify({
        "success": True,
        "user_a": user_a,
        "user_b": user_b,
        "blocked": result["a_blocked_b"] or result["b_blocked_a"],
        "a_blocked_b": result["a_blocked_b"],
        "b_blocked_a": result["b_blocked_a"],
    })


@partner_blocks_bp.route("/blocks/<user_id>", methods=["GET"])
@require_integration_api_key
def get_player_blocks(user_id):
    """Who a player has blocked, and who has blocked them."""
    user_id = _clean_id(user_id)
    if not user_id:
        return jsonify({"success": False, "error": "Invalid user id"}), 400

    try:
        blocks = BlockedUsersRepository().get_blocks_involving(user_id)
        resolve = _name_resolver()
        for section in ("blocked", "blocked_by"):
            for entry in blocks[section]:
                entry["display_name"] = resolve(entry["user_id"])
    except Exception as e:
        logger.error(f"Error fetching blocks for {user_id}: {e}", exc_info=True)
        return jsonify({"success": False, "error": "Could not load blocks"}), 500

    return jsonify({"success": True, "user_id": user_id, **blocks})
