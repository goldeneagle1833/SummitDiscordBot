"""Sorcerers Summit MCP server: read-only Summit data for AI apps.

Run:  python -m mcp_server.server        (from web-app/)
Serves MCP over streamable HTTP on 127.0.0.1:8790; nginx forwards
https://sorcererssummit.com/mcp here. Read-only, no PSO calls.

Two connectors, one service:
  /mcp           public data, no login
  /mcp/account   the same tools plus the player's own data; AI apps sign in
                 with any Summit login (OAuth, served by the Flask site at
                 /auth/mcp, see services/mcp_oauth.py)
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from typing import Annotated

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import tools
from .site_client import PUBLIC_URL, SignInExpired, SiteClient, SiteError

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

# Public, read-only and cookie-free behind nginx: the Host check is done by
# nginx's server_name, so the SDK's localhost-only default would only block it.
_NO_REBINDING_CHECK = TransportSecuritySettings(enable_dns_rebinding_protection=False)

mcp = FastMCP(
    "Sorcerers Summit",
    instructions=INSTRUCTIONS,
    website_url=PUBLIC_URL,
    host=HOST,
    port=PORT,
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
    transport_security=_NO_REBINDING_CHECK,
)

ACCOUNT_PATH = "/mcp/account"
ACCOUNT_URL = PUBLIC_URL + ACCOUNT_PATH
SCOPE = "summit:read"

ACCOUNT_INSTRUCTIONS = INSTRUCTIONS + """
This connector is signed in as one Summit player. The my_* tools read that player's
own data (their newest games, private Card Stats and their own ranked deck lists) to
coach them. Never share it about anyone else, and never show anyone else's ranked decks.
"""


class SiteTokenVerifier:
    """A bearer token is good when the site says so (/api/mcp/me); the answer is cached a minute."""

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            me = await site().get(site().path("mcp", "me"), ttl=60, user_token=token)
        except SiteError:
            return None
        if not isinstance(me, dict) or not me.get("player_id"):
            return None
        return AccessToken(token=token, client_id="summit-ai-app", scopes=[SCOPE],
                           subject=str(me["player_id"]), resource=ACCOUNT_URL)


mcp_account = FastMCP(
    "Sorcerers Summit (signed in)",
    instructions=ACCOUNT_INSTRUCTIONS,
    website_url=PUBLIC_URL,
    host=HOST,
    port=PORT,
    streamable_http_path=ACCOUNT_PATH,
    stateless_http=True,
    json_response=True,
    transport_security=_NO_REBINDING_CHECK,
    auth=AuthSettings(
        issuer_url=PUBLIC_URL,
        resource_server_url=ACCOUNT_URL,
        required_scopes=[SCOPE],
        validate_token_resource=False,  # the site checks the token itself
        service_documentation_url=f"{PUBLIC_URL}/help",
    ),
    token_verifier=SiteTokenVerifier(),
)


def tool(**kwargs):
    """Register a tool on both connectors."""
    def register(fn):
        mcp.tool(**kwargs)(fn)
        mcp_account.tool(**kwargs)(fn)
        return fn
    return register


def prompt(**kwargs):
    def register(fn):
        mcp.prompt(**kwargs)(fn)
        mcp_account.prompt(**kwargs)(fn)
        return fn
    return register


def _user_token() -> str:
    token = get_access_token()
    if token is None:
        raise ToolError("Sign in first: add the Summit (signed in) connector and sign in.")
    return token.token


_site: SiteClient | None = None


def site() -> SiteClient:
    global _site
    if _site is None:
        _site = SiteClient()
    return _site


async def _run(coro):
    try:
        return await coro
    except SignInExpired as exc:
        raise ToolError(str(exc)) from None
    except SiteError as exc:
        raise ToolError(str(exc)) from None


Season = Annotated[str, Field(description="'current' for this ranked season (default, fast) or 'all' for all time (can take up to a minute)")]


# ----------------------------------------------------------------------
# Tools
# ----------------------------------------------------------------------


@tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def player_lookup(
    player: Annotated[str, Field(description="The player's Summit / Discord display name")],
    season: Season = "current",
) -> dict:
    """A Summit player's ranked record: wins, losses, the Avatars they play, how they do
    against each Avatar and their last 10 ranked games. Private profile sections stay hidden.
    No rank or rating is given."""
    return await _run(tools.player_lookup(site(), player, season))


@tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def match_history_review(
    player: Annotated[str, Field(description="The player's Summit / Discord display name")],
    season: Annotated[str, Field(description="'all' (default): their most recent 300 ranked games across "
                                             "seasons. 'current': this season only")] = "all",
) -> dict:
    """Review a player's ranked match history so you can coach them: record and recent form,
    results by their Avatar and deck elements, toughest and easiest opponent Avatars and elements,
    their main Avatar's matchups next to how everyone else does with it, going first vs second,
    and results by game length. Avatar win rates are compared with everyone's in the latest Meta Report. Ranked deck lists are never included and no rating is given.
    Use the numbers to give a few specific, encouraging tips, and say when a sample is small."""
    return await _run(tools.match_history_review(site(), player, season))


@tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def avatar_stats(
    avatar: Annotated[str | None, Field(description="Avatar name, e.g. 'Sparkmage'. Leave empty to list every Avatar")] = None,
    season: Season = "current",
) -> dict:
    """Ranked win rates for Avatars. With no Avatar: every Avatar's games and win rate.
    With an Avatar: its win rate, going first/second, and best and worst matchups."""
    return await _run(tools.avatar_stats(site(), avatar, season))


@tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def card_stats(card: Annotated[str, Field(description="Exact card name, e.g. 'Lightning Bolt'")]) -> dict:
    """One card's details (type, element, cost, text) and its win rate in Summit ranked games."""
    return await _run(tools.card_stats(site(), card))


@tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def top_staples(
    element: Annotated[str | None, Field(description="Air, Earth, Fire or Water")] = None,
    card_type: Annotated[str | None, Field(description="Minion, Magic, Aura, Artifact or Site")] = None,
    season: Annotated[str | None, Field(description="Leave empty for the latest release window, or 'all' for all time")] = None,
    limit: Annotated[int, Field(ge=1, le=40)] = 15,
) -> dict:
    """The most played, best performing cards (staples), optionally by element or card type.
    Uses the saved release data from the 1st and 15th."""
    return await _run(tools.top_staples(site(), element, card_type, season, limit))


@tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def meta_report(
    report: Annotated[str | None, Field(description="Report id like '2026-11-a'. Leave empty for the latest")] = None,
) -> dict:
    """The Summit Meta Report: Avatar tiers, matchups, card trends, takeaways and the
    tournament deck to try. Published twice a month."""
    return await _run(tools.meta_report(site(), report))


@tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def meta_trends() -> dict:
    """How the ranked metagame is moving month by month: each archetype's share of
    ranked decks and which elements are rising or falling."""
    return await _run(tools.meta_trends(site()))


@tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def top8_events(
    search: Annotated[str | None, Field(description="Words in the event name, e.g. 'Cornerstone' or 'Gencon'")] = None,
    avatar: Annotated[str | None, Field(description="Only events won by this Avatar")] = None,
    event_format: Annotated[str | None, Field(description="e.g. 'Constructed'")] = None,
    limit: Annotated[int, Field(ge=1, le=25)] = 10,
) -> dict:
    """Public tournament results on the Summit Top 8 page, newest first: event, date,
    size, winner and winning Avatar."""
    return await _run(tools.top8_events(site(), search, avatar, event_format, limit))


@tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def top8_event_decks(
    event: Annotated[str, Field(description="The event's 'event' value from top8_events, or its name")],
) -> dict:
    """The Top 8 decks from one public tournament (player, Avatar, elements, link to the
    deck on Summit) and the most played cards in that Top 8."""
    return await _run(tools.top8_event_decks(site(), event))


@tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def top8_card_search(card: Annotated[str, Field(description="Exact card name")]) -> dict:
    """Which public tournaments had decks running a card, and how many decks."""
    return await _run(tools.top8_card_search(site(), card))


@tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def matchup_prep(
    my_avatar: Annotated[str, Field(description="The Avatar you are playing")],
    opponent_avatar: Annotated[str, Field(description="The Avatar you expect to face")],
    season: Season = "current",
) -> dict:
    """Prepare for a matchup: head-to-head ranked win rate, how the opponent's Avatar does
    overall, the cards it usually plays in tournaments, and recent Top 8 lists on it."""
    return await _run(tools.matchup_prep(site(), my_avatar, opponent_avatar, season))


@tool(annotations={"readOnlyHint": True, "openWorldHint": True})
async def deck_check(
    deck_url: Annotated[str | None, Field(description="A Curiosa deck link")] = None,
    deck_list: Annotated[str | None, Field(description="Or the list as text: 'Avatar: Sparkmage' then lines like '3 Fireball'")] = None,
) -> dict:
    """Check your own deck: its deck type, common cards in tournament decks of the same
    Avatar that you don't run, unusual picks, how the deck type does in ranked, and card
    win rates. The deck is not saved."""
    return await _run(tools.deck_check(site(), deck_url, deck_list))


@tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def store_products() -> dict:
    """What's for sale in the Sorcerers Summit store right now, with prices and stock.
    Buying happens on the site."""
    return await _run(tools.store_products(site()))


@tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def ranked_recap(
    kind: Annotated[str, Field(description="'daily' or 'weekly'")] = "daily",
    day: Annotated[str | None, Field(description="YYYY-MM-DD the recap covered (last day for weekly). Empty = most recent")] = None,
) -> dict:
    """The Summit Discord's daily or weekly ranked recap: games played, top performers,
    highlights and streaks."""
    return await _run(tools.ranked_recap(site(), kind, day))


# ----------------------------------------------------------------------
# Signed-in connector only: the player's own data
# ----------------------------------------------------------------------

_OWN = {"readOnlyHint": True, "openWorldHint": False}


@mcp_account.tool(annotations=_OWN)
async def my_account() -> dict:
    """Which Summit player this connector is signed in as, with their profile link."""
    return await _run(tools.my_account(site(), _user_token()))


@mcp_account.tool(annotations=_OWN)
async def my_match_review(
    season: Annotated[str, Field(description="'all' (default): your most recent 300 ranked games. "
                                             "'current': this season only")] = "all",
) -> dict:
    """Coach the signed-in player from their OWN ranked games: everything match_history_review
    gives (record, form, Avatars, matchups vs everyone in the Meta Report, going first/second,
    game length) including their newest games, plus their private Card Stats: the cards that
    lift or drag their win rate. Use this, not match_history_review, when they ask about
    themselves. No rating is given; for their actual deck lists use my_decks."""
    return await _run(tools.my_match_review(site(), _user_token(), season))


@mcp_account.tool(annotations=_OWN)
async def my_card_stats(
    season: Annotated[str, Field(description="'all' (default) or 'current' for this season")] = "all",
) -> dict:
    """The signed-in player's own ranked Card Stats: most-played cards and which cards go with
    winning or losing (win rate when played vs not played). Private on their profile."""
    return await _run(tools.my_card_stats(site(), _user_token(), season))


@mcp_account.tool(annotations=_OWN)
async def my_decks(
    season: Annotated[str, Field(description="'all' (default): decks from your recent ranked games. "
                                             "'current': this season only")] = "all",
) -> dict:
    """The signed-in player's OWN ranked deck lists (up to 10, newest first), each with its full
    card list and its record, including results against each opponent Avatar. Use it to give
    card-by-card advice on decks they actually played. Only for this player; never anyone else's."""
    return await _run(tools.my_decks(site(), _user_token(), season))


@mcp_account.prompt(title="Coach me from my games (signed in)")
def coach_me() -> str:
    return ("Use the Sorcerers Summit my_match_review tool and coach me: what I'm doing well, my 2 or 3 "
            "biggest leaks (matchups, elements, going second, long games, cards that drag my win rate) and "
            "one concrete tip for each. Use my_decks to look at the actual lists I played. Compare me with everyone where the numbers allow and say when a "
            "sample is too small. Finish with my profile link.")


# ----------------------------------------------------------------------
# Prompts (one-tap starters in AI apps)
# ----------------------------------------------------------------------


@prompt(title="Prep me for a matchup")
def prep_matchup(my_avatar: str, opponent_avatar: str) -> str:
    return (f"I'm playing {my_avatar} against {opponent_avatar} in Sorcery. Use the Sorcerers Summit "
            "matchup_prep tool, then give me a short game plan: how the matchup usually goes, the cards "
            "I should expect, and three tips. Link the Top 8 lists you used.")


@prompt(title="Explain this release's meta report")
def explain_meta_report() -> str:
    return ("Use the Sorcerers Summit meta_report tool for the latest report and explain it in 5 short "
            "bullets for a player who wants to know what to play and what to expect. Finish with the link.")


@prompt(title="Review my deck")
def review_my_deck(deck: str) -> str:
    return ("Review my Sorcery deck with the Sorcerers Summit deck_check tool. If this is a link pass it "
            "as deck_url, otherwise as deck_list:\n\n"
            f"{deck}\n\n"
            "Then tell me what's working, the 3 changes you'd make and the matchups to watch.")


@prompt(title="Help me pick an avatar")
def pick_an_avatar(playstyle: str) -> str:
    return (f"I like this playstyle in Sorcery: {playstyle}. Use the Sorcerers Summit avatar_stats and "
            "meta_report tools to suggest 2 or 3 Avatars that fit and are doing well, with a sentence on "
            "why each one suits me.")


@prompt(title="Review my match history")
def review_my_match_history(player_name: str) -> str:
    return (f"My Sorcerers Summit name is {player_name}. Use the match_history_review tool on my recent "
            "ranked games and coach me: what I'm doing well, my 2 or 3 biggest leaks (matchups, "
            "elements, going second, long games) and one concrete tip for each. Compare me with how "
            "everyone else does where the tool gives those numbers, and tell me when a sample is too small "
            "to trust. If it helps, suggest matchup_prep for my worst matchup. Finish with my profile link.")


@prompt(title="What changed in ranked this week?")
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


class Connectors:
    """One ASGI app for both connectors: /mcp/account (and its sign-in metadata) or /mcp."""

    def __init__(self, public_app, account_app):
        self.public_app, self.account_app = public_app, account_app

    @staticmethod
    def _is_account(path: str) -> bool:
        return (path == ACCOUNT_PATH or path.startswith(ACCOUNT_PATH + "/")
                or path.startswith("/.well-known/oauth-protected-resource"))

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self._lifespan(receive, send)
            return
        app = self.account_app if self._is_account(scope.get("path", "")) else self.public_app
        await app(scope, receive, send)

    async def _lifespan(self, receive, send):
        from contextlib import AsyncExitStack

        message = await receive()
        if message["type"] != "lifespan.startup":
            return
        async with AsyncExitStack() as stack:
            try:
                await stack.enter_async_context(mcp.session_manager.run())
                await stack.enter_async_context(mcp_account.session_manager.run())
            except Exception as exc:  # pragma: no cover
                await send({"type": "lifespan.startup.failed", "message": str(exc)})
                return
            await send({"type": "lifespan.startup.complete"})
            message = await receive()
        await send({"type": "lifespan.shutdown.complete"})


def create_app():
    return RateLimit(Connectors(mcp.streamable_http_app(), mcp_account.streamable_http_app()))


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    # One line per upstream request and per MCP call would flood the journal
    for noisy in ("httpx", "mcp.server.lowlevel.server", "mcp.server.streamable_http_manager"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    uvicorn.run(create_app(), host=HOST, port=PORT, proxy_headers=False, log_level="warning")


if __name__ == "__main__":
    main()
