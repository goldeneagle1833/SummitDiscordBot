"""Partner (Play Sorcery Online) endpoints for player blocks and reports.

Players manage their block list on their Summit profile. The block endpoints
let a partner server read those blocks so it can keep blocked players apart,
the same way the Summit bot's matchmaking does. Read only; reasons are never
shared.

The report endpoint is the partner's version of the bot's Report Player
button: reports land in the same admin list, tagged with their source.
"""

import logging

from flask import Blueprint, jsonify, request

from repositories.blocked_users_repo import BlockedUsersRepository
from repositories.elo import EloRepository
from repositories.player_reports_repo import REPORT_REASONS, PlayerReportsRepository
from repositories.user_profiles import UserProfileRepository
from utils.api_auth import require_integration_api_key

logger = logging.getLogger(__name__)

partner_blocks_bp = Blueprint("partner_blocks", __name__)

MAX_ID_LENGTH = 64
MAX_DETAILS_LENGTH = 1000
MAX_NAME_LENGTH = 100
REPORT_SOURCE = "sorcery-online"


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


@partner_blocks_bp.route("/player-reports", methods=["POST"])
@require_integration_api_key
def create_player_report():
    """File a Report Player report from a partner match.

    Body: reporter_id, reported_id (Discord user IDs), reasons (list of
    REPORT_REASONS values) and/or details; optional reporter_name,
    reported_name, pairing_id, match_type.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "error": "Request body must be JSON"}), 400

    reporter_id = _clean_id(data.get("reporter_id"))
    reported_id = _clean_id(data.get("reported_id"))
    if not reporter_id or not reported_id:
        return jsonify({"success": False, "error": "reporter_id and reported_id are required"}), 400
    if reporter_id == reported_id:
        return jsonify({"success": False, "error": "A player cannot report themselves"}), 400

    reasons = data.get("reasons") or []
    if not isinstance(reasons, list):
        return jsonify({"success": False, "error": "reasons must be a list"}), 400
    reasons = list(dict.fromkeys(str(r).strip() for r in reasons))
    unknown = [r for r in reasons if r not in REPORT_REASONS]
    if unknown:
        return jsonify({
            "success": False,
            "error": f"Unknown reasons: {', '.join(unknown)}",
            "allowed_reasons": REPORT_REASONS,
        }), 400

    details = str(data.get("details") or "").strip()
    if len(details) > MAX_DETAILS_LENGTH:
        return jsonify({
            "success": False,
            "error": f"details must be {MAX_DETAILS_LENGTH} characters or fewer",
        }), 400
    if not reasons and not details:
        return jsonify({"success": False, "error": "Give at least one reason or some details"}), 400

    pairing_id = data.get("pairing_id")
    if pairing_id in ("", None):
        pairing_id = None
    else:
        try:
            pairing_id = int(pairing_id)
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "pairing_id must be an integer"}), 400

    def _name(key):
        return str(data.get(key) or "").strip()[:MAX_NAME_LENGTH] or None

    match_type = str(data.get("match_type") or "").strip()[:30] or None

    try:
        report_id = PlayerReportsRepository().save_report(
            reporter_id=reporter_id,
            reporter_name=_name("reporter_name"),
            reported_id=reported_id,
            reported_name=_name("reported_name"),
            pairing_id=pairing_id,
            match_type=match_type,
            reasons=reasons,
            details=details,
            source=REPORT_SOURCE,
        )
    except Exception as e:
        logger.error(f"Error saving partner player report: {e}", exc_info=True)
        return jsonify({"success": False, "error": "Could not save report"}), 500

    logger.info(
        "Partner player report filed: %s reported %s (pairing %s): %s",
        reporter_id, reported_id, pairing_id, reasons,
    )
    return jsonify({"success": True, "report_id": report_id}), 201
