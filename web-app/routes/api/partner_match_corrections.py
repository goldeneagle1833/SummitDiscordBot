"""Partner (Play Sorcery Online) endpoint for correcting a match result.

PSO's version of the bot's ``!correct_match`` and the Mod Tools "Flip
results" button. PSO says which match and who really won; if the recorded
winner is wrong, the flip is queued for the Discord bot, which does it the
same safe way as those two (``correct_match_record``: winner and loser swap,
decks and avatars swap with them, and every later rated game of both players
is recalculated). The bot works the queue every 30 seconds, posts the change
in the mod channel and writes the audit log entry. This endpoint writes its
own audit entry too, naming Play Sorcery Online and the reason it gave.

Same API key as /api/report-external-match.
"""

import logging

from flask import Blueprint, jsonify, request

from utils.api_auth import require_integration_api_key

logger = logging.getLogger(__name__)

partner_match_corrections_bp = Blueprint("partner_match_corrections", __name__)

PARTNER_ID = "sorcery-online"
PARTNER_NAME = "Play Sorcery Online"
MAX_ID_LENGTH = 64
MAX_REASON_LENGTH = 500


def _clean_id(value) -> str | None:
    user_id = str(value if value is not None else "").strip()
    if not user_id or len(user_id) > MAX_ID_LENGTH:
        return None
    return user_id


def _int_or_none(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError
    return int(value)


def _status_body(flip: dict) -> dict:
    status = {"pending": "queued", "done": "corrected", "error": "failed"}.get(flip["status"], flip["status"])
    return {
        "success": True,
        "request_id": flip["id"],
        "match_id": flip["match_id"],
        "status": status,
        "result": flip.get("result"),
        "requested_at": flip.get("created_at"),
        "done_at": flip.get("done_at"),
    }


CORRECTION_FLAGS = ("correction", "is_correction", "isCorrection", "corrected", "correct_match", "correctMatch")
CORRECTION_ACTIONS = {"correction", "correct", "correct_match", "correct-match", "flip", "fix"}
# Without an ID, a correction sent to the report link means the two players'
# most recent recorded match in this window.
RECENT_MATCH_DAYS = 2


def is_correction_request(data: dict) -> bool:
    """True when a payload sent to /api/report-external-match is really a
    correction of an already-recorded result (a flag or an action name)."""
    if any(data.get(k) is True or str(data.get(k)).lower() == "true" for k in CORRECTION_FLAGS):
        return True
    for key in ("action", "type", "kind", "reportType", "report_type"):
        if str(data.get(key) or "").strip().lower() in CORRECTION_ACTIONS:
            return True
    return False


def queue_partner_correction(data: dict, *, allow_recent_fallback: bool = False):
    """Queue PSO's correction of one recorded match. Returns (body, status).

    ``winner_id`` is who really won. The match is found by ``match_id``
    (Summit's), ``pairing_id``, ``replay_url``, or - only when
    ``allow_recent_fallback`` (the report link's corrections) - the two
    players' most recent match in the last RECENT_MATCH_DAYS days, the two
    being ``winner_id`` and ``loser_id``.
    """
    from datetime import datetime, timedelta

    from repositories.mod_record_repo import ModRequestsRepository
    from utils.match_tables import live_matches

    winner_id = _clean_id(data.get("winner_id") or data.get("winnerId"))
    if not winner_id:
        return {"success": False, "error": "winner_id is required"}, 400
    try:
        match_id = _int_or_none(data.get("match_id", data.get("matchId")))
        pairing_id = _int_or_none(data.get("pairing_id", data.get("pairingId")))
    except (TypeError, ValueError):
        return {"success": False, "error": "match_id and pairing_id must be whole numbers"}, 400
    replay_url = str(data.get("replay_url") or data.get("replayUrl") or "").strip() or None
    loser_id = _clean_id(data.get("loser_id") or data.get("loserId"))
    reason = str(data.get("reason") or data.get("match_comment") or "").strip()[:MAX_REASON_LENGTH]

    repo = ModRequestsRepository()
    table = live_matches()
    if match_id is not None or pairing_id is not None:
        found = repo.find_match(table, match_id=match_id, pairing_id=pairing_id)
        if pairing_id is not None and match_id is not None:
            found = [m for m in found if m.get("pairing_id") is not None and int(m["pairing_id"]) == pairing_id]
    elif replay_url:
        found = repo.find_match(table, replay_url=replay_url)
    elif allow_recent_fallback and loser_id and loser_id != winner_id:
        since = (datetime.now() - timedelta(days=RECENT_MATCH_DAYS)).strftime("%Y-%m-%d")
        found = repo.find_match(table, players=(winner_id, loser_id), since=since)[:1]
    else:
        return {"success": False, "error": "Send match_id or pairing_id"}, 400
    # Only matches this player actually played in
    found = [m for m in found if winner_id in (m["winner_id"], m["loser_id"])]
    if not found:
        return {"success": False, "error": "No recorded match this season with that ID for that player"}, 404
    if len(found) > 1:
        return {
            "success": False,
            "error": "That pairing has more than one recorded match; send match_id instead",
            "match_ids": [m["id"] for m in found],
        }, 409
    match = found[0]

    base = {
        "success": True,
        "pipeline": "correction",
        "match_id": match["id"],
        "pairing_id": match.get("pairing_id"),
        "winner_id": winner_id,
    }

    pending = repo.pending_flip_for_match(match["id"])
    if pending:
        # A flip is already waiting; once it runs the winners swap, so it only
        # helps if this player is the current loser.
        if match["winner_id"] == winner_id:
            return {
                "success": False,
                "error": "A correction for this match is already queued and would make the other player the winner",
                "request_id": pending["id"],
            }, 409
        return {**base, "status": "queued", "request_id": pending["id"],
                "message": "This correction is already queued"}, 202

    if match["winner_id"] == winner_id:
        return {**base, "status": "already_correct",
                "message": "That player is already recorded as the winner; nothing changed"}, 200

    request_id, _ = repo.queue_flip(match["id"], winner_id, PARTNER_ID, PARTNER_NAME)
    try:
        from repositories.audit import AuditRepository
        AuditRepository().log_action(
            PARTNER_ID, PARTNER_NAME, "partner_correct_match", target_id=str(match["id"]),
            previous_state={"winner_id": match["winner_id"], "winner_name": match["winner_display_name"],
                            "loser_id": match["loser_id"], "loser_name": match["loser_display_name"]},
            new_state={"winner_id": match["loser_id"], "winner_name": match["loser_display_name"],
                       "request_id": request_id},
            details=(f"Play Sorcery Online asked to flip match #{match['id']}"
                     + (f": {reason}" if reason else "")),
        )
    except Exception as e:
        logger.warning(f"Partner match correction not audit-logged: {e}")
    logger.info("PSO queued a correction of match #%s (request %s)", match["id"], request_id)
    return {**base, "status": "queued", "request_id": request_id,
            "message": "Correction queued; Summit applies it within about a minute"}, 202


@partner_match_corrections_bp.route("/partner/correct-match", methods=["POST"])
@require_integration_api_key
def partner_correct_match():
    """Correct who won a recorded match.

    Body: ``winner_id`` (Discord user ID of the player who really won) and
    either ``match_id`` (Summit's match ID, returned when the result was
    reported) or ``pairing_id`` (the Summit pairing the table was opened
    for), or ``replay_url``. Optional ``reason`` (shown in the audit log).
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "error": "Request body must be JSON"}), 400
    body, status = queue_partner_correction(data)
    return jsonify(body), status


@partner_match_corrections_bp.route("/partner/correct-match/<int:request_id>", methods=["GET"])
@require_integration_api_key
def partner_correct_match_status(request_id):
    """Check a correction this endpoint queued: queued, corrected or failed."""
    from repositories.mod_record_repo import ModRequestsRepository

    flip = ModRequestsRepository().get_flip(request_id)
    if not flip or flip.get("requested_by_id") != PARTNER_ID:
        return jsonify({"success": False, "error": "Unknown request"}), 404
    return jsonify(_status_body(flip)), 200
