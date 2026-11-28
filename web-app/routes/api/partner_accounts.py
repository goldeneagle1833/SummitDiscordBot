"""Partner (Play Sorcery Online) lookup of a player's Summit account.

PSO lets players sign in without Discord. To report their ranked games it
needs the id Summit records them under, so it asks here with the email the
player signed in to PSO with. Summit answers only for an email a Summit
login has verified (Discord or Google sign-in).
"""

import logging

from flask import Blueprint, jsonify, request

from services.summit_player_numbers import lookup_account_by_email
from utils.api_auth import require_integration_api_key

logger = logging.getLogger(__name__)

partner_accounts_bp = Blueprint("partner_accounts", __name__)

MAX_EMAIL_LENGTH = 254
SITE_URL = "https://sorcererssummit.com"


@partner_accounts_bp.route("/partner/summit-account", methods=["POST"])
@require_integration_api_key
def find_summit_account():
    """POST /api/partner/summit-account  {"email": "player@example.com"}

    The email goes in the body, not the URL, so it stays out of access logs.

    200 {"success": true, "found": true, "summit_user_id": "...", "login":
         "discord" | "google", "display_name": "...", "profile_url": "..."}
    200 {"success": true, "found": false}  when no Summit login has that email
    400 when the email is missing or malformed
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "error": "Request body must be JSON"}), 400
    email = str(data.get("email") or "").strip()
    if not email or "@" not in email or len(email) > MAX_EMAIL_LENGTH:
        return jsonify({"success": False, "error": "email must be an email address"}), 400

    account = lookup_account_by_email(email)
    if not account:
        logger.info("Partner account lookup: no Summit login for that email")
        return jsonify({"success": True, "found": False})

    logger.info(
        "Partner account lookup: found %s login %s",
        account["login"], account["summit_user_id"],
    )
    return jsonify({
        "success": True,
        "found": True,
        "summit_user_id": account["summit_user_id"],
        "login": account["login"],
        "display_name": account["display_name"],
        "profile_url": f"{SITE_URL}/player/{account['summit_user_id']}",
    })
