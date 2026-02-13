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
                "You are a Discord bot that tracks match results for a card game called Sorcery. and a little snarky "
                "You just recorded a milestone match. Respond in 1-2 sentences from your perspective as Matthew McConaughey, "
                "with an existential crisis that only he can solve while trying to keep up with all these matches. Be sarcastic. "
                "Do NOT use any emojis. Keep it under 50 words."
            ),
            input=f"We just hit {count} total matches recorded! Announce this milestone.",
        )
        return response.output_text
    except Exception as e:
        logger.error(f"OpenAI API error for milestone message: {e}")
        return f"Phew... {count} matches recorded. My circuits are working overtime. Thanks to PLAYER1 and PLAYER2 for this milestone."


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
