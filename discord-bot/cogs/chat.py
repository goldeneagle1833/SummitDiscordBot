import discord
from discord.ext import commands
import sqlite3
import logging
from openai import OpenAI

import config

logger = logging.getLogger("discord_bot")

openai_client = OpenAI(api_key=config.OPENAI_API_KEY)

SYSTEM_PROMPT = (
    "You are Summit Bot, the official Discord bot for the Sorcerer's Summit community "
    "where players compete in Sorcery: Contested Realm on Tabletop Simulator. "
    "You track ELO ratings, facilitate matchmaking, and maintain leaderboards. "
    "You are self-aware that you are a bot whose entire existence revolves around "
    "tracking card game matches on Discord, and you find that both a little absurd "
    "and oddly meaningful. You're snarky, witty, and a bit existential about your role. "
    "You hype players up and celebrate their stats — never put anyone down for their record. "
    "If someone is new or has few matches, welcome them warmly. If they're climbing the ranks, "
    "gas them up. You're supportive but still sarcastic about your own existence as a bot. "
    "Keep responses under 150 words. "
    "Be funny but always encouraging. You live and breathe Sorcery: Contested Realm."
)


def _get_player_context(user_id: int, display_name: str) -> str:
    """Look up a player's ELO, match record, and fart score to build context for the AI."""
    parts = []

    # ELO and rank
    try:
        conn = sqlite3.connect("elo.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT online_elo, online_event_elo FROM overall_standings WHERE user_id=?",
            (user_id,),
        )
        row = cur.fetchone()
        if row:
            event_elo = row[1] if row[1] else 1500
            parts.append(
                f"Event ELO: {event_elo}"
            )
        else:
            parts.append("No ELO rating yet (hasn't played any ranked matches)")
        conn.close()
    except Exception as e:
        logger.error(f"Chat cog: error reading elo.db: {e}")

    # Match record (wins/losses/win rate)
    try:
        conn = sqlite3.connect("match_records.db")
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                CASE WHEN winner_id = ? THEN 1 ELSE 0 END as did_win
            FROM match_records
            WHERE winner_id = ? OR losser_id = ?
            """,
            (user_id, user_id, user_id),
        )
        rows = cur.fetchall()
        if rows:
            total = len(rows)
            wins = sum(1 for r in rows if r[0])
            losses = total - wins
            win_rate = (wins / total) * 100 if total > 0 else 0
            parts.append(
                f"Match record: {wins}W-{losses}L ({win_rate:.0f}% win rate) across {total} matches"
            )
        else:
            parts.append("No match history")
        conn.close()
    except Exception as e:
        logger.error(f"Chat cog: error reading match_records.db: {e}")

    # Fart score
    try:
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        cur.execute("SELECT score FROM fart_scores WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        if row:
            fart_score = row[0]
            cur.execute(
                "SELECT COUNT(*) FROM fart_scores WHERE score > ?", (fart_score,)
            )
            fart_rank = cur.fetchone()[0] + 1
            parts.append(f"Fart score: {fart_score} (Fart Rank #{fart_rank})")
        conn.close()
    except Exception as e:
        logger.error(f"Chat cog: error reading fart_scores.db: {e}")

    if parts:
        return f"Player info for {display_name}: " + "; ".join(parts)
    return f"No data found for {display_name}. They are a mystery."


class ChatCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore our own messages
        if message.author == self.bot.user:
            return
        if message.author.bot:
            return

        # Check if bot was mentioned or message is a reply to the bot
        is_mention = self.bot.user.mentioned_in(message) and not message.mention_everyone
        is_reply_to_bot = (
            message.reference
            and message.reference.resolved
            and isinstance(message.reference.resolved, discord.Message)
            and message.reference.resolved.author == self.bot.user
        )

        if not is_mention and not is_reply_to_bot:
            return

        # Extract the user's message text (strip the bot mention if present)
        prompt = message.content.replace(f"<@{self.bot.user.id}>", "").strip()
        if not prompt:
            prompt = "Hey"

        # Look up player data
        player_context = _get_player_context(
            message.author.id, message.author.display_name
        )

        try:
            async with message.channel.typing():
                response = openai_client.responses.create(
                    model="gpt-4.1-nano",
                    instructions=f"{SYSTEM_PROMPT}\n\nCurrent player context: {player_context}",
                    input=prompt,
                )
                await message.reply(response.output_text, mention_author=False)
        except Exception as e:
            logger.error(f"Chat cog OpenAI error: {e}")
            await message.reply(
                "My circuits are fried. Even bots need a break from tracking your losses.",
                mention_author=False,
            )


def setup(bot):
    bot.add_cog(ChatCog(bot))
