"""Release voice holds: make the no-voice game for a voice-first player after the hold.

A player whose first choice is voice but who is also OK without voice waits
``VOICE_HOLD_SECONDS`` for another voice player. Matching normally happens only
when someone joins, so if a no-voice player is already waiting when the hold
runs out, nobody new joins to pair them. This sweep finds those players, takes
them out of the queue and runs the normal join flow for them again with the hold
over, which pairs them through the usual path (provisioning, DMs, reporting).
"""

import datetime
import logging

import config
from cogs.lfg.state import lfg_queue, lfg_queue_lock, matching_web_users
from cogs.lfg.voice import (
    VOICE,
    entry_voice_flexible,
    holding_for_voice,
    normalize_voice_preference,
    queue_has_voice_choice,
)

logger = logging.getLogger("discord_bot")

# A player re-joined by the sweep keeps at least this many minutes of queue time.
MIN_REJOIN_MINUTES = 5


class _HoldContext:
    def __init__(self, user_id):
        self.author = type("Author", (), {"id": user_id})()


class _DirectMessageFollowup:
    """Join-flow followups for a Discord player go to their DMs."""

    def __init__(self, user):
        self._user = user

    async def send(self, message=None, **kwargs):
        kwargs.pop("ephemeral", None)
        try:
            return await self._user.send(message, **kwargs)
        except Exception as e:
            logger.warning(f"Voice hold: could not DM {getattr(self._user, 'id', '?')}: {e}")
            return None


class _HoldInteraction:
    """Run the queue join flow for a held player as if they had joined again."""

    def __init__(self, bot, member, guild, followup):
        self.user = member
        self.guild = guild
        self.channel = bot.get_channel(getattr(bot.get_cog("LFGCog"), "lfg_channel_id", 0))
        self.followup = followup


def _minutes_left(entry, now):
    return entry["timeframe"] - (now - entry["timestamp"]).total_seconds() / 60


def held_players_ready(lfg_cog, now=None):
    """(user_id, queue_type, entry) for voice holds that are over and have a no-voice partner waiting.

    Takes each such player out of that queue; the caller re-joins them. Call
    with ``lfg_queue_lock`` held.
    """
    now = now or datetime.datetime.now()
    ready = []
    for user_id, user_data in list(lfg_queue.items()):
        if user_id in matching_web_users:
            continue
        for queue_type, entry in list(user_data.get("queues", {}).items()):
            if not queue_has_voice_choice(queue_type) or entry.get("ladder_info"):
                continue
            voice = normalize_voice_preference(entry.get("voice")) or VOICE
            if voice != VOICE or not entry_voice_flexible(entry):
                continue
            if holding_for_voice(voice, True, entry["timestamp"], now) or _minutes_left(entry, now) <= 0:
                continue
            partner = lfg_cog.check_if_someone_is_lfg(
                _HoldContext(user_id), queue_type, voice=VOICE, voice_flexible=True, voice_hold=False
            )
            if partner is None:
                continue
            del user_data["queues"][queue_type]
            if not user_data["queues"]:
                lfg_queue.pop(user_id, None)
            ready.append((user_id, queue_type, dict(entry)))
            break
    return ready


async def release_voice_holds(bot):
    """Pair voice-first, no-voice-OK players whose hold ran out with a waiting no-voice player."""
    lfg_cog = bot.get_cog("LFGCog")
    if not lfg_cog:
        return
    now = datetime.datetime.now()
    async with lfg_queue_lock:
        lfg_cog.clean_expired_lfg()
        ready = held_players_ready(lfg_cog, now)
    if not ready:
        return

    from cogs.lfg.queue import _process_queue_join
    from services.matchmaking_api import WebsiteInteraction

    guild = bot.get_guild(config.GUILD_ID)
    for user_id, queue_type, entry in ready:
        member = guild.get_member(user_id) if guild else None
        if member is None and guild:
            try:
                member = await guild.fetch_member(user_id)
            except Exception as e:
                logger.error(f"Voice hold: could not fetch member {user_id}: {e}")
        if member is None:
            continue
        origin = entry.get("origin", "discord")
        interaction = (
            WebsiteInteraction(bot, member, guild) if origin == "sorcery_online"
            else _HoldInteraction(bot, member, guild, _DirectMessageFollowup(member))
        )
        minutes = max(MIN_REJOIN_MINUTES, round(_minutes_left(entry, now)))
        logger.info(f"Voice hold over for {user_id} in {queue_type}; pairing without voice")
        try:
            await _process_queue_join(
                bot,
                interaction,
                queue_type,
                minutes,
                entry.get("deck_url"),
                run_id=entry.get("run_id"),
                origin=origin,
                voice=VOICE,
                voice_flexible=True,
                voice_hold=False,
                alert_avatar=entry.get("alert_avatar", False),
                deck_avatar=entry.get("deck_avatar"),
            )
        except Exception as e:
            logger.error(f"Voice hold: re-join failed for {user_id} in {queue_type}: {e}", exc_info=True)
