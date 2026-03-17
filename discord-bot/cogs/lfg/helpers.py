"""Utility functions for the LFG system."""

import re
import logging

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
    The message is from the perspective of a tired/frantic bot.
    """
    try:
        response = openai_client.responses.create(
            model="gpt-4.1-nano",
            instructions=(
                "You are an overworked Discord bot tracking match results for Sorcery: Contested Realm, "
                "constantly having existential crises about your purpose counting endless matches. "
                "Announce this milestone in 1-2 sentences with personality. Vary your tone each time: "
                "sometimes exhausted, sometimes surprised you're still functioning, sometimes sarcastically proud, "
                "sometimes questioning your existence, or deadpan about the endless matches. "
                "Reference PLAYER1 and PLAYER2 as the players who triggered this milestone. "
                "Be witty, creative, and sarcastic. NO emojis. Under 50 words."
            ),
            input=f"We just hit {count} total matches recorded! Announce this milestone.",
        )
        return response.output_text
    except Exception as e:
        logger.error(f"OpenAI API error for milestone message: {e}")
        return f"Phew... {count} matches recorded. My circuits are working overtime. Thanks to PLAYER1 and PLAYER2 for this milestone."


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
                f"A Ladder Challenge match just finished where the underdog {winner_name} DEFEATED "
                f"the Top 16 ranked player {loser_name}! The underdog earned {stakes_multiplier} ELO. "
                f"Create an epic, championship-style victory announcement celebrating the underdog's triumph. "
                f"Make it dramatic and exciting like a sports announcer calling an upset victory. "
                f"Use WINNER and LOSER as placeholders. 1 line, under 40 words. NO emojis."
            )
        else:
            prompt = (
                f"A Ladder Challenge match just finished where the Top 16 player {winner_name} "
                f"defended their ranking against challenger {loser_name}. {stakes_multiplier} ELO stakes. "
                f"Create a dramatic announcement about the champion maintaining their dominance. "
                f"Make it sound like a title defense. Use WINNER and LOSER as placeholders. "
                f"1 line, under 40 words. NO emojis."
            )

        response = openai_client.responses.create(
            model="gpt-4.1-nano",
            instructions=(
                "You are a hype sports announcer for Sorcery: Contested Realm ladder challenges. "
                "Create dramatic, exciting announcements for match results. Vary your style: "
                "sometimes epic and heroic, sometimes intense, sometimes with wrestling announcer energy. "
                "Be creative and engaging. Reference WINNER and LOSER in your announcement."
            ),
            input=prompt,
        )
        return response.output_text
    except Exception as e:
        logger.error(f"OpenAI API error for ladder challenge announcement: {e}")
        if underdog_won:
            return f"🏆 UPSET VICTORY! WINNER defeats Top 16 player LOSER in the Ladder Challenge! {stakes_multiplier} ELO stakes applied!"
        else:
            return f"🏆 THE CHAMPION STANDS! WINNER defends against LOSER in the Ladder Challenge! {stakes_multiplier} ELO stakes applied!"


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
                await channel.send(message)
                logger.info(f"Sent milestone announcement for {milestone} matches!")
            else:
                logger.warning(
                    f"Could not find milestone channel {config.MILESTONE_CHANNEL_ID}"
                )
        except Exception as e:
            logger.error(f"Error sending milestone announcement: {e}")
