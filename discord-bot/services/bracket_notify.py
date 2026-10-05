"""DM bracket players their new pairing.

The web app settles bracket results. When a result fills both seats of the
next match, it posts the pairing to the bot's loopback API and this module
DMs each player who they play, in which round, and where to go.
"""

import logging

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

    embed = discord.Embed(
        title=f"{bracket_name}: {round_title}",
        description=(
            f"You advanced! Your next match is ready.\n\n"
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


async def send_pairing_dms(bot, payload: dict) -> list[dict]:
    """DM each player in the pairing. Returns one result per player."""
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

    logger.info(
        "Bracket notify: %s %s, DMed %s of %s players",
        payload.get("bracket_name"), payload.get("round_title"),
        sum(1 for r in results if r["sent"]), len(results),
    )
    return results
