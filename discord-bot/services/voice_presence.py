"""Find the Summit voice channel a set of players is talking in.

Sorcery Online polls this (through the web app relay) so a live game can
show how many people are listening in and offer a one-click join link.
Everything is read from the bot's guild cache, so a lookup costs no
Discord API calls; only the invite link is fetched, and it is cached.
"""

import logging
import os
import time

import discord

import config
from cogs.lfg.pairing_messages import SUMMIT_VOICE_URL

logger = logging.getLogger("discord_bot")

MAX_USER_IDS = 10
MAX_SPECTATORS = 25
INVITE_MAX_AGE = 3600
_INVITE_CACHE_TTL = 1800
# channel_id -> (invite_url, expiry_time)
_invite_cache: dict[int, tuple[str, float]] = {}


def parse_user_ids(raw):
    """Turn a comma-separated ``user_ids`` value into a deduped list of ints."""
    user_ids = []
    for chunk in str(raw or "").replace(" ", "").split(","):
        if not chunk:
            continue
        if not chunk.isdigit():
            raise ValueError(f"'{chunk}' is not a Discord user id")
        user_id = int(chunk)
        if user_id not in user_ids:
            user_ids.append(user_id)
    if not user_ids:
        raise ValueError("user_ids is required")
    if len(user_ids) > MAX_USER_IDS:
        raise ValueError(f"At most {MAX_USER_IDS} user ids per lookup")
    return user_ids


async def _invite_url(channel):
    """A join link for the voice channel itself, cached well inside its lifetime."""
    now = time.time()
    cached = _invite_cache.get(channel.id)
    if cached and cached[1] > now:
        return cached[0]
    for channel_id, (_url, expiry) in list(_invite_cache.items()):
        if expiry <= now:
            _invite_cache.pop(channel_id, None)
    try:
        invite = await channel.create_invite(
            max_age=INVITE_MAX_AGE,
            reason="Sorcery Online listen-in link",
        )
    except discord.HTTPException as exc:
        logger.warning("Could not create a listen-in invite for %s: %s", channel, exc)
        return None
    _invite_cache[channel.id] = (invite.url, now + _INVITE_CACHE_TTL)
    return invite.url


def _occupant(member, is_player):
    voice = member.voice
    return {
        "user_id": str(member.id),
        "display_name": member.display_name,
        "avatar_url": str(member.display_avatar.url) if member.display_avatar else None,
        "is_player": is_player,
        "streaming": bool(voice and voice.self_stream),
    }


def _summit_invite_url():
    return os.getenv("SUMMIT_DISCORD_INVITE", "https://discord.gg/sorcererssummit")


async def voice_session(bot, user_ids):
    """Describe the voice channel the given players are in.

    Returns ``None`` when the guild is not cached yet so the caller can
    answer 503. ``status`` is one of:

    - ``together``    — every requested player is in the same channel
    - ``split``       — someone is in voice, but not all of them together
    - ``not_in_voice`` — nobody is in a Summit voice channel
    """
    guild = bot.get_guild(config.GUILD_ID) if bot.is_ready() else None
    if guild is None:
        return None

    players = []
    channels = {}
    channel_player_counts = {}
    for user_id in user_ids:
        member = guild.get_member(user_id)
        voice = member.voice if member else None
        channel = voice.channel if voice else None
        players.append({
            "user_id": str(user_id),
            "display_name": member.display_name if member else None,
            "in_voice": channel is not None,
            "channel_id": str(channel.id) if channel else None,
            "streaming": bool(voice and voice.self_stream),
        })
        if channel is not None:
            channels[channel.id] = channel
            channel_player_counts[channel.id] = channel_player_counts.get(channel.id, 0) + 1

    payload = {
        "status": "not_in_voice",
        "channel": None,
        "players": players,
        "summit_invite_url": _summit_invite_url(),
        "voice_hub_url": SUMMIT_VOICE_URL,
    }
    if not channels:
        return payload

    # The channel holding the most of the requested players wins; ties go to
    # whichever player was asked about first.
    channel_id = max(channel_player_counts.items(), key=lambda item: item[1])[0]
    channel = channels[channel_id]
    payload["status"] = (
        "together" if channel_player_counts[channel_id] == len(user_ids) else "split"
    )

    player_ids = set(user_ids)
    occupants = [member for member in channel.members if not member.bot]
    spectators = [member for member in occupants if member.id not in player_ids]
    channel_url = f"https://discord.com/channels/{guild.id}/{channel.id}"
    invite_url = await _invite_url(channel)
    payload["channel"] = {
        "id": str(channel.id),
        "name": channel.name,
        "channel_url": channel_url,
        "invite_url": invite_url,
        "listen_url": invite_url or channel_url,
        "member_count": len(occupants),
        "player_count": len(occupants) - len(spectators),
        "spectator_count": len(spectators),
        "spectators": [_occupant(member, False) for member in spectators[:MAX_SPECTATORS]],
        "players_in_channel": [
            _occupant(member, True)
            for member in occupants if member.id in player_ids
        ],
    }
    return payload
