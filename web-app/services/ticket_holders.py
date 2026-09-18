"""Ticket-holder roster, synced from Discord.

The bot's leaderboard message splits players into Ticket Holders and Free Play
by checking Discord roles. The web app has no gateway connection, so it asks
Discord's REST API for the guild's members and caches the result - the bracket
seed pool can then use the same filter.
"""

import logging

import requests

import webapp_config

logger = logging.getLogger(__name__)

DISCORD_API = "https://discord.com/api/v10"
MEMBER_PAGE_SIZE = 1000
REQUEST_TIMEOUT = 20


class TicketHolderError(Exception):
    """Raised when the roster cannot be synced."""


def is_configured() -> bool:
    """Whether we have both a bot token and at least one ticket role."""
    return bool(webapp_config.DISCORD_BOT_TOKEN and webapp_config.TICKET_HOLDER_ROLE_IDS)


def sync_roster(repo) -> dict:
    """Fetch guild members holding a ticket role and cache them.

    Needs the bot's Server Members intent, the same one it already uses to read
    roles for the leaderboard.
    """
    if not webapp_config.DISCORD_BOT_TOKEN:
        raise TicketHolderError("No Discord bot token configured (set TOKEN or DISCORD_BOT_TOKEN)")
    if not webapp_config.TICKET_HOLDER_ROLE_IDS:
        raise TicketHolderError("No TICKET_HOLDER_ROLE_IDS configured")

    headers = {"Authorization": f"Bot {webapp_config.DISCORD_BOT_TOKEN}"}
    url = f"{DISCORD_API}/guilds/{webapp_config.DISCORD_GUILD_ID}/members"

    holders = []
    after = "0"
    while True:
        try:
            resp = requests.get(
                url,
                headers=headers,
                params={"limit": MEMBER_PAGE_SIZE, "after": after},
                timeout=REQUEST_TIMEOUT,
            )
        except Exception as e:
            raise TicketHolderError(f"Could not reach Discord: {e}") from e

        if resp.status_code == 403:
            raise TicketHolderError(
                "Discord refused the member list - the bot needs the Server Members intent"
            )
        if resp.status_code != 200:
            raise TicketHolderError(f"Discord returned {resp.status_code}")

        members = resp.json()
        if not members:
            break

        for member in members:
            user = member.get("user") or {}
            user_id = user.get("id")
            if not user_id:
                continue
            roles = set(member.get("roles") or [])
            if roles & webapp_config.TICKET_HOLDER_ROLE_IDS:
                holders.append(
                    {
                        "user_id": user_id,
                        "display_name": (
                            member.get("nick")
                            or user.get("global_name")
                            or user.get("username")
                        ),
                    }
                )

        if len(members) < MEMBER_PAGE_SIZE:
            break
        after = members[-1]["user"]["id"]

    repo.replace_ticket_holders(holders)
    logger.info("Synced %s ticket holders from Discord", len(holders))
    return {"count": len(holders)}


def ticket_holder_ids(repo) -> set:
    """Cached ticket-holder user ids. Empty when the roster has never synced."""
    return {str(h["user_id"]) for h in repo.get_ticket_holders()}
