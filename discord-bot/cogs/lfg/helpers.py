"""Utility functions for the LFG system."""

import re
import logging

import discord
from openai import OpenAI

import config
from utils.database import check_milestone

logger = logging.getLogger("discord_bot")

openai_client = OpenAI(api_key=config.OPENAI_API_KEY)

# URL pattern for scrubbing URLs from public fallback channel messages
_URL_PATTERN = re.compile(r"https?://\S+")


def scrub_urls(text: str) -> str:
    """Remove URLs from a message to avoid leaking deck links in public channels."""
    return _URL_PATTERN.sub("[link removed]", text)


def generate_milestone_message(count: int) -> str:
    """
    Generate a milestone message using ChatGPT.
    Fantasy Bard of the Void themed milestone announcement.
    """
    try:
        response = openai_client.responses.create(
            model="gpt-4.1-nano",
            instructions=(
                "You are a wandering bard drifting through the cosmic nothingness between worlds. "
                "You chronicle milestones of Sorcery: Contested Realm as legends whispered across the void. "
                "Describe the milestone number as a rune carved into the emptiness itself. "
                "PLAYER1 and PLAYER2 are heroes whose deeds have reached even you, out here in the nothing. "
                "You MUST include the exact number of games in the announcement. "
                "Be poetic, whimsical, and speak with the wonder of one who has seen infinite worlds rise and fall. "
                "NO emojis. 2-3 sentences, under 60 words."
            ),
            input=f"We just hit {count} games played! Announce this milestone.",
        )
        return response.output_text
    except Exception as e:
        logger.error(f"OpenAI API error for milestone message: {e}")
        return f"From the nothingness between worlds, I carve the rune of {count} into the void itself. PLAYER1 and PLAYER2, your deeds echo even here, in the nothing."


def generate_ladder_challenge_announcement(underdog_won: bool, winner_name: str, loser_name: str, stakes_multiplier: str) -> str:
    """
    Generate a stylized ladder challenge announcement using ChatGPT.

    Args:
        underdog_won: True if the non-Top 16 player won, False if Top 16 player won
        winner_name: Display name of the winner
        loser_name: Display name of the loser
        stakes_multiplier: String like "2.0x/0.5x" or "Normal"

    Returns:
        Announcement text with WINNER and LOSER placeholders for mentions
    """
    try:
        if underdog_won:
            prompt = (
                f"A Ladder Challenge match just finished where the underdog {winner_name} beat "
                f"the Top 16 ranked player {loser_name}. The underdog earned {stakes_multiplier} ELO. "
                f"Create a fun, upbeat announcement celebrating the underdog's win. "
                f"Keep the tone lighthearted and conversational, not over-the-top dramatic. "
                f"Use WINNER and LOSER as placeholders. 1 line, under 40 words. NO emojis."
            )
        else:
            prompt = (
                f"A Ladder Challenge match just finished where the Top 16 player {winner_name} "
                f"held their ranking against challenger {loser_name}. {stakes_multiplier} ELO stakes. "
                f"Create a short, casual announcement about the champion keeping their spot. "
                f"Keep it lighthearted and conversational, not over-the-top dramatic. "
                f"Use WINNER and LOSER as placeholders. 1 line, under 40 words. NO emojis."
            )

        response = openai_client.responses.create(
            model="gpt-4.1-nano",
            instructions=(
                "You are a chill announcer for Sorcery: Contested Realm ladder challenges. "
                "Create fun, engaging announcements for match results. Vary your style but "
                "keep it casual and lighthearted — not overly dramatic or intense. "
                "Be creative and conversational. Reference WINNER and LOSER in your announcement."
            ),
            input=prompt,
        )
        return response.output_text
    except Exception as e:
        logger.error(f"OpenAI API error for ladder challenge announcement: {e}")
        if underdog_won:
            return f"Nice one! WINNER takes down Top 16 player LOSER in the Ladder Challenge! {stakes_multiplier} ELO stakes applied."
        else:
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
                # Generate message from ChatGPT and replace placeholders with actual mentions
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
