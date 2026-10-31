"""Time out or ban a player in the Summit Discord from the website.

The web app has no gateway connection, so it uses Discord's REST API with the
bot's token, like services/ticket_holders.py. The bot needs the Moderate
Members (timeout) and Ban Members permissions, and its role must sit above
the player's.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests

import webapp_config

logger = logging.getLogger(__name__)

DISCORD_API = "https://discord.com/api/v10"
REQUEST_TIMEOUT = 15

# Same choices as the bot's DM (discord-bot/cogs/moderation_alerts.py).
# Discord caps a timeout at 28 days.
TIMEOUT_MINUTES = (60, 1440, 10080, 40320)

DISCORD_ID = re.compile(r"^\d{15,25}$")


class ModerationError(Exception):
    """The action could not be done; the message is safe to show admins."""


def is_discord_id(value) -> bool:
    return bool(DISCORD_ID.match(str(value or "")))


def _headers(reason: str | None) -> dict:
    if not webapp_config.DISCORD_BOT_TOKEN:
        raise ModerationError("No Discord bot token configured (set TOKEN or DISCORD_BOT_TOKEN)")
    headers = {"Authorization": f"Bot {webapp_config.DISCORD_BOT_TOKEN}"}
    if reason:
        # Shown in the server's audit log; must be URL-encoded, max 512.
        headers["X-Audit-Log-Reason"] = quote(reason[:400], safe="")
    return headers


def _check(resp, action: str):
    if resp.status_code in (200, 201, 204):
        return
    if resp.status_code == 404:
        raise ModerationError("They are not in the Summit Discord any more.")
    if resp.status_code == 403:
        raise ModerationError(
            "Discord refused. The bot needs Moderate Members (timeout) or Ban Members, "
            "and its role must be above theirs. Server admins can't be timed out."
        )
    raise ModerationError(f"Discord returned {resp.status_code} for the {action}.")


def timeout_member(user_id: str, minutes: int, reason: str | None = None) -> datetime:
    """Time out a member. Returns when it ends (UTC)."""
    if not is_discord_id(user_id):
        raise ModerationError("Not a Discord account.")
    if int(minutes) not in TIMEOUT_MINUTES:
        raise ModerationError("Pick 1 hour, 1 day, 1 week or 28 days.")
    until = datetime.now(timezone.utc) + timedelta(minutes=int(minutes))
    url = f"{DISCORD_API}/guilds/{webapp_config.DISCORD_GUILD_ID}/members/{user_id}"
    try:
        resp = requests.patch(
            url,
            headers=_headers(reason),
            json={"communication_disabled_until": until.isoformat()},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        raise ModerationError(f"Could not reach Discord: {e}") from e
    _check(resp, "timeout")
    return until


def ban_user(user_id: str, reason: str | None = None):
    """Ban a user from the server (works even if they already left)."""
    if not is_discord_id(user_id):
        raise ModerationError("Not a Discord account.")
    url = f"{DISCORD_API}/guilds/{webapp_config.DISCORD_GUILD_ID}/bans/{user_id}"
    try:
        resp = requests.put(
            url,
            headers=_headers(reason),
            json={"delete_message_seconds": 0},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        raise ModerationError(f"Could not reach Discord: {e}") from e
    _check(resp, "ban")
