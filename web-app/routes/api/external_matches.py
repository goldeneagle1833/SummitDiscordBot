"""External match reporting API routes."""

import logging
import re
import os
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from repositories.pairings import PairingRepository
from routes.api.matchmaking import relay_to_bot
from services.external_match import ExternalMatchService
from utils.api_auth import require_integration_api_key

logger = logging.getLogger(__name__)

external_matches_bp = Blueprint("external_matches", __name__)


@external_matches_bp.route("/report-external-match", methods=["POST"])
@require_integration_api_key
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
            if not isinstance(data["winner_went_first"], bool):
                return jsonify({
                    "error": "winner_went_first must be a boolean",
                    "success": False,
                }), 400
            winner_went_first = "y" if data["winner_went_first"] else "n"

        match_time = None
        if data.get("match_time") is not None:
            match_time = int(data["match_time"])

        # Bracket (top cut) games never move ELO and must never reach a
        # ranked pipeline. They are recognised by the pairing id we gave the
        # table, or - when the report carries no pairing id - by the two
        # players having an open bracket table. The players settle the game
        # on the bracket page, which logs it to their history as top cut.
        bracket_ack = _acknowledge_bracket_pairing(data, winner_id, loser_id)
        if bracket_ack is not None:
            return bracket_ack

        # Summit-queued games go through the bot pipeline, same as a
        # Discord Report-button match. Resolve this before the standalone
        # PSO Ranked pipeline so an explicitly identified Summit pairing is
        # completed instead of leaving its pairing active.
        pairing = _resolve_summit_pairing(data, winner_id, loser_id)
        if pairing is not None:
            return _record_via_bot(pairing, data, winner_id, loser_id, source)

        # An explicit pairing is authoritative. Never silently turn a stale,
        # mistyped, or player-mismatched pairing callback into an unrelated
        # external match, since PSO would consider that a successful report.
        if data.get("pairing_id") is not None or data.get("pairingId") is not None:
            return jsonify({
                "error": "Summit pairing was not found or does not match these players",
                "success": False,
            }), 400

        # Standalone PSO Ranked games always go through the ranked pipeline as
        # pending confirmations (24h auto-confirm with ELO).
        if source == "PSO Ranked":
            players = data.get("players") or data.get("played_cards") or data.get("playedCards")
            return _record_pso_ranked(
                data, winner_id, loser_id,
                winner_name, loser_name,
                winner_deck_url, loser_deck_url,
                winner_went_first, match_time, match_comment,
                players=players,
            )

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
    players: list | None = None,
):
    """Create a pending ranked confirmation for a PSO-reported match."""
    from services.match_confirmation import MatchConfirmationService

    # Extract per-player deck URLs from the players array (mirrors bot logic
    # in summit_result_reporting.py lines 366-377).
    if players:
        for p in players:
            pid = str(
                p.get("player_id") or p.get("discord_id")
                or p.get("playerId") or p.get("discordId") or ""
            )
            url = p.get("deck_url") or p.get("deckUrl") or ""
            if pid and url:
                if pid == winner_id:
                    winner_deck_url = winner_deck_url or url
                elif pid == loser_id:
                    loser_deck_url = loser_deck_url or url

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
            players=players,
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


BRACKET_PAIRING = re.compile(r"bracket-(\d+)-m(\d+)")
_PAIRING_KEYS = ("pairing_id", "pairingId", "match_id", "matchId", "table_id", "tableId")
# How long after a bracket game is settled a late table report still belongs to it.
BRACKET_REPORT_WINDOW = timedelta(hours=48)


def _acknowledge_bracket_pairing(data: dict, winner_id: str, loser_id: str):
    """Answer a report for a bracket table, or None when it is not one.

    The winner is filed on the bracket as a report the players confirm,
    and nothing is rated. Returning 200 keeps the integration healthy
    instead of leaving PSO retrying.
    """
    from repositories.brackets import BracketRepository

    pairing_id = ""
    found = None
    for key in _PAIRING_KEYS:
        value = str(data.get(key) or "")
        found = BRACKET_PAIRING.search(value)
        if found:
            pairing_id = value
            break
    explicit_pairing = any(data.get(k) is not None for k in ("pairing_id", "pairingId"))

    try:
        repo = BracketRepository()
        if found:
            bracket_id, match_no = int(found.group(1)), int(found.group(2))
            bracket = repo.get_bracket(bracket_id=bracket_id)
            bracket_match = repo.get_match(bracket_id, match_no) if bracket else None
            if not bracket_match:
                return None
        elif explicit_pairing:
            # A Summit queue pairing; that pipeline decides.
            return None
        else:
            since = (datetime.now() - BRACKET_REPORT_WINDOW).isoformat()
            bracket_match = repo.find_table_match(winner_id, loser_id, since)
            if not bracket_match:
                return None
            bracket = repo.get_bracket(bracket_id=bracket_match["bracket_id"])
            match_no = bracket_match["match_no"]
            pairing_id = f"bracket-{bracket_match['bracket_id']}-m{match_no}"
    except Exception as e:
        logger.error("Could not look up bracket pairing %s: %s", pairing_id or "(by players)", e)
        return None

    players = {
        str(bracket_match["p1_user_id"] or ""),
        str(bracket_match["p2_user_id"] or ""),
    }
    if players != {winner_id, loser_id}:
        logger.warning(
            "Bracket report for %s names players %s/%s who are not in that match",
            pairing_id, winner_id, loser_id,
        )
        return jsonify({
            "error": "Bracket match was not found or does not match these players",
            "success": False,
        }), 400

    # The table's result goes on the bracket as a report the players confirm
    # or dispute there. It never touches ELO.
    from services.brackets import BracketService

    try:
        state = BracketService(repo=repo).record_table_result(
            bracket["bracket_id"], match_no, winner_id
        )
    except Exception as e:
        logger.error("Could not file bracket table result for %s: %s", pairing_id, e)
        state = bracket_match["state"]

    logger.info("Bracket table report for %s: match is %s", pairing_id, state)
    return jsonify({
        "success": True,
        "pipeline": "bracket",
        "bracket_slug": bracket["slug"],
        "match_no": match_no,
        "state": state,
        "message": "Recorded on the bracket; players confirm the result there.",
    })


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
    if data.get("winner_went_first") is not None:
        payload["winner_went_first"] = bool(data["winner_went_first"])
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
        # Match recording includes ELO and other durable bot-side work. Keep
        # this below Sorcery Online's 35s timeout so its retry worker receives
        # a definite match-history receipt or error.
        timeout=float(os.getenv("MATCH_REPORT_BOT_API_TIMEOUT", "30")),
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
