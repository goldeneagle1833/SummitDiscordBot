"""Best-effort Sorcery Online table provisioning for Summit pairings."""

import logging
import os
from pathlib import Path

import aiohttp
from dotenv import dotenv_values


logger = logging.getLogger("discord_bot")
BOT_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def summit_matchmaking_api_key():
    """Read the shared integration key used by both Summit services."""
    file_key = dotenv_values(BOT_ENV_PATH).get("DRAFT_SORCERY_API_KEY")
    return str(file_key or os.getenv("DRAFT_SORCERY_API_KEY", "")).strip()


async def provision_sorcery_online_match(guild_id, pairing_id, queue_type, players):
    api_key = summit_matchmaking_api_key()
    endpoint = os.getenv(
        "SORCERY_ONLINE_MATCHMAKING_URL",
        "https://playsorceryonline.com/api/internal/summit-matchmaking/matches",
    ).strip()
    if not api_key or not endpoint:
        logger.info("Sorcery Online matchmaking provisioning is not configured")
        return None

    payload = {
        "guildId": str(guild_id),
        "pairingId": str(pairing_id),
        "queueType": queue_type,
        "players": [
            {
                "discordUserId": str(player["discord_user_id"]),
                "displayName": player["display_name"],
                "deckUrl": player.get("deck_url") or None,
            }
            for player in players
        ],
    }
    try:
        timeout = aiohttp.ClientTimeout(total=5, connect=2)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(endpoint, json=payload, headers={"X-API-Key": api_key}) as response:
                if response.status != 200:
                    logger.warning("Sorcery Online provisioning returned status %s", response.status)
                    return None
                data = await response.json()
        links = {
            int(player["discordUserId"]): player["gameUrl"]
            for player in data.get("players", [])
            if player.get("discordUserId") and player.get("gameUrl")
        }
        return links if len(links) == 2 else None
    except Exception as exc:
        logger.warning("Sorcery Online provisioning failed: %s", exc)
        return None
