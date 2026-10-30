"""Best-effort Play Sorcery Online table provisioning for Summit pairings."""

import asyncio
import logging
import os
import re
import urllib.parse
from pathlib import Path

import aiohttp
from dotenv import dotenv_values

from cogs.lfg.voice import NO_VOICE, VOICE


logger = logging.getLogger("discord_bot")
BOT_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
PROVISION_ATTEMPTS = 3
PROVISION_RETRY_DELAYS = (0.25, 0.75)
PSO_HOST = "playsorceryonline.com"
# Table names look like "glowing-lantern-citadel"
_TABLE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def table_url_from_response(data) -> str | None:
    """The table's own link (playsorceryonline.com/play?table=<name>), if PSO sent one.

    This is the shared room link, not a player's seat link (``?m=...``), so it
    is safe to show other people. Accepts a full link or just the table name.
    """
    if not isinstance(data, dict):
        return None
    table = data.get("table")
    if isinstance(table, dict):
        candidates = [table.get("url"), table.get("tableUrl"), table.get("name"), table.get("id")]
    else:
        candidates = [table]
    candidates = [
        data.get("tableUrl"), data.get("table_url"), *candidates,
        data.get("tableName"), data.get("tableId"), data.get("table_id"),
    ]
    for value in candidates:
        value = str(value or "").strip()
        if not value:
            continue
        if value.lower().startswith(("http://", "https://")):
            parsed = urllib.parse.urlparse(value)
            host = (parsed.hostname or "").lower().removeprefix("www.")
            name = urllib.parse.parse_qs(parsed.query).get("table", [""])[0]
            if host == PSO_HOST and _TABLE_NAME_RE.match(name):
                return f"https://{PSO_HOST}/play?table={name}"
        elif _TABLE_NAME_RE.match(value):
            return f"https://{PSO_HOST}/play?table={value}"
    return None


def summit_matchmaking_api_key():
    """Read the shared integration key used by both Summit services."""
    file_key = dotenv_values(BOT_ENV_PATH).get("DRAFT_SORCERY_API_KEY")
    return str(file_key or os.getenv("DRAFT_SORCERY_API_KEY", "")).strip()


async def provision_sorcery_online_match(
    guild_id, pairing_id, queue_type, players, voice=False, on_replay_url=None,
    on_table_url=None,
):
    """Open a Play Sorcery Online table and return {discord_user_id: seat_url}.

    Play Sorcery Online also hands back a replay link with the table; it is passed
    to ``on_replay_url`` when given. The link is stable but only plays once
    the game has been saved. The table's shared link, when PSO includes it,
    goes to ``on_table_url``.
    """
    api_key = summit_matchmaking_api_key()
    endpoint = os.getenv(
        "SORCERY_ONLINE_MATCHMAKING_URL",
        "https://playsorceryonline.com/api/internal/summit-matchmaking/matches",
    ).strip()
    if not api_key or not endpoint:
        logger.info("Play Sorcery Online matchmaking provisioning is not configured")
        return None

    payload = {
        "guildId": str(guild_id),
        "pairingId": str(pairing_id),
        "queueType": queue_type,
        "voiceType": VOICE if voice else NO_VOICE,
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
                                    "Play Sorcery Online provisioning returned %s usable seat links",
                                    len(links),
                                )
                                return None
                            table_url = table_url_from_response(data)
                            logger.info(
                                "Play Sorcery Online table for pairing %s: fields %s, table link %s",
                                pairing_id, sorted(data), "found" if table_url else "missing",
                            )
                            if table_url and on_table_url:
                                try:
                                    on_table_url(table_url)
                                except Exception as exc:
                                    logger.warning(
                                        "Could not save Play Sorcery Online table link for pairing %s: %r",
                                        pairing_id, exc,
                                    )
                            replay_url = data.get("replayUrl") or data.get("replay_url")
                            if replay_url and on_replay_url:
                                try:
                                    on_replay_url(replay_url)
                                except Exception as exc:
                                    logger.warning(
                                        "Could not save Play Sorcery Online replay for pairing %s: %r",
                                        pairing_id, exc,
                                    )
                            return links

                        body = await response.text()
                        retryable = response.status in {408, 425, 429} or response.status >= 500
                        logger.warning(
                            "Play Sorcery Online provisioning attempt %s/%s returned status %s: %s",
                            attempt, PROVISION_ATTEMPTS, response.status, body[:500],
                        )
                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    retryable = True
                    logger.warning(
                        "Play Sorcery Online provisioning attempt %s/%s failed: %r",
                        attempt, PROVISION_ATTEMPTS, exc,
                    )

                if not retryable or attempt == PROVISION_ATTEMPTS:
                    return None
                await asyncio.sleep(PROVISION_RETRY_DELAYS[attempt - 1])
    except Exception as exc:
        logger.warning("Play Sorcery Online provisioning failed: %r", exc, exc_info=True)
    return None
