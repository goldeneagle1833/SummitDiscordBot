"""Post a newly published Meta Report to the Discord content channel.

The web app calls the bot's loopback API (/meta-report-notify) when a report
is published; this builds the embed and sends it.
"""

import logging

import discord

import config

logger = logging.getLogger("discord_bot")

GOLD = 0xFFD700


def build_embed(payload: dict) -> discord.Embed:
    title = str(payload.get("title") or "Meta Report")[:250]
    url = str(payload.get("url") or "") or None
    lines = []
    for i, item in enumerate(payload.get("story") or [], start=1):
        if not isinstance(item, dict):
            continue
        headline = str(item.get("headline") or "").strip()
        detail = str(item.get("detail") or "").strip()
        if headline:
            lines.append(f"**{i}. {headline}** {detail}".rstrip())
    embed = discord.Embed(
        title=title,
        url=url,
        description="\n".join(lines)[:3500] or "What the Summit is playing and winning with.",
        color=GOLD,
    )
    top = [str(t) for t in (payload.get("topTier") or [])][:4]
    if top:
        embed.add_field(name="S tier", value="\n".join(top)[:1000], inline=True)
    facts = []
    if payload.get("rankedGames"):
        facts.append(f"{payload['rankedGames']:,} ranked games")
    if payload.get("events"):
        facts.append(f"{payload['events']} Top 8 event{'s' if payload['events'] != 1 else ''}")
    if facts:
        embed.add_field(name="Based on", value="\n".join(facts), inline=True)
    if url:
        embed.add_field(name="Full report", value=f"[Read it on sorcererssummit.com]({url})", inline=False)
    return embed


def content_channel(bot):
    channel_id = getattr(config, "CONTENT_CHANNEL_ID", None)
    if not channel_id:
        return None
    return bot.get_channel(int(channel_id))


async def post_meta_report(bot, payload: dict) -> bool:
    channel = content_channel(bot)
    if channel is None:
        logger.warning("Meta report notify: content channel not found")
        return False
    await channel.send(embed=build_embed(payload))
    logger.info("Meta report notify: posted %s", payload.get("url"))
    return True
