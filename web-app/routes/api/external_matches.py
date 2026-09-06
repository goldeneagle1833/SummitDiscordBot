"""External match reporting API routes."""

import logging

from flask import Blueprint, jsonify, request

from repositories.pairings import PairingRepository
from routes.api.matchmaking import relay_to_bot
from services.external_match import ExternalMatchService
from utils.auth import require_api_key

logger = logging.getLogger(__name__)

external_matches_bp = Blueprint("external_matches", __name__)


@external_matches_bp.route("/report-external-match", methods=["POST"])
@require_api_key
def report_external_match():
    """
    API endpoint for external applications to report match results.
    Requires API key authentication.

    If the two players have a Summit queue pairing (or the payload names one
    via ``pairing_id``), the result is forwarded to the Discord bot and
    recorded exactly like a bot-reported match: it lands in match_records,
    ELO is applied, the pairing is closed, and the match card is retired.
    The response then includes ``pipeline: "bot"`` and the bot's ``match_id``.

    Results that don't belong to a Summit pairing are stored in the
    external_matches table (no ELO) with ``pipeline: "external"``.
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Request body must be JSON", "success": False}), 400

        # Validate required fields
        required = ["winner_id", "loser_id", "winner_deck_url", "loser_deck_url", "source"]
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({
                "error": f"Missing required fields: {', '.join(missing)}",
                "success": False,
            }), 400

        winner_id = str(data["winner_id"]).strip()
        loser_id = str(data["loser_id"]).strip()

        if winner_id == loser_id:
            return jsonify({
                "error": "winner_id and loser_id must be different",
                "success": False,
            }), 400

        winner_deck_url = str(data["winner_deck_url"]).strip()
        loser_deck_url = str(data["loser_deck_url"]).strip()
        source = str(data["source"]).strip()

        if not source:
            return jsonify({"error": "source cannot be empty", "success": False}), 400

        # Optional fields
        winner_name = str(data["winner_name"]).strip() if data.get("winner_name") else None
        loser_name = str(data["loser_name"]).strip() if data.get("loser_name") else None
        match_comment = str(data["match_comment"]).strip() if data.get("match_comment") else None

        winner_went_first = None
        if data.get("winner_went_first") is not None:
            winner_went_first = "y" if data["winner_went_first"] else "n"

        match_time = None
        if data.get("match_time") is not None:
            match_time = int(data["match_time"])

        # PSO Ranked games always go through the ranked pipeline as
        # pending confirmations (24h auto-confirm with ELO).
        if source == "PSO Ranked":
            return _record_pso_ranked(
                data, winner_id, loser_id,
                winner_name, loser_name,
                winner_deck_url, loser_deck_url,
                winner_went_first, match_time, match_comment,
            )

        # Summit-queued games go through the bot pipeline, same as a
        # Discord Report-button match.
        pairing = _resolve_summit_pairing(data, winner_id, loser_id)
        if pairing is not None:
            return _record_via_bot(pairing, data, winner_id, loser_id, source)

        # No Summit pairing: keep it as a stats-only external match.
        service = ExternalMatchService()
        result = service.report_match(
            winner_id=winner_id,
            loser_id=loser_id,
            winner_deck_url=winner_deck_url,
            loser_deck_url=loser_deck_url,
            source=source,
            winner_name=winner_name,
            loser_name=loser_name,
            winner_went_first=winner_went_first,
            match_time=match_time,
            match_comment=match_comment,
        )

        return jsonify({
            "success": True,
            "message": "External match recorded successfully",
            "pipeline": "external",
            **result,
        })

    except ValueError as e:
        return jsonify({"error": f"Invalid data: {str(e)}", "success": False}), 400
    except Exception as e:
        logger.error(f"Error recording external match: {e}", exc_info=True)
        return jsonify({"error": "Internal server error", "success": False}), 500


def _record_pso_ranked(
    data: dict,
    winner_id: str,
    loser_id: str,
    winner_name: str | None,
    loser_name: str | None,
    winner_deck_url: str,
    loser_deck_url: str,
    winner_went_first: str | None,
    match_time: int | None,
    match_comment: str | None,
):
    """Create a pending ranked confirmation for a PSO-reported match."""
    from services.match_confirmation import MatchConfirmationService

    try:
        service = MatchConfirmationService()
        result = service.create_pso_match_report(
            winner_id=winner_id,
            loser_id=loser_id,
            winner_deck_url=winner_deck_url,
            loser_deck_url=loser_deck_url,
            winner_name=winner_name,
            loser_name=loser_name,
            winner_went_first=winner_went_first,
            match_time=match_time,
            match_comment=match_comment or "",
        )

        # Send web notifications to both players
        _notify_pso_match_players(winner_id, loser_id, result)

        # Send Discord DM to the loser with confirm/dispute buttons
        _notify_pso_loser_discord(
            loser_id, result,
            winner_deck_url=winner_deck_url,
            loser_deck_url=loser_deck_url,
        )

        return jsonify(result)

    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e), "pipeline": "pso_ranked"}), 409
    except ValueError as e:
        return jsonify({"success": False, "error": str(e), "pipeline": "pso_ranked"}), 400


def _notify_pso_match_players(winner_id: str, loser_id: str, result: dict):
    """Send web notifications to both players about the PSO match report."""
    try:
        from repositories.store import StoreRepository
        store_repo = StoreRepository()

        winner_name = result["winner"]["display_name"]
        loser_name = result["loser"]["display_name"]
        confirmation_id = result["confirmation_id"]

        store_repo.create_web_notification(
            user_id=winner_id,
            ntype="pso_match_pending",
            title="PSO Ranked Match Reported",
            body=(
                f"A ranked win against {loser_name} was reported by Play Sorcery Online. "
                f"It will auto-confirm in 24h. Dispute on your profile if incorrect."
            ),
        )

        store_repo.create_web_notification(
            user_id=loser_id,
            ntype="pso_match_pending",
            title="PSO Ranked Match Reported",
            body=(
                f"A ranked loss against {winner_name} was reported by Play Sorcery Online. "
                f"It will auto-confirm in 24h. Dispute on your profile if incorrect."
            ),
        )

        logger.info(
            f"Sent PSO match notifications: confirmation={confirmation_id}, "
            f"winner={winner_id}, loser={loser_id}"
        )
    except Exception as e:
        logger.error(f"Failed to send PSO match notifications: {e}", exc_info=True)


def _notify_pso_loser_discord(loser_id: str, result: dict, *, winner_deck_url: str, loser_deck_url: str):
    """Call the bot's loopback API to send a Discord DM to the loser with confirm/dispute buttons."""
    try:
        body, status = relay_to_bot(
            "POST",
            "/pso-match-notify",
            {
                "loser_discord_id": loser_id,
                "winner_name": result["winner"]["display_name"],
                "loser_name": result["loser"]["display_name"],
                "confirmation_id": result["confirmation_id"],
                "winner_deck_url": winner_deck_url,
                "loser_deck_url": loser_deck_url,
                "expires_at": result.get("expires_at"),
            },
            unavailable_body={"sent": False, "reason": "bot_unavailable"},
        )
        if body.get("sent"):
            logger.info(f"Discord DM sent to loser {loser_id} for confirmation {result['confirmation_id']}")
        else:
            logger.warning(f"Discord DM not sent to loser {loser_id}: {body.get('reason', 'unknown')}")
    except Exception as e:
        logger.error(f"Failed to send Discord DM to loser {loser_id}: {e}", exc_info=True)


def _resolve_summit_pairing(data: dict, winner_id: str, loser_id: str) -> dict | None:
    """Find the Summit pairing this result belongs to, if any.

    An explicit ``pairing_id`` in the payload wins; otherwise the most recent
    active pairing between the two players is used. Returns None when the
    game wasn't queued through Summit.
    """
    repo = PairingRepository()
    pairing_id = data.get("pairing_id") or data.get("pairingId")
    queue_type = data.get("queue_type") or data.get("queueType")
    if pairing_id:
        pairing = repo.get_pairing_by_id(pairing_id, queue_type)
        if pairing is None:
            return None
        participants = {str(pairing["player1_id"]), str(pairing["player2_id"])}
        if participants != {winner_id, loser_id}:
            logger.warning(
                "External report for pairing %s names players %s/%s who are not in it",
                pairing_id, winner_id, loser_id,
            )
            return None
        return pairing
    return repo.find_active_pairing(winner_id, loser_id)


def _record_via_bot(pairing: dict, data: dict, winner_id: str, loser_id: str, source: str):
    """Forward a Summit-paired result to the bot's results endpoint."""
    reporter_id = str(data.get("reporter_id") or data.get("reporterId") or winner_id).strip()
    payload = {
        "queue_type": pairing["match_type"],
        "outcome": "decided",
        "reporter_id": reporter_id,
        "winner_id": winner_id,
        "loser_id": loser_id,
        "source": source,
    }
    players = data.get("players") or data.get("played_cards") or data.get("playedCards")
    if players:
        payload["players"] = players

    body, status = relay_to_bot(
        "POST",
        f"/matches/{pairing['guild_id']}/{pairing['pairing_id']}/results",
        payload,
        unavailable_body={
            "success": False,
            "error": "Summit bot is unavailable; retry later",
            "pipeline": "bot",
        },
    )
    if status >= 400:
        logger.warning(
            "Bot rejected external result for pairing %s (status %s): %s",
            pairing["pairing_id"], status, body,
        )
        if "error" not in body:
            body = {"error": "Summit bot rejected the result", **body}
        return jsonify({"success": False, "pipeline": "bot", **body}), status

    recorded = bool(body.get("recorded"))
    duplicate = bool(body.get("duplicate"))
    logger.info(
        "External result for pairing %s routed through bot: recorded=%s duplicate=%s match_id=%s",
        pairing["pairing_id"], recorded, duplicate, body.get("match_id"),
    )
    return jsonify({
        "success": True,
        "message": (
            "Match already recorded for this pairing"
            if duplicate else "Match recorded through Summit bot"
        ),
        "pipeline": "bot",
        "pairing_id": pairing["pairing_id"],
        "queue_type": pairing["match_type"],
        "winner_id": winner_id,
        "loser_id": loser_id,
        "source": source,
        **body,
    })
