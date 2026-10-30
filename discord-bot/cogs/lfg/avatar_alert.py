"""Opt-in "Alert my avatar's channel" for LFG joins.

A player can tick a box in the join modal; when their match is made the bot
posts in the private channel for the avatar they are playing (the same
config.AVATAR_CHANNEL_MAP the stream alerts use), with a link to the live
Play Sorcery Online table. The post never carries a deck link or list, and
never a player's own seat link.

The post lives only while the game does: a one-minute sweep
(:func:`refresh_avatar_alerts`) deletes it once the result is reported (or
the pairing is cancelled or expires). Posts are remembered in the database,
so a bot restart still cleans them up.
"""

import datetime
import logging
import sqlite3

import discord

import config
from cogs.lfg.helpers import match_type_presentation
from repositories.elo_repo import create_active_pairings_table, get_db_connection, get_pairing_table
from utils.avatars import read_deck_avatar

logger = logging.getLogger("discord_bot")

ALERT_LABEL = "Alert my avatar's channel that I'm playing"
ALERT_DESCRIPTION = "Posts in your avatar's channel with a link to your game. Removed once it's reported."
# An alert is removed after this long even if the result was never reported
ALERT_MAX_AGE = datetime.timedelta(hours=6)


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


# ── Storage ──


def create_avatar_alerts_table():
    with get_db_connection("match_records.db") as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS avatar_alerts
                        (pairing_id INTEGER NOT NULL,
                         player_id INTEGER NOT NULL,
                         opponent_id INTEGER NOT NULL,
                         channel_id INTEGER NOT NULL,
                         message_id INTEGER NOT NULL,
                         content TEXT NOT NULL,
                         created_at TEXT NOT NULL,
                         PRIMARY KEY (pairing_id, player_id))""")


def save_avatar_alert(pairing_id, player_id, opponent_id, channel_id, message_id, content):
    create_avatar_alerts_table()
    with get_db_connection("match_records.db") as conn:
        conn.execute(
            """INSERT OR REPLACE INTO avatar_alerts
               (pairing_id, player_id, opponent_id, channel_id, message_id, content, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (pairing_id, player_id, opponent_id, channel_id, message_id, content,
             datetime.datetime.now().isoformat()),
        )


def _open_alerts() -> list[dict]:
    """Every stored alert with its pairing's status (None when the pairing is gone)."""
    create_avatar_alerts_table()
    create_active_pairings_table()
    conn = sqlite3.connect("match_records.db")
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT a.*, p.status AS pairing_status
               FROM avatar_alerts a
               LEFT JOIN active_pairings p ON p.pairing_id = a.pairing_id"""
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def _forget_alert(pairing_id, player_id):
    with get_db_connection("match_records.db") as conn:
        conn.execute(
            "DELETE FROM avatar_alerts WHERE pairing_id = ? AND player_id = ?",
            (pairing_id, player_id),
        )


# ── Posting ──


def build_alert_message(player_name, avatar, opponent_name, match_type, table_url=None) -> str:
    emoji, label = match_type_presentation(match_type)
    message = (
        f"{emoji} **{player_name}** is playing **{avatar}** in a {label} game "
        f"against **{opponent_name}**!"
    )
    if table_url:
        message += f"\n🎮 [Watch the live game]({table_url})"
    return message


async def _get_channel(bot, channel_id):
    return bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)


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
        channel = await _get_channel(bot, channel_id)

        table_url = get_pairing_table(pairing_id) if match_type != "limited" else None
        content = build_alert_message(player_name, avatar, opponent_name, match_type, table_url)
        message = await channel.send(
            content,
            allowed_mentions=discord.AllowedMentions.none(),
            suppress_embeds=True,
        )
        save_avatar_alert(pairing_id, player_id, opponent_id, channel_id, message.id, content)
        logger.info("Avatar alert sent to %s channel for %s (pairing %s)", avatar, player_id, pairing_id)
        return True
    except Exception:
        logger.exception("Avatar alert failed for %s (pairing %s)", player_id, pairing_id)
        return False


def _alert_is_over(alert, now) -> bool:
    if alert.get("pairing_status") != "active":
        return True  # reported, cancelled, expired, or gone
    try:
        created = datetime.datetime.fromisoformat(alert["created_at"])
    except (TypeError, ValueError):
        return True
    return now - created > ALERT_MAX_AGE


async def refresh_avatar_alerts(bot):
    """Delete the alerts whose game is over (reported, cancelled, expired or too old)."""
    now = datetime.datetime.now()
    for alert in _open_alerts():
        if not _alert_is_over(alert, now):
            continue
        pairing_id, player_id = alert["pairing_id"], alert["player_id"]
        try:
            try:
                channel = await _get_channel(bot, alert["channel_id"])
                await channel.get_partial_message(alert["message_id"]).delete()
            except discord.NotFound:
                pass  # already deleted by hand
            _forget_alert(pairing_id, player_id)
            logger.info("Avatar alert for %s (pairing %s) removed", player_id, pairing_id)
        except Exception:
            logger.exception("Could not remove avatar alert for %s (pairing %s)", player_id, pairing_id)
