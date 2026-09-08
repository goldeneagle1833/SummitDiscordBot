"""Best-effort Sorcery Online table provisioning for Summit pairings."""

import asyncio
import logging
import os
from pathlib import Path

import aiohttp
from dotenv import dotenv_values


logger = logging.getLogger("discord_bot")
BOT_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
PROVISION_ATTEMPTS = 3
PROVISION_RETRY_DELAYS = (0.25, 0.75)


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
    timeout = aiohttp.ClientTimeout(total=5, connect=2)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for attempt in range(1, PROVISION_ATTEMPTS + 1):
                retryable = False
                try:
                    async with session.post(
                        endpoint,
                        json=payload,
                        headers={"X-API-Key": api_key},
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            links = {
                                int(player["discordUserId"]): player["gameUrl"]
                                for player in data.get("players", [])
                                if player.get("discordUserId") and player.get("gameUrl")
                            }
                            if len(links) != 2:
                                logger.warning(
                                    "Sorcery Online provisioning returned %s usable seat links",
                                    len(links),
                                )
                                return None
                            return links

                        body = await response.text()
                        retryable = response.status in {408, 425, 429} or response.status >= 500
                        logger.warning(
                            "Sorcery Online provisioning attempt %s/%s returned status %s: %s",
                            attempt, PROVISION_ATTEMPTS, response.status, body[:500],
                        )
                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    retryable = True
                    logger.warning(
                        "Sorcery Online provisioning attempt %s/%s failed: %r",
                        attempt, PROVISION_ATTEMPTS, exc,
                    )

                if not retryable or attempt == PROVISION_ATTEMPTS:
                    return None
                await asyncio.sleep(PROVISION_RETRY_DELAYS[attempt - 1])
    except Exception as exc:
        logger.warning("Sorcery Online provisioning failed: %r", exc, exc_info=True)
    return None
