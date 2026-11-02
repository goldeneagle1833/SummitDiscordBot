"""Partner (Play Sorcery Online) endpoint for kudos (positive player reports).

The partner's version of the Discord bot's Give Kudos button: a player thanks
an opponent they played and says why. Kudos land in the same table as the
bot's, and players who receive them can be picked as the homepage Player of
the Day. Same auth and conventions as partner_blocks.py.
"""

import logging

from flask import Blueprint, jsonify, request

from repositories.player_kudos_repo import (
    KUDOS_REASON_VALUES,
    KudosError,
    PlayerKudosRepository,
)
from utils.api_auth import require_integration_api_key

logger = logging.getLogger(__name__)

partner_kudos_bp = Blueprint("partner_kudos", __name__)

MAX_ID_LENGTH = 64
MAX_MESSAGE_LENGTH = 200
MAX_NAME_LENGTH = 100
KUDOS_SOURCE = "sorcery-online"


def _clean_id(value) -> str | None:
    user_id = str(value or "").strip()
    if not user_id or len(user_id) > MAX_ID_LENGTH:
        return None
    return user_id


@partner_kudos_bp.route("/player-kudos", methods=["POST"])
@require_integration_api_key
def give_player_kudos():
    """Give kudos to an opponent.

    Body: giver_id, receiver_id (Discord user IDs), reasons (list of
    KUDOS_REASON_VALUES) and/or message; optional anonymous, giver_name,
    receiver_name, pairing_id. The two must have a Summit-recorded match in
    the last 14 days, and each match can get one kudos from each player.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "error": "Request body must be JSON"}), 400

    giver_id = _clean_id(data.get("giver_id"))
    receiver_id = _clean_id(data.get("receiver_id"))
    if not giver_id or not receiver_id:
        return jsonify({"success": False, "error": "giver_id and receiver_id are required"}), 400
    if giver_id == receiver_id:
        return jsonify({"success": False, "error": "A player cannot applaud themselves"}), 400

    reasons = data.get("reasons") or []
    if not isinstance(reasons, list):
        return jsonify({"success": False, "error": "reasons must be a list"}), 400
    reasons = list(dict.fromkeys(str(r).strip() for r in reasons))
    unknown = [r for r in reasons if r not in KUDOS_REASON_VALUES]
    if unknown:
        return jsonify({
            "success": False,
            "error": f"Unknown reasons: {', '.join(unknown)}",
            "allowed_reasons": KUDOS_REASON_VALUES,
        }), 400

    message = str(data.get("message") or "").strip()
    if len(message) > MAX_MESSAGE_LENGTH:
        return jsonify({
            "success": False,
            "error": f"message must be {MAX_MESSAGE_LENGTH} characters or fewer",
        }), 400
    if not reasons and not message:
        return jsonify({"success": False, "error": "Give at least one reason or a message"}), 400

    anonymous = data.get("anonymous", False)
    if not isinstance(anonymous, bool):
        return jsonify({"success": False, "error": "anonymous must be true or false"}), 400

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

    try:
        saved = PlayerKudosRepository().give_kudos(
            giver_id=giver_id,
            giver_name=_name("giver_name"),
            receiver_id=receiver_id,
            receiver_name=_name("receiver_name"),
            pairing_id=pairing_id,
            reasons=reasons,
            message=message,
            anonymous=anonymous,
            source=KUDOS_SOURCE,
        )
    except KudosError as e:
        status = 409 if e.code == "already_given" else 422
        return jsonify({"success": False, "error": e.message, "code": e.code}), status
    except Exception as e:
        logger.error(f"Error saving partner kudos: {e}", exc_info=True)
        return jsonify({"success": False, "error": "Could not save kudos"}), 500

    logger.info("Partner kudos: %s -> %s (match %s): %s", giver_id, receiver_id, saved["match_id"], reasons)
    return jsonify({"success": True, **saved}), 201
