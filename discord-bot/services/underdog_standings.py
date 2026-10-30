"""The underdog bracket standings card on the leaderboard message.

The underdog bracket takes the best player on each of the season's 8 weakest
avatars (see web-app/services/underdog_bracket.py). This card shows who it
would take right now, so players can see where they stand. The pick comes
from the web app (GET /api/brackets/underdog-standings), the same one the
admin's New bracket preview makes, so the card and the draft always agree.

Avatars an admin leaves out of a season's underdog bracket are only chosen
when the bracket is drafted, so the card keeps its own list per season:
config.UNDERDOG_LEFT_OUT ({season name: [avatars]}) overrides the default.
"""

import logging

import aiohttp
import discord

import config

logger = logging.getLogger("discord_bot")

STANDINGS_URL = "http://127.0.0.1:5000/api/brackets/underdog-standings"
CARD_TITLE = "Underdog Bracket Standings"
# Bruce's Season 8 call: Frostmage and Lavamancer stay out of the underdog bracket.
DEFAULT_LEFT_OUT = {"season 8": ("Frostmage", "Lavamancer")}
# Skipped avatars and the next ones up, shown under the 8.
NEXT_UP_SHOWN = 3


def left_out_for(event_name) -> list[str]:
    """Avatars left out of this season's underdog bracket."""
    table = getattr(config, "UNDERDOG_LEFT_OUT", DEFAULT_LEFT_OUT)
    wanted = str(event_name or "").strip().lower()
    for name, avatars in table.items():
        if str(name).strip().lower() == wanted:
            return list(avatars)
    return []


async def fetch_standings(event_id, exclude) -> dict | None:
    """The web app's underdog pick for a season, or None when it can't be read."""
    params = {"event": str(event_id)}
    if exclude:
        params["exclude"] = ",".join(exclude)
    headers = {}
    api_key = getattr(config, "WEB_APP_API_KEY", "")
    if api_key:
        headers["X-API-Key"] = api_key
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                STANDINGS_URL, params=params, headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    logger.warning("Underdog standings: web app answered %s", resp.status)
                    return None
                data = await resp.json()
    except Exception as e:
        logger.warning("Underdog standings: could not reach the web app: %s", e)
        return None
    return data if data.get("success") else None


def build_embed(standings: dict, left_out=()) -> discord.Embed | None:
    """The card: the 8 weakest avatars with a player, weakest first."""
    if not standings or not standings.get("event"):
        return None
    esc = discord.utils.escape_markdown
    min_games = standings.get("min_games", 10)
    names = {p["avatar"]: p for p in standings.get("players", [])}
    avatars = standings.get("avatars", [])

    rows = []
    for a in avatars:
        p = names.get(a["avatar"])
        if not p:
            continue
        rows.append(
            f"{len(rows) + 1}. **{esc(a['avatar'])}** ({a['avatar_score']}) — "
            f"{esc(str(p['display_name']))}, {p['avatar_score']} ({p['wins']}-{p['losses']})"
        )

    # Below the 8: avatars weaker than the last one in that nobody qualifies
    # on yet, then the next weakest avatars waiting for a spot.
    last_in = max((i for i, a in enumerate(avatars) if a["avatar"] in names), default=-1)
    skipped = [
        a["avatar"] for a in avatars[:last_in]
        if a["avatar"] not in names and not a.get("excluded")
    ]
    next_up = [
        a["avatar"] for a in avatars[last_in + 1:]
        if a["avatar"] not in names and not a.get("excluded")
    ][:NEXT_UP_SHOWN]

    parts = ["\n".join(rows) if rows else f"No avatar has a player with {min_games} games yet."]
    notes = []
    if skipped:
        notes.append(f"**Open:** {', '.join(esc(s) for s in skipped)} (no one with {min_games} games, or its players took another avatar)")
    if next_up:
        notes.append(f"**Next up:** {', '.join(esc(s) for s in next_up)}")
    if left_out:
        notes.append(f"**Left out:** {', '.join(esc(s) for s in left_out)}")
    if notes:
        parts.append("\n".join(notes))

    embed = discord.Embed(
        title=CARD_TITLE,
        description="\n\n".join(parts)[:4096],
        color=discord.Color.dark_teal(),
    )
    embed.set_footer(
        text=(
            f"The 8 lowest Avatar Scores each send their best player ({min_games}+ games on it). "
            "One avatar per player. Avatar score in brackets, then the player's score and record."
        )
    )
    return embed


async def underdog_embed(active_event) -> discord.Embed | None:
    """The card for the running season, or None (no season, or the site is down)."""
    if not active_event:
        return None
    left_out = left_out_for(active_event.get("event_name"))
    standings = await fetch_standings(active_event["event_id"], left_out)
    return build_embed(standings, left_out)
