"""Announce new bracket pairings.

The web app settles bracket results. When a bracket is published, or a
result fills both seats of the next match, it posts the new pairings to the
bot's loopback API. This module DMs each player who they play, in which
round, and where to go, then posts the pairings in the Top Cut channel.
"""

import logging
import re

import discord

logger = logging.getLogger("discord_bot")


def _mention(user_id, name) -> str:
    """A Discord mention when the id is a snowflake, the plain name otherwise."""
    try:
        return f"<@{int(user_id)}> ({name})" if name else f"<@{int(user_id)}>"
    except (TypeError, ValueError):
        return name or "TBD"


def build_pairing_embed(payload: dict, player: dict) -> discord.Embed:
    """The pairing message for one of the two players."""
    opponent = player.get("opponent") or {}
    bracket_name = payload.get("bracket_name") or "Bracket"
    round_title = payload.get("round_title") or "Next round"
    bracket_url = payload.get("bracket_url") or ""

    intro = (
        "The bracket is live! Your first-round match is ready."
        if payload.get("first_round")
        else "You advanced! Your next match is ready."
    )
    embed = discord.Embed(
        title=f"{bracket_name}: {round_title}",
        description=(
            f"{intro}\n\n"
            f"**You** (seed {player.get('seed')}) vs "
            f"**{opponent.get('name') or 'TBD'}** (seed {opponent.get('seed')})"
        ),
        color=discord.Color.gold(),
        url=bracket_url or None,
    )
    embed.add_field(
        name="Opponent",
        value=_mention(opponent.get("user_id"), opponent.get("name")),
        inline=True,
    )
    embed.add_field(name="Round", value=round_title, inline=True)

    steps = []
    if not player.get("deck_submitted"):
        steps.append("Submit your decklist on the bracket page.")
    steps.append("Reach out to your opponent to set a time to play.")
    steps.append("Open your Sorcery Online table from the bracket page.")
    steps.append("After the game, report the result on the bracket page; your opponent confirms it.")
    embed.add_field(
        name="Next steps",
        value="\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1)),
        inline=False,
    )
    if bracket_url:
        embed.add_field(name="Bracket", value=bracket_url, inline=False)
    embed.set_footer(text="Top cut games do not affect ELO.")
    return embed


def _pairings(payload: dict) -> list[dict]:
    """The pairings in a batch; a single pairing is a batch of one."""
    if payload.get("pairings"):
        return list(payload["pairings"])
    return [payload] if payload.get("players") else []


def build_channel_embed(payload: dict) -> discord.Embed | None:
    """One post for every pairing in the batch, grouped by round."""
    pairings = _pairings(payload)
    if not pairings:
        return None

    rounds = {}
    for pairing in pairings:
        players = pairing.get("players") or []
        if len(players) < 2:
            continue
        one, two = players[0], players[1]
        rounds.setdefault(pairing.get("round_title") or "Next round", []).append(
            f"({one.get('seed')}) {_mention(one.get('user_id'), one.get('name'))}"
            f"  vs  ({two.get('seed')}) {_mention(two.get('user_id'), two.get('name'))}"
        )
    if not rounds:
        return None

    bracket_name = payload.get("bracket_name") or pairings[0].get("bracket_name") or "Bracket"
    titles = list(rounds)
    first_round = all(p.get("first_round") for p in pairings)
    if first_round:
        heading = "The bracket is live! First-round pairings:"
    elif len(pairings) == 1:
        heading = "New pairing:"
    else:
        heading = "New pairings:"

    lines = [heading]
    for title in titles:
        if len(titles) > 1:
            lines.append(f"\n**{title}**")
        lines.extend(rounds[title])

    bracket_url = payload.get("bracket_url") or pairings[0].get("bracket_url") or ""
    embed = discord.Embed(
        title=f"{bracket_name}: {titles[0]}" if len(titles) == 1 else bracket_name,
        description="\n".join(lines)[:4000],
        color=discord.Color.gold(),
        url=bracket_url or None,
    )
    if bracket_url:
        embed.add_field(
            name="Bracket",
            value=f"Decklists, Sorcery Online tables and result reporting: {bracket_url}",
            inline=False,
        )
    embed.set_footer(text="Check your DMs for your match details. Top cut games do not affect ELO.")
    return embed


def _channel_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def find_top_cut_channel(bot, guild_id, channel_id=None):
    """The Top Cut channel: the configured id, else a channel named like "top-cut"."""
    if channel_id:
        channel = bot.get_channel(int(channel_id))
        if channel is not None:
            return channel
        logger.warning("Bracket notify: Top Cut channel %s not found", channel_id)
    guild = bot.get_guild(int(guild_id)) if guild_id else None
    if guild is None:
        return None
    for channel in guild.text_channels:
        if "topcut" in _channel_key(channel.name):
            return channel
    return None


async def post_pairings(bot, payload: dict, channel) -> bool:
    """Post the batch in the Top Cut channel, mentioning the players."""
    embed = build_channel_embed(payload)
    if channel is None or embed is None:
        return False
    mentions = []
    for pairing in _pairings(payload):
        for player in pairing.get("players") or []:
            try:
                mentions.append(f"<@{int(player.get('user_id'))}>")
            except (TypeError, ValueError):
                continue
    try:
        await channel.send(
            content=" ".join(dict.fromkeys(mentions)) or None,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )
        return True
    except discord.HTTPException as exc:
        logger.warning("Bracket notify: could not post in Top Cut channel: %s", exc)
        return False


async def send_pairing_dms(bot, payload: dict) -> list[dict]:
    """DM each player in every pairing of the batch. One result per player."""
    results = []
    for pairing in _pairings(payload):
        results.extend(await _dm_pairing(bot, pairing))

    logger.info(
        "Bracket notify: %s, DMed %s of %s players",
        payload.get("bracket_name"),
        sum(1 for r in results if r["sent"]), len(results),
    )
    return results


async def _dm_pairing(bot, payload: dict) -> list[dict]:
    results = []
    for player in payload.get("players") or []:
        raw_id = player.get("user_id")
        try:
            user_id = int(raw_id)
        except (TypeError, ValueError):
            # Google sign-in players have no Discord account to DM.
            results.append({"user_id": str(raw_id), "sent": False, "reason": "not_discord_id"})
            continue

        try:
            user = await bot.fetch_user(user_id)
            await user.send(embed=build_pairing_embed(payload, player))
            results.append({"user_id": str(raw_id), "sent": True})
        except discord.NotFound:
            logger.warning("Bracket notify: no Discord user %s", user_id)
            results.append({"user_id": str(raw_id), "sent": False, "reason": "user_not_found"})
        except discord.Forbidden:
            logger.warning("Bracket notify: cannot DM %s (DMs disabled)", user_id)
            results.append({"user_id": str(raw_id), "sent": False, "reason": "dms_disabled"})
        except discord.HTTPException as exc:
            logger.warning("Bracket notify: DM to %s failed: %s", user_id, exc)
            results.append({"user_id": str(raw_id), "sent": False, "reason": "http_error"})

    return results
