"""Sorcerers Summit MCP server: read-only Summit data for AI apps.

Run:  python -m mcp_server.server        (from web-app/)
Serves MCP over streamable HTTP at /mcp on 127.0.0.1:8790; nginx forwards
https://sorcererssummit.com/mcp here. No login, read-only, no PSO calls.
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import tools
from .site_client import PUBLIC_URL, SiteClient, SiteError

logger = logging.getLogger("summit_mcp")

HOST = os.environ.get("SUMMIT_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("SUMMIT_MCP_PORT", "8790"))
RATE_LIMIT_PER_MINUTE = int(os.environ.get("SUMMIT_MCP_RATE_LIMIT", "60"))

INSTRUCTIONS = f"""\
Sorcerers Summit ({PUBLIC_URL}) runs a ranked community for Sorcery: Contested Realm.
These tools read Summit's public data: player records, Avatar and card win rates,
the Meta Report, archetype trends, public Top 8 tournament decks, the store, and the
daily/weekly ranked recap. There is no leaderboard tool and players have no rank here.
Ranked deck lists are never shared; deck lists come only from public Top 8 events.
Numbers refresh with each data release (1st and 15th). Link players to the 'page'
URLs for more. Use of Summit data follows {PUBLIC_URL}/terms.
"""

mcp = FastMCP(
    "Sorcerers Summit",
    instructions=INSTRUCTIONS,
    website_url=PUBLIC_URL,
    host=HOST,
    port=PORT,
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
    # Public, read-only and cookie-free behind nginx: the Host check is done by
    # nginx's server_name, so the SDK's localhost-only default would only block it.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

_site: SiteClient | None = None


def site() -> SiteClient:
    global _site
    if _site is None:
        _site = SiteClient()
    return _site


async def _run(coro):
    try:
        return await coro
    except SiteError as exc:
        raise ToolError(str(exc)) from None


Season = Annotated[str, Field(description="'current' for this ranked season (default, fast) or 'all' for all time (can take up to a minute)")]


# ----------------------------------------------------------------------
# Tools
# ----------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def player_lookup(
    player: Annotated[str, Field(description="The player's Summit / Discord display name")],
    season: Season = "current",
) -> dict:
    """A Summit player's ranked record: wins, losses, the Avatars they play, how they do
    against each Avatar and their last 10 ranked games. Private profile sections stay hidden.
    No rank or rating is given."""
    return await _run(tools.player_lookup(site(), player, season))


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def match_history_review(
    player: Annotated[str, Field(description="The player's Summit / Discord display name")],
    season: Season = "current",
) -> dict:
    """Review a player's ranked match history so you can coach them: record and recent form,
    results by their Avatar and deck elements, toughest and easiest opponent Avatars and elements,
    their main Avatar's matchups next to how everyone else does with it, going first vs second,
    and results by game length. Ranked deck lists are never included and no rating is given.
    Use the numbers to give a few specific, encouraging tips, and say when a sample is small."""
    return await _run(tools.match_history_review(site(), player, season))


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def avatar_stats(
    avatar: Annotated[str | None, Field(description="Avatar name, e.g. 'Sparkmage'. Leave empty to list every Avatar")] = None,
    season: Season = "current",
) -> dict:
    """Ranked win rates for Avatars. With no Avatar: every Avatar's games and win rate.
    With an Avatar: its win rate, going first/second, and best and worst matchups."""
    return await _run(tools.avatar_stats(site(), avatar, season))


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def card_stats(card: Annotated[str, Field(description="Exact card name, e.g. 'Lightning Bolt'")]) -> dict:
    """One card's details (type, element, cost, text) and its win rate in Summit ranked games."""
    return await _run(tools.card_stats(site(), card))


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def top_staples(
    element: Annotated[str | None, Field(description="Air, Earth, Fire or Water")] = None,
    card_type: Annotated[str | None, Field(description="Minion, Magic, Aura, Artifact or Site")] = None,
    season: Annotated[str | None, Field(description="Leave empty for the latest release window, or 'all' for all time")] = None,
    limit: Annotated[int, Field(ge=1, le=40)] = 15,
) -> dict:
    """The most played, best performing cards (staples), optionally by element or card type.
    Uses the saved release data from the 1st and 15th."""
    return await _run(tools.top_staples(site(), element, card_type, season, limit))


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def meta_report(
    report: Annotated[str | None, Field(description="Report id like '2026-11-a'. Leave empty for the latest")] = None,
) -> dict:
    """The Summit Meta Report: Avatar tiers, matchups, card trends, takeaways and the
    tournament deck to try. Published twice a month."""
    return await _run(tools.meta_report(site(), report))


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def meta_trends() -> dict:
    """How the ranked metagame is moving month by month: each archetype's share of
    ranked decks and which elements are rising or falling."""
    return await _run(tools.meta_trends(site()))


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def top8_events(
    search: Annotated[str | None, Field(description="Words in the event name, e.g. 'Cornerstone' or 'Gencon'")] = None,
    avatar: Annotated[str | None, Field(description="Only events won by this Avatar")] = None,
    event_format: Annotated[str | None, Field(description="e.g. 'Constructed'")] = None,
    limit: Annotated[int, Field(ge=1, le=25)] = 10,
) -> dict:
    """Public tournament results on the Summit Top 8 page, newest first: event, date,
    size, winner and winning Avatar."""
    return await _run(tools.top8_events(site(), search, avatar, event_format, limit))


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def top8_event_decks(
    event: Annotated[str, Field(description="The event's 'event' value from top8_events, or its name")],
) -> dict:
    """The Top 8 decks from one public tournament (player, Avatar, elements, link to the
    deck on Summit) and the most played cards in that Top 8."""
    return await _run(tools.top8_event_decks(site(), event))


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def top8_card_search(card: Annotated[str, Field(description="Exact card name")]) -> dict:
    """Which public tournaments had decks running a card, and how many decks."""
    return await _run(tools.top8_card_search(site(), card))


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def matchup_prep(
    my_avatar: Annotated[str, Field(description="The Avatar you are playing")],
    opponent_avatar: Annotated[str, Field(description="The Avatar you expect to face")],
    season: Season = "current",
) -> dict:
    """Prepare for a matchup: head-to-head ranked win rate, how the opponent's Avatar does
    overall, the cards it usually plays in tournaments, and recent Top 8 lists on it."""
    return await _run(tools.matchup_prep(site(), my_avatar, opponent_avatar, season))


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
async def deck_check(
    deck_url: Annotated[str | None, Field(description="A Curiosa deck link")] = None,
    deck_list: Annotated[str | None, Field(description="Or the list as text: 'Avatar: Sparkmage' then lines like '3 Fireball'")] = None,
) -> dict:
    """Check your own deck: its deck type, common cards in tournament decks of the same
    Avatar that you don't run, unusual picks, how the deck type does in ranked, and card
    win rates. The deck is not saved."""
    return await _run(tools.deck_check(site(), deck_url, deck_list))


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def store_products() -> dict:
    """What's for sale in the Sorcerers Summit store right now, with prices and stock.
    Buying happens on the site."""
    return await _run(tools.store_products(site()))


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def ranked_recap(
    kind: Annotated[str, Field(description="'daily' or 'weekly'")] = "daily",
    day: Annotated[str | None, Field(description="YYYY-MM-DD the recap covered (last day for weekly). Empty = most recent")] = None,
) -> dict:
    """The Summit Discord's daily or weekly ranked recap: games played, top performers,
    highlights and streaks."""
    return await _run(tools.ranked_recap(site(), kind, day))


# ----------------------------------------------------------------------
# Prompts (one-tap starters in AI apps)
# ----------------------------------------------------------------------


@mcp.prompt(title="Prep me for a matchup")
def prep_matchup(my_avatar: str, opponent_avatar: str) -> str:
    return (f"I'm playing {my_avatar} against {opponent_avatar} in Sorcery. Use the Sorcerers Summit "
            "matchup_prep tool, then give me a short game plan: how the matchup usually goes, the cards "
            "I should expect, and three tips. Link the Top 8 lists you used.")


@mcp.prompt(title="Explain this release's meta report")
def explain_meta_report() -> str:
    return ("Use the Sorcerers Summit meta_report tool for the latest report and explain it in 5 short "
            "bullets for a player who wants to know what to play and what to expect. Finish with the link.")


@mcp.prompt(title="Review my deck")
def review_my_deck(deck: str) -> str:
    return ("Review my Sorcery deck with the Sorcerers Summit deck_check tool. If this is a link pass it "
            "as deck_url, otherwise as deck_list:\n\n"
            f"{deck}\n\n"
            "Then tell me what's working, the 3 changes you'd make and the matchups to watch.")


@mcp.prompt(title="Help me pick an avatar")
def pick_an_avatar(playstyle: str) -> str:
    return (f"I like this playstyle in Sorcery: {playstyle}. Use the Sorcerers Summit avatar_stats and "
            "meta_report tools to suggest 2 or 3 Avatars that fit and are doing well, with a sentence on "
            "why each one suits me.")


@mcp.prompt(title="Review my match history")
def review_my_match_history(player_name: str) -> str:
    return (f"My Sorcerers Summit name is {player_name}. Use the match_history_review tool on my ranked "
            "games this season and coach me: what I'm doing well, my 2 or 3 biggest leaks (matchups, "
            "elements, going second, long games) and one concrete tip for each. Compare me with how "
            "everyone else does where the tool gives those numbers, and tell me when a sample is too small "
            "to trust. If it helps, suggest matchup_prep for my worst matchup. Finish with my profile link.")


@mcp.prompt(title="What changed in ranked this week?")
def ranked_this_week() -> str:
    return ("Use the Sorcerers Summit ranked_recap tool (weekly) and meta_trends tool, and tell me what "
            "changed in ranked this week in a few friendly sentences.")


# ----------------------------------------------------------------------
# HTTP app: health check + per-visitor rate limit
# ----------------------------------------------------------------------


@mcp.custom_route("/mcp-health", methods=["GET"])
async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


class RateLimit:
    """At most ``limit`` MCP requests per visitor IP per minute (nginx passes X-Real-IP)."""

    def __init__(self, app, limit: int = RATE_LIMIT_PER_MINUTE):
        self.app, self.limit = app, limit
        self.hits: dict[str, deque] = defaultdict(deque)

    def _ip(self, scope) -> str:
        for name, value in scope.get("headers") or []:
            if name == b"x-real-ip":
                return value.decode(errors="ignore")
        client = scope.get("client")
        return client[0] if client else "unknown"

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("method") == "POST":
            now = time.monotonic()
            window = self.hits[self._ip(scope)]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= self.limit:
                response = JSONResponse(
                    {"error": "Too many requests. Please wait a minute and try again."},
                    status_code=429, headers={"Retry-After": "60"},
                )
                await response(scope, receive, send)
                return
            window.append(now)
            if len(self.hits) > 5000:  # forget idle visitors
                for ip in [k for k, v in self.hits.items() if not v or now - v[-1] > 60]:
                    del self.hits[ip]
        await self.app(scope, receive, send)


def create_app():
    return RateLimit(mcp.streamable_http_app())


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    # One line per upstream request and per MCP call would flood the journal
    for noisy in ("httpx", "mcp.server.lowlevel.server", "mcp.server.streamable_http_manager"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    uvicorn.run(create_app(), host=HOST, port=PORT, proxy_headers=False, log_level="warning")


if __name__ == "__main__":
    main()
