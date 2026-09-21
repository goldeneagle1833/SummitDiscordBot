"""Utility functions for the LFG system."""

import re
import logging

import discord

import config
from utils.database import check_milestone

logger = logging.getLogger("discord_bot")

# URL pattern for scrubbing URLs from public fallback channel messages
_URL_PATTERN = re.compile(r"https?://\S+")

# Channel where a player asks for a mis-reported result to be fixed.  The live
# config file predates this setting, so fall back to the Summit server channel.
MATCH_CORRECTION_CHANNEL_ID = getattr(
    config, "MATCH_CORRECTION_CHANNEL_ID", 1456299008023728302
)


def scrub_urls(text: str) -> str:
    """Remove URLs from a message to avoid leaking deck links in public channels."""
    return _URL_PATTERN.sub("[link removed]", text)


def correction_tip(match_id=None) -> str:
    """The one place that tells players how to fix a wrongly reported result.

    Pass ``match_id`` wherever the match is already recorded so the command
    can be copied as-is; before that there is no id yet to name.
    """
    command = f"!correct_match {match_id}" if match_id else "!correct_match <match id>"
    return (
        f"🛠️ **Wrong result reported?** Run `{command}` in "
        f"<#{MATCH_CORRECTION_CHANNEL_ID}> — the other player confirms the fix "
        f"and ELO is recalculated."
    )


def outstanding_match_tip() -> str:
    """Tip for a message about a match that is already recorded.

    "Report Last Match" only ever hands back buttons for a pairing that is
    still active, so it cannot reopen the match this message is about - it is
    there for a different match the player has yet to report.
    """
    return (
        f"💡 **Another match still unreported?** Click "
        f"**📋 Report Last Match** in <#{config.LFG_CHANNEL_ID}> for its buttons."
    )


_MATCH_TYPE_PRESENTATION = {
    "limited": ("🎲", "Limited"),
    "ranked": ("⚔️", "Ranked"),
    "rumble": ("💥", "Rumble"),
    "points": ("📊", "Rumble (Omens)"),
}
_CASUAL_PRESENTATION = ("⭐", "Casual")


def match_type_presentation(match_type):
    """Return the (emoji, label) pair every message for this match type uses."""
    return _MATCH_TYPE_PRESENTATION.get(match_type or "ranked", _CASUAL_PRESENTATION)


def deck_text_if_private(interaction, deck_text: str) -> str:
    """Keep a deck line only where it stays private, i.e. in a bot DM.

    A match card normally lives in the player's DMs, but for players who
    block DMs it lives in the public fallback channel instead - and a reply
    there is visible to everyone, so the deck list has to be left out.
    """
    return deck_text if interaction.guild is None else ""


def generate_milestone_message(count: int) -> str:
    """Milestone announcement text with PLAYER1/PLAYER2 placeholders for mentions."""
    return (
        f"From the nothingness between worlds, I carve the rune of {count} into the void itself. "
        f"PLAYER1 and PLAYER2, your deeds echo even here, in the nothing."
    )


def generate_ladder_challenge_announcement(underdog_won: bool, winner_name: str, loser_name: str, stakes_multiplier: str) -> str:
    """Ladder challenge announcement text with WINNER/LOSER placeholders for mentions."""
    if underdog_won:
        return f"Nice one! WINNER takes down Top 16 player LOSER in the Ladder Challenge! {stakes_multiplier} ELO stakes applied."
    return f"WINNER holds strong against LOSER in the Ladder Challenge! {stakes_multiplier} ELO stakes applied."


async def send_milestone_announcement(
    bot, winner_id: int, loser_id: int, match_id: int
):
    """
    Check if we hit a milestone and send an announcement if so.

    Args:
        bot: The Discord bot instance
        winner_id: The ID of the winning player
        loser_id: The ID of the losing player
        match_id: The match ID that was just recorded
    """
    milestone = check_milestone(match_id)
    if milestone:
        try:
            channel = bot.get_channel(config.MILESTONE_CHANNEL_ID)
            if channel:
                # Replace placeholders with actual mentions
                message = generate_milestone_message(milestone)
                message = message.replace("PLAYER1", f"<@{winner_id}>")
                message = message.replace("PLAYER2", f"<@{loser_id}>")
                embed = discord.Embed(
                    title=f"Match Milestone: {milestone} Games!",
                    description=message,
                    color=discord.Color.gold(),
                )
                embed.set_footer(text="Sorcery: Contested Realm")
                await channel.send(embed=embed)
                logger.info(f"Sent milestone announcement for {milestone} matches!")
            else:
                logger.warning(
                    f"Could not find milestone channel {config.MILESTONE_CHANNEL_ID}"
                )
        except Exception as e:
            logger.error(f"Error sending milestone announcement: {e}")
