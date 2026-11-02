"""Partner (Play Sorcery Online) endpoints for player blocks and reports.

Players block others from their Summit profile. The block endpoints let a
partner add or remove blocks on a player's behalf; they land in the same
block list, so the Summit bot's matchmaking keeps the pair apart too.

The report endpoint is the partner's version of the bot's Report Player
button: reports land in the same admin list, tagged with their source.
"""

import logging

from flask import Blueprint, jsonify, request

from repositories.blocked_users_repo import BlockedUsersRepository
from repositories.player_reports_repo import REPORT_REASONS, PlayerReportsRepository
from utils.api_auth import require_integration_api_key

logger = logging.getLogger(__name__)

partner_blocks_bp = Blueprint("partner_blocks", __name__)

MAX_ID_LENGTH = 64
MAX_REASON_LENGTH = 200
MAX_DETAILS_LENGTH = 1000
MAX_NAME_LENGTH = 100
REPORT_SOURCE = "sorcery-online"


def _clean_id(value) -> str | None:
    user_id = str(value or "").strip()
    if not user_id or len(user_id) > MAX_ID_LENGTH:
        return None
    return user_id


@partner_blocks_bp.route("/blocks", methods=["POST"])
@require_integration_api_key
def add_block():
    """Add a player to another player's block list.

    Body: user_id (the blocker), blocked_user_id, reason (Discord user IDs).
    Same rules as blocking from the Summit profile: a reason is required and
    a player cannot block themselves.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "error": "Request body must be JSON"}), 400

    user_id = _clean_id(data.get("user_id"))
    blocked_user_id = _clean_id(data.get("blocked_user_id"))
    if not user_id or not blocked_user_id:
        return jsonify({"success": False, "error": "user_id and blocked_user_id are required"}), 400
    if BlockedUsersRepository._stripped(user_id) == BlockedUsersRepository._stripped(blocked_user_id):
        return jsonify({"success": False, "error": "A player cannot block themselves"}), 400

    reason = str(data.get("reason") or "").strip()[:MAX_REASON_LENGTH]
    if not reason:
        return jsonify({"success": False, "error": "A reason is required when blocking a user"}), 400

    try:
        added = BlockedUsersRepository().block_user(user_id, blocked_user_id, reason=reason)
    except Exception as e:
        logger.error(f"Error adding partner block: {e}", exc_info=True)
        return jsonify({"success": False, "error": "Could not save block"}), 500

    logger.info("Partner block: %s blocked %s (added=%s)", user_id, blocked_user_id, added)
    return jsonify({"success": True, "added": added}), 201 if added else 200


@partner_blocks_bp.route("/blocks/<user_id>/<blocked_user_id>", methods=["DELETE"])
@require_integration_api_key
def remove_block(user_id, blocked_user_id):
    """Remove a player from another player's block list."""
    user_id = _clean_id(user_id)
    blocked_user_id = _clean_id(blocked_user_id)
    if not user_id or not blocked_user_id:
        return jsonify({"success": False, "error": "Invalid user id"}), 400

    try:
        removed = BlockedUsersRepository().unblock_user(user_id, blocked_user_id)
    except Exception as e:
        logger.error(f"Error removing partner block: {e}", exc_info=True)
        return jsonify({"success": False, "error": "Could not remove block"}), 500

    logger.info("Partner unblock: %s unblocked %s (removed=%s)", user_id, blocked_user_id, removed)
    return jsonify({"success": True, "removed": removed})


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
