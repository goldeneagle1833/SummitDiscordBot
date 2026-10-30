"""Opt-in "Alert my avatar's channel" for LFG joins.

A player can tick a box in the join modal; when their match is made the bot
posts in the private channel for the avatar they are playing (the same
config.AVATAR_CHANNEL_MAP the stream alerts use). The post never carries a
deck link or list. It links the game's Play Sorcery Online replay only when
both players turned on "Game Replays" on their Summit profile, the same rule
the website uses, because a replay shows both players' decks.
"""

import json
import logging
import sqlite3

import discord

import config
from cogs.lfg.helpers import match_type_presentation
from repositories.elo_repo import get_pairing_replay
from utils.avatars import read_deck_avatar

logger = logging.getLogger("discord_bot")

ALERT_LABEL = "Alert my avatar's channel that I'm playing"
ALERT_DESCRIPTION = "Posts in your avatar's channel with a link to the game once you're paired."


def avatar_channel_map() -> dict:
    return getattr(config, "AVATAR_CHANNEL_MAP", None) or {}


def avatar_alerts_enabled() -> bool:
    """The option only shows when at least one avatar channel is set up."""
    return bool(avatar_channel_map())


def avatar_channel_id(avatar: str | None) -> int | None:
    """The channel mapped to an avatar name (case-insensitive), if any."""
    if not avatar:
        return None
    wanted = avatar.strip().lower()
    for name, channel_id in avatar_channel_map().items():
        if str(name).strip().lower() == wanted:
            return channel_id
    return None


def add_avatar_alert_checkbox(modal):
    """Add the alert checkbox at the bottom of a join modal and return it (None when off)."""
    if not avatar_alerts_enabled():
        return None
    checkbox = discord.ui.Checkbox(default=False)
    modal.add_item(discord.ui.Label(
        text=ALERT_LABEL,
        description=ALERT_DESCRIPTION,
        component=checkbox,
    ))
    return checkbox


def alert_ticked(checkbox) -> bool:
    return bool(checkbox is not None and checkbox.value)


def players_share_replays(*player_ids) -> bool:
    """True when every player made "Game Replays" public on their profile."""
    ids = {str(pid) for pid in player_ids if pid}
    if not ids:
        return False
    keys = list(ids) + [f"google_{pid}" for pid in ids]
    conn = sqlite3.connect("match_records.db")
    try:
        rows = conn.execute(
            "SELECT user_id, profile_public_sections FROM user_profiles"
            f" WHERE user_id IN ({','.join('?' * len(keys))})",
            keys,
        ).fetchall()
    except sqlite3.OperationalError:
        return False  # no profiles table yet: nobody has opted in
    finally:
        conn.close()
    public = set()
    for user_id, raw in rows:
        try:
            if raw and json.loads(raw).get("replays"):
                public.add(str(user_id).removeprefix("google_"))
        except (TypeError, ValueError, AttributeError):
            continue
    return ids <= public


def build_alert_message(player_name, avatar, opponent_name, match_type, game_url=None) -> str:
    emoji, label = match_type_presentation(match_type)
    message = (
        f"{emoji} **{player_name}** is playing **{avatar}** in a {label} game "
        f"against **{opponent_name}**!"
    )
    if game_url:
        message += f"\n[Watch the replay]({game_url}) (plays once the game is saved)"
    return message


async def send_avatar_alert(
    bot, *, player_id, player_name, opponent_id, opponent_name,
    pairing_id, match_type, avatar=None, deck_url=None,
):
    """Post the "now playing" alert in the player's avatar channel. Never raises."""
    try:
        if not avatar and deck_url:
            avatar = await read_deck_avatar(deck_url)
        if not avatar:
            logger.info("Avatar alert for %s skipped: no avatar (deck %s)", player_id, deck_url)
            return False
        channel_id = avatar_channel_id(avatar)
        if not channel_id:
            logger.info("Avatar alert for %s skipped: no channel mapped for %s", player_id, avatar)
            return False
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)

        game_url = None
        if match_type != "limited" and players_share_replays(player_id, opponent_id):
            game_url = get_pairing_replay(pairing_id)

        await channel.send(
            build_alert_message(player_name, avatar, opponent_name, match_type, game_url),
            allowed_mentions=discord.AllowedMentions.none(),
            suppress_embeds=True,
        )
        logger.info("Avatar alert sent to %s channel for %s (pairing %s)", avatar, player_id, pairing_id)
        return True
    except Exception:
        logger.exception("Avatar alert failed for %s (pairing %s)", player_id, pairing_id)
        return False
