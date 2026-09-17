"""Single-seat Sorcery Online table provisioning for "Try this Deck".

The Discord bot provisions a preloaded table for both players when the LFG
queue makes a pairing (see ``discord-bot/services/sorcery_online_matchmaking.py``).
This module asks Sorcery Online for the same thing with only one seat filled:
the visitor gets a table with the deck already loaded and can invite whoever
they like from there.
"""

import logging
import os
import threading
import time
import uuid

import requests

import webapp_config

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://playsorceryonline.com/api/internal/summit-matchmaking/matches"
# (connect, read) — Sorcery Online imports the deck before answering, so the
# read budget is generous while a dead host still fails fast.
REQUEST_TIMEOUT_S = (3, 15)
QUEUE_TYPE = "testing"

# Per-visitor cooldown. In-process only (each Gunicorn worker keeps its own
# table), which is enough to stop a held-down button from hammering a partner
# API without adding shared state.
COOLDOWN_SECONDS = 10
_MAX_TRACKED_CLIENTS = 5000
_recent_requests: dict[str, float] = {}
_recent_lock = threading.Lock()


class TableUnavailable(Exception):
    """Sorcery Online could not provision a table for this deck."""


def endpoint() -> str:
    return os.getenv("SORCERY_ONLINE_MATCHMAKING_URL", DEFAULT_ENDPOINT).strip()


def is_configured() -> bool:
    """True when the shared Sorcery Online integration key is available."""
    return bool((webapp_config.DRAFT_SORCERY_API_KEY or "").strip() and endpoint())


def claim_slot(client_key: str) -> float:
    """Reserve this client's next request slot.

    Returns the seconds left to wait, or 0 when the request may proceed.
    """
    now = time.monotonic()
    with _recent_lock:
        last = _recent_requests.get(client_key)
        if last is not None and now - last < COOLDOWN_SECONDS:
            return round(COOLDOWN_SECONDS - (now - last), 1)
        if len(_recent_requests) >= _MAX_TRACKED_CLIENTS:
            cutoff = now - COOLDOWN_SECONDS
            for key in [k for k, ts in _recent_requests.items() if ts < cutoff]:
                del _recent_requests[key]
            if len(_recent_requests) >= _MAX_TRACKED_CLIENTS:
                _recent_requests.clear()
        _recent_requests[client_key] = now
    return 0


def release_slot(client_key: str) -> None:
    """Drop a reserved slot so a failed attempt doesn't cost the cooldown."""
    with _recent_lock:
        _recent_requests.pop(client_key, None)


def provision_solo_table(deck_url: str, *, display_name: str, player_id: str | None = None) -> str:
    """Return a Sorcery Online table URL with ``deck_url`` preloaded.

    Raises TableUnavailable when the integration is unconfigured or Sorcery
    Online declines; the response body is logged so failures are diagnosable.
    """
    api_key = (webapp_config.DRAFT_SORCERY_API_KEY or "").strip()
    url = endpoint()
    if not api_key or not url:
        raise TableUnavailable("Sorcery Online provisioning is not configured")

    seat_id = str(player_id) if player_id else f"web-{uuid.uuid4().hex[:16]}"
    payload = {
        "guildId": str(webapp_config.DISCORD_GUILD_ID),
        "pairingId": f"trydeck-{uuid.uuid4().hex[:16]}",
        "queueType": QUEUE_TYPE,
        "players": [
            {
                "discordUserId": seat_id,
                "displayName": display_name[:60] or "Summit Player",
                "deckUrl": deck_url,
            }
        ],
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers={"X-API-Key": api_key},
            timeout=REQUEST_TIMEOUT_S,
        )
    except requests.RequestException as exc:
        logger.warning("Sorcery Online table request failed: %r", exc)
        raise TableUnavailable("Could not reach Sorcery Online. Try again in a moment.")

    if response.status_code != 200:
        logger.warning(
            "Sorcery Online table request returned %s: %s",
            response.status_code, response.text[:500],
        )
        raise TableUnavailable("Sorcery Online could not open a table for this deck.")

    try:
        players = (response.json() or {}).get("players") or []
    except ValueError:
        logger.warning("Sorcery Online table response was not JSON: %s", response.text[:500])
        raise TableUnavailable("Sorcery Online returned an unexpected response.")

    game_url = next(
        (p.get("gameUrl") for p in players if isinstance(p, dict) and p.get("gameUrl")),
        None,
    )
    if not game_url:
        logger.warning(
            "Sorcery Online table response had no seat link: %s", response.text[:500]
        )
        raise TableUnavailable("Sorcery Online did not return a table link.")
    return game_url
