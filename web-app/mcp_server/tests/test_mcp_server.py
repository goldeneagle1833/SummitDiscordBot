"""Tests for the Summit MCP server.

They run the real tools against a fake site (httpx.MockTransport), so no
database, Flask app or network is needed. Run from web-app/:

    pip install -r mcp_server/requirements.txt pytest
    python -m pytest mcp_server/tests -q
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import re

import httpx
import pytest

pytest.importorskip("mcp")

from mcp_server import safety, tools  # noqa: E402
from mcp_server.site_client import SiteClient, SiteError  # noqa: E402

RANKED_DECK = "https://curiosa.io/decks/rankedsecretdeck123"

PLAYER = {
    "id": "1", "name": "Pete", "wins": 6, "losses": 4, "on_play_win_rate": 60.0, "on_draw_win_rate": 40.0,
    "rank": 3, "displayed_rank": 3, "elo": 1600, "displayed_elo": 1600, "event_elo": 1600,
    "avatar_performance": [{"name": "Sparkmage", "wins": 6, "losses": 4, "win_rate": 60.0}],
    "avatar_matchups": [{"opponent_avatar": "Pathfinder", "wins": 2, "losses": 1, "win_rate": 66.7}],
    "recent_decks": [{"url": RANKED_DECK}],
    "matches": [{
        "date": "2026-11-20T10:00:00", "result": "Win", "opponent": "Amy", "player_avatar": "Sparkmage",
        "opponent_avatar": "Pathfinder", "player_deck_url": RANKED_DECK, "opponent_deck_url": RANKED_DECK,
        "has_deck": True, "replay_url": "https://x/replay",
    }],
}

AVATARS = [{"name": "Sparkmage", "total": 50, "wins": 30, "losses": 20, "win_rate": 60.0,
            "top_player": {"name": "Pete"}},
           {"name": "Pathfinder", "total": 40, "wins": 18, "losses": 22, "win_rate": 45.0}]

EVENTS = {"events": [{"folder": "Cornerstone Ohio", "name": "Cornerstone Ohio", "event_date": "2026-11-01",
                      "format": "Constructed", "player_count": 24, "winner_username": "Ann",
                      "winner_avatar": "Pathfinder", "has_top8": True}]}
EVENT = {"event_name": "Cornerstone Ohio", "format": "Constructed", "event_date_display": "Nov 1, 2026",
         "top8_decks": [{"player": "Ann", "avatar": "Pathfinder", "elements": ["Fire"], "deck_name": "Burn",
                         "deck_id": "top8deck1"}],
         "top8_card_data": [{"name": "Fireball", "deck_percent": "80", "avg_played": "3"}]}

ARCHETYPES = {"status": "ready", "groups": [
    {"id": "pathfinder-fire", "avatar": "Pathfinder", "elementsLabel": "Fire", "name": "Pathfinder · Fire", "size": 9},
    {"id": "sparkmage-air-fire", "avatar": "Sparkmage", "elementsLabel": "Air / Fire", "name": "Sparkmage · Air / Fire", "size": 7},
]}
PATTERNS = {"status": "ready", "patterns": {"spellbook": [
    {"name": "Fireball", "rate": 0.9, "avgCopies": 3},
    {"name": "Lightning Bolt", "rate": 0.8, "avgCopies": 3},
    {"name": "Chain Lightning", "rate": 0.7, "avgCopies": 2},
]}, "decks": {"rankeddeck": {"url": RANKED_DECK}}, "members": ["rankeddeck"]}

REPORTS = {"reports": [{"slug": "2026-11-a", "label": "Nov 1-15, 2026"}]}
REPORT = {"slug": "2026-11-a", "story": ["Fire is up"], "ranked": {
    "tiers": [{"avatar": "Sparkmage", "tier": "S"}],
    "archetypes": [{"avatar": "Sparkmage", "elements": "", "games": 80, "winRate": 54.0, "tier": "S"}],
    "matchups": {"archetypes": [{"avatar": "Sparkmage"}, {"avatar": "Pathfinder"}, {"avatar": "Druid"}],
                 "cells": [[None, {"games": 30, "winRate": 61.0}, {"games": 4, "winRate": None}],
                           [{"games": 30, "winRate": 39.0}, None, None], [None, None, None]]},
    "deckTypes": {"picks": {"Air / Fire|Sparkmage": {"games": 40, "winRate": 55.0, "both": [
        {"avatar": "Pathfinder", "elements": "Fire", "games": 12, "winRate": 40.0},
        {"avatar": "Druid", "elements": "Earth / Water", "games": 10, "winRate": 70.0}]}}},
}, "tournaments": {"events": [{"name": "Cornerstone Ohio", "deckUrl": RANKED_DECK}]}}

CARDS = [{"name": "Fireball", "elements": "Fire"}, {"name": "Lightning Bolt", "elements": "Air"},
         {"name": "Spark", "elements": "Fire"},
         {"name": "Sparkmage", "type": "Avatar"}, {"name": "Pathfinder", "type": "Avatar"}]

def _pm(result, mine, theirs, mine_el, theirs_el, first, minutes, released=True):
    return {"match_id": 1, "date": "2026-11-20T10:00:00", "result": result, "rating_change": 12,
            "rating_change_hidden": False, "on_play": first, "match_time_minutes": minutes,
            "deck_info_released": released,
            "player": {"avatar": mine if released else None, "elements": mine_el if released else None},
            "opponent": {"id": "182857376171294720", "name": "Amy", "avatar": theirs if released else None,
                         "elements": theirs_el if released else None}}


PUBLIC_MATCHES = {"player": {"id": "1", "name": "Pete"}, "deck_info_released_through": "2026-11-15",
                  "record": {"wins": 5, "losses": 5}, "pagination": {"has_next": False}, "matches": [
    _pm("loss", None, None, None, None, False, 40, released=False),
    _pm("win", "Sparkmage", "Druid", ["Air", "Fire"], ["Earth", "Water"], True, 12),
    _pm("loss", "Sparkmage", "Pathfinder", ["Air", "Fire"], ["Fire"], False, 35),
    _pm("loss", "Sparkmage", "Pathfinder", ["Air", "Fire"], ["Fire"], False, 33),
    _pm("loss", "Sparkmage", "Pathfinder", ["Air", "Fire"], ["Fire"], True, 31),
    _pm("win", "Sparkmage", "Druid", ["Air", "Fire"], ["Earth", "Water"], True, 14),
    _pm("win", "Sparkmage", "Druid", ["Air", "Fire"], ["Earth", "Water"], False, 20),
    _pm("win", "Pathfinder", "Druid", ["Fire"], ["Earth", "Water"], True, 18),
    _pm("win", "Sparkmage", "Pathfinder", ["Air", "Fire"], ["Fire"], True, 16),
    _pm("loss", "Sparkmage", "Druid", ["Air", "Fire"], ["Earth", "Water"], False, 45),
]}

MY_CARDS = {"games": 40, "win_rate": 55.0, "cards": [
    {"name": "Fireball", "games": 30, "wins": 20, "losses": 10, "win_rate": 66.7, "win_rate_not_played": 30.0,
     "effect": 36.7, "element": "Fire"},
    {"name": "Spark", "games": 12, "wins": 4, "losses": 8, "win_rate": 33.3, "win_rate_not_played": 64.3,
     "effect": -31.0, "element": "Fire"},
    {"name": "Rare Thing", "games": 2, "wins": 2, "losses": 0, "win_rate": 100.0, "win_rate_not_played": 52.6,
     "effect": 47.4},
]}

STORE = {"products": [
    {"name": "Island Leviathan Pack", "price_cents": 599, "stock_quantity": 3, "description": "2 tokens",
     "product_line": "Tokens", "images": ["https://x/img.png"], "sku": "ISL"},
    {"name": "Horns Pack", "price_cents": 599, "stock_quantity": 0, "description": "", "product_line": None},
], "shipping_rules": {}}


def make_site(calls: list | None = None, overrides: dict | None = None) -> SiteClient:
    overrides = overrides or {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if calls is not None:
            calls.append(str(request.url))
        if path == "/api/site-token":
            return httpx.Response(200, json={"ok": True}, headers={"set-cookie": "summit_site=tok; Path=/api/"})
        assert request.headers.get("X-Site-Token") == "tok"
        assert "X-API-Key" not in request.headers  # an API key would make us an admin
        if path in overrides:
            status, body = overrides[path]
            return httpx.Response(status, json=body)
        if path.startswith("/api/mcp/"):
            # A signed-in player's own data: only with a good player token
            who = {"good": ("1", "Pete"), "other": ("2", "Amy")}.get(request.headers.get("X-Summit-User-Token"))
            if not who:
                return httpx.Response(401, json={"error": "Sign in again from your AI app."})
            if path == "/api/mcp/me":
                return httpx.Response(200, json={"player_id": who[0], "name": who[1], "app": "Claude",
                                                 "profile": f"/player/{who[0]}"})
            if path == "/api/mcp/me/matches":
                newest = _pm("win", "Sparkmage", "Druid", ["Air", "Fire"], ["Earth", "Water"], True, 12)
                return httpx.Response(200, json={**PUBLIC_MATCHES, "matches": [newest] + PUBLIC_MATCHES["matches"][1:]})
            if path == "/api/mcp/me/decks":
                return httpx.Response(200, json={"decks": [{
                    "avatar": "Sparkmage", "elements": ["Air", "Fire"], "games": 6, "wins": 4, "losses": 2,
                    "win_rate": 66.7, "first_played": "2026-11-01T10:00:00", "last_played": "2026-11-20T10:00:00",
                    "against": [{"avatar": "Druid", "wins": 2, "losses": 0}],
                    "cards": {"spellbook": [{"name": "Fireball", "quantity": 3}],
                              "atlas": [{"name": "Volcano", "quantity": 2}]}}] if who[0] == "1" else []})
            if path == "/api/mcp/me/card-stats":
                return httpx.Response(200, json=MY_CARDS if who[0] == "1" else {"games": 0, "cards": []})
        routes = {
            "/api/players/search": {"players": [{"user_id": "1", "display_name": "Pete"}]},
            "/api/player/1": PLAYER,
            "/api/public/players/1/matches": PUBLIC_MATCHES,
            "/api/avatars": AVATARS,
            "/api/avatar/Sparkmage": {"total_matches": 50, "win_rate": 60.0, "play_stats": {"win_rate": 62.0},
                                      "draw_stats": {"win_rate": 58.0}, "wins_matches": [{"deck_url": RANKED_DECK}]},
            "/api/avatar/Pathfinder": {"total_matches": 40, "win_rate": 45.0, "play_stats": {"win_rate": 50.0}},
            "/api/avatar/Sparkmage/matchups": {"matchups": [
                {"opponent": "Pathfinder", "total": 12, "win_rate": 58.3},
                {"opponent": "Druid", "total": 3, "win_rate": 100.0}]},
            "/api/top-8-events": EVENTS,
            "/api/events/Cornerstone Ohio": EVENT,
            "/api/deck-archetypes": ARCHETYPES,
            "/api/deck-archetypes/pathfinder-fire": PATTERNS,
            "/api/deck-archetypes/sparkmage-air-fire": PATTERNS,
            "/api/meta-reports": REPORTS,
            "/api/meta-reports/2026-11-a": REPORT,
            "/api/deck-builder/all-cards": CARDS,
            "/api/store/products": STORE,
            "/api/card/Fireball": {"name": "Fireball", "type": "Magic", "element": "Fire", "wins": 30,
                                   "losses": 20, "total_matches": 50, "win_rate": 60.0, "image": "x.png"},
            "/api/staples": {"success": True, "cards": [{"name": "Fireball", "score": 9.1}]},
            "/api/match-history/recap": {"stats": {"games": 120, "biggest_loser": [1122920529205145712, "Clockwork", -24],
                                                   "broken_streaks": [{"player": "Ann", "player_id": 182857376171294720}]},
                                         "names": {"1122920529205145712": "Clockwork"}, "performers": ["Pete 5-0"]},
            "/api/deck-archetypes/trends": {
                "archetypes": [{"id": "sparkmage-air-fire", "name": "Sparkmage · Air / Fire", "elements": "Air / Fire"},
                               {"id": "pathfinder-fire", "name": "Pathfinder · Fire", "elements": "Fire"}],
                "months": [{"month": "2026-10", "matches": 100,
                            "counts": {"sparkmage-air-fire": 30, "pathfinder-fire": 20}}]},
        }
        if path in routes:
            return httpx.Response(200, json=routes[path])
        if path.startswith("/api/card/"):
            return httpx.Response(404, json={"error": "Card not found"})
        return httpx.Response(404, json={"error": "Not found"})

    return SiteClient(transport=httpx.MockTransport(handler))


def run(coro):
    return asyncio.run(coro)


def everything_but_top8_links(value) -> str:
    return json.dumps(value)


# ----------------------------------------------------------------------
# Safety
# ----------------------------------------------------------------------


def test_strip_deck_data_removes_links_lists_and_snapshots():
    raw = {"player_deck_url": RANKED_DECK, "matches": [{"curiosa_url": RANKED_DECK, "result": "Win",
                                                        "note": f"see {RANKED_DECK}"}],
           "spellbook": [{"name": "Fireball"}], "deck_snapshot": {"x": 1}, "keep": "ok"}
    cleaned = safety.strip_deck_data(raw)
    assert not safety.contains_deck_data(cleaned)
    assert cleaned["keep"] == "ok"
    assert cleaned["matches"][0]["result"] == "Win"


def test_compact_cuts_lists_and_drops_images():
    out = safety.compact({"rows": list(range(100)), "image_url": "x", "text": "a" * 2000})
    assert len(out["rows"]) == safety.MAX_LIST + 1
    assert "image_url" not in out
    assert len(out["text"]) < 700


@pytest.mark.parametrize("call", [
    lambda s: tools.player_lookup(s, "Pete"),
    lambda s: tools.match_history_review(s, "Pete"),
    lambda s: tools.avatar_stats(s),
    lambda s: tools.avatar_stats(s, "sparkmage"),
    lambda s: tools.card_stats(s, "Fireball"),
    lambda s: tools.top_staples(s, "fire"),
    lambda s: tools.meta_report(s),
    lambda s: tools.meta_trends(s),
    lambda s: tools.deck_check(s, deck_list="Avatar: Sparkmage\n3 Fireball\n2 Spark\n3 Lightning Bolt"),
    lambda s: tools.store_products(s),
    lambda s: tools.ranked_recap(s, "daily", "2026-11-26"),
])
def test_no_tool_leaks_a_deck_link(call):
    result = run(call(make_site()))
    assert not safety.contains_deck_data(result), result
    assert "rankedsecretdeck123" not in json.dumps(result)


def test_matchup_prep_only_links_top8_decks():
    result = run(tools.matchup_prep(make_site(), "Sparkmage", "Pathfinder"))
    lists = result.pop("recent_top8_lists")
    assert lists and lists[0]["deck_page"].endswith("/deck-rec/top8deck1")
    assert not safety.contains_deck_data(result)
    assert "rankedsecretdeck123" not in json.dumps(result) + json.dumps(lists)
    assert result["head_to_head"] == {"games": 12, "your_win_rate": 58.3}
    assert result["what_they_usually_play"][0]["cards_to_expect"][0]["card"] == "Fireball"


def test_top8_event_decks_link_to_our_site():
    result = run(tools.top8_event_decks(make_site(), "cornerstone"))
    assert result["top_8"][0]["deck_page"] == "https://sorcererssummit.com/deck-rec/top8deck1"
    assert "curiosa" not in json.dumps(result).lower()


# ----------------------------------------------------------------------
# Rules from Bruce
# ----------------------------------------------------------------------


def test_player_lookup_has_no_rank_or_rating():
    result = run(tools.player_lookup(make_site(), "Pete"))
    text = json.dumps(result).lower()
    assert "rank\"" not in text and "elo" not in text and "1600" not in text
    assert result["ranked_record"] == {"wins": 6, "losses": 4, "games": 10, "win_rate": 60.0}


def test_avatar_list_has_no_top_player():
    result = run(tools.avatar_stats(make_site()))
    assert "Pete" not in json.dumps(result)
    assert result["avatars"][0]["avatar"] == "Sparkmage"


def test_staples_never_sends_a_custom_date_range():
    calls: list = []
    run(tools.top_staples(make_site(calls), "Fire", season="all"))
    staples = [c for c in calls if "/api/staples" in c]
    assert staples and all("from=" not in c and "through=" not in c for c in staples)


def test_no_pso_address_in_the_server_code():
    root = pathlib.Path(__file__).resolve().parents[1]
    for path in root.glob("*.py"):
        text = path.read_text()
        assert not re.search(r"playsorceryonline|sorcery\s*online\.com|ranked[-_]analytics", text, re.IGNORECASE), path


def test_store_shows_public_fields_only():
    result = run(tools.store_products(make_site()))
    first = result["products"][0]
    assert first == {"product": "Island Leviathan Pack", "price": "$5.99", "in_stock": True,
                     "description": "2 tokens", "line": "Tokens"}
    assert result["products"][1]["in_stock"] is False


def test_deck_check_compares_with_tournament_archetype():
    result = run(tools.deck_check(make_site(), deck_list="Avatar: Sparkmage\n3 Fireball\n3 Lightning Bolt\n2 Spark"))
    assert result["deck_type"] == "Air / Fire"
    assert result["compared_with"]["archetype"] == "Sparkmage · Air / Fire"
    assert [c["card"] for c in result["common_cards_you_dont_run"]] == ["Chain Lightning"]
    assert result["deck_type_in_ranked"]["hardest_matchups"][0]["avatar"] == "Pathfinder"


def test_deck_check_rejects_other_sites():
    with pytest.raises(SiteError):
        run(tools.deck_check(make_site(), deck_url="https://evil.example/deck"))


def test_parse_deck_text_sections():
    deck = tools.parse_deck_text("Avatar: Sparkmage\nSpellbook\n3x Fireball\nAtlas\n4 Spring River")
    assert deck["avatar"][0]["name"] == "Sparkmage"
    assert deck["spellbook"] == [{"name": "Fireball", "quantity": 3}]
    assert deck["atlas"] == [{"name": "Spring River", "quantity": 4}]


# ----------------------------------------------------------------------
# Site client
# ----------------------------------------------------------------------


def test_answers_are_cached():
    calls: list = []
    site = make_site(calls)
    run(_twice(site))
    assert sum("/api/avatars" in c for c in calls) == 1


async def _twice(site):
    await site.get(site.path("avatars", event="all"))
    await site.get(site.path("avatars", event="all"))


def test_site_errors_become_friendly_messages():
    site = make_site(overrides={"/api/avatars": (500, {"error": "Traceback ..."})})
    with pytest.raises(SiteError) as exc:
        run(site.get(site.path("avatars")))
    assert "Traceback" not in str(exc.value)


def test_unknown_avatar_lists_the_real_ones():
    with pytest.raises(SiteError) as exc:
        run(tools.avatar_stats(make_site(), "Nobody"))
    assert "Sparkmage" in str(exc.value)


def test_server_registers_tools_and_prompts():
    from mcp_server import server

    names = {t.name for t in run(server.mcp.list_tools())}
    assert {"player_lookup", "avatar_stats", "card_stats", "top_staples", "meta_report", "meta_trends",
            "top8_events", "top8_event_decks", "top8_card_search", "matchup_prep", "deck_check",
            "store_products", "ranked_recap", "match_history_review"} == names
    assert "leaderboard" not in " ".join(names)
    assert len(run(server.mcp.list_prompts())) == 6
    account = {t.name for t in run(server.mcp_account.list_tools())}
    assert account == names | {"my_account", "my_match_review", "my_card_stats", "my_decks"}
    assert len(run(server.mcp_account.list_prompts())) == 7


def test_rate_limit_per_visitor():
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from mcp_server.server import RateLimit

    inner = Starlette(routes=[Route("/mcp", lambda r: PlainTextResponse("ok"), methods=["POST"])])
    client = TestClient(RateLimit(inner, limit=3))
    codes = [client.post("/mcp", headers={"X-Real-IP": "1.1.1.1"}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    assert client.post("/mcp", headers={"X-Real-IP": "2.2.2.2"}).status_code == 200


def test_port_does_not_clash_with_the_bot_api():
    """The bot's matchmaking API listens on 8765; sharing it broke /mcp on 2026-11-27."""
    root = pathlib.Path(__file__).resolve().parents[3]
    bot_api = (root / "discord-bot" / "services" / "matchmaking_api.py").read_text()
    bot_port = re.search(r'MATCHMAKING_BOT_API_PORT", "(\d+)"', bot_api).group(1)
    unit = (root / "web-app" / "systemd" / "summit-mcp.service").read_text()
    nginx = (root / "web-app" / "nginx" / "summit-web-cloudflare.conf").read_text()
    from mcp_server import server

    assert str(server.PORT) != bot_port
    assert f"SUMMIT_MCP_PORT={server.PORT}" in unit
    assert f"127.0.0.1:{server.PORT};" in nginx


def test_avatar_names_never_load_the_slow_all_time_page():
    calls: list = []
    run(tools.matchup_prep(make_site(calls), "sparkmage", "pathfinder"))
    assert not any("/api/avatars" in c and "event=all" in c for c in calls)


def test_recap_drops_discord_ids():
    result = run(tools.ranked_recap(make_site(), "daily", "2026-11-26"))
    text = json.dumps(result)
    assert "1122920529205145712" not in text and "182857376171294720" not in text
    assert "Clockwork" in text and "Ann" in text


def test_meta_trends_names_archetypes_and_counts_elements():
    result = run(tools.meta_trends(make_site()))
    assert result["months"][0]["top_archetypes"][0]["archetype"] == "Sparkmage · Air / Fire"
    shares = result["element_share_by_month_pct"][0]
    assert shares["Fire"] == 100.0 and shares["Air"] == 60.0 and shares["Water"] == 0.0


def test_match_history_review_coaching_numbers():
    calls: list = []
    result = run(tools.match_history_review(make_site(calls), "Pete"))
    assert result["games_reviewed"] == 10
    assert result["record"] == {"wins": 5, "losses": 5, "win_rate": 50.0}
    assert result["main_avatar"] == "Sparkmage"
    pathfinder = next(r for r in result["main_avatar_matchups"] if r["against"] == "Pathfinder")
    assert (pathfinder["wins"], pathfinder["losses"]) == (1, 3)
    assert pathfinder["everyone_with_this_avatar_win_rate"] == 61.0
    druid = next(r for r in result["main_avatar_matchups"] if r["against"] == "Druid")
    assert druid["everyone_with_this_avatar_win_rate"] is None  # too few games in the report
    assert "Nov 1-15, 2026" in result["compared_with"]
    assert result["toughest_opponent_avatars"][0]["against"] == "Pathfinder"
    first = {r["turn_order"]: r for r in result["going_first_vs_second"]}
    assert first["going first"]["wins"] == 4 and first["going second"]["losses"] == 4
    assert result["form"]["current_streak"] == "1 loss"
    assert result["form"]["longest_losing_streak"] == 3
    assert any("Meta Report release" in n for n in result["notes"])
    spark = next(r for r in result["avatars_played"] if r["avatar"] == "Sparkmage")
    assert spark["everyone_win_rate"] == 54.0  # latest Meta Report, not a thin season start
    # The public API asks callers to name themselves
    assert any("/api/public/players/1/matches" in c and "site=" in c for c in calls)


def test_match_history_review_has_no_rating_ids_or_opponent_names():
    text = json.dumps(run(tools.match_history_review(make_site(), "Pete")))
    assert "rating" not in text
    assert "Amy" not in text
    assert "182857376171294720" not in text


def test_match_history_review_no_games():
    empty = {"player": {"id": "1"}, "matches": [], "pagination": {"has_next": False}}
    site = make_site(overrides={"/api/public/players/1/matches": (200, empty)})
    result = run(tools.match_history_review(site, "Pete"))
    assert result["games"] == 0 and "no ranked games" in result["message"]
    assert "  " not in result["message"]


def test_public_review_offers_the_signed_in_connector():
    result = run(tools.match_history_review(make_site(), "Pete"))
    assert "/mcp/account" in result["deeper_review"]


def test_my_match_review_uses_own_games_and_card_stats():
    result = run(tools.my_match_review(make_site(), "good"))
    assert result["signed_in"] is True and result["player"] == "Pete"
    assert result["recent_games"][0]["my_avatar"] == "Sparkmage"  # newest game not held back
    assert not any("Meta Report release" in n for n in result["notes"])
    cards = result["card_stats"]
    assert cards["lifts_you_most"][0]["card"] == "Fireball"
    assert cards["drags_you_down"][0]["card"] == "Spark"
    assert all(c["card"] != "Rare Thing" for c in cards["most_played"])  # under the minimum games
    text = json.dumps(result)
    assert "rating" not in text and "Amy" not in text and "rankedsecretdeck123" not in text


def test_player_answers_are_never_shared_between_players():
    site = make_site()
    mine = run(tools.my_card_stats(site, "good"))
    theirs = run(tools.my_card_stats(site, "other"))
    assert mine["most_played"] and not theirs["most_played"]


def test_expired_sign_in_gets_a_clear_message():
    with pytest.raises(SiteError) as err:
        run(tools.my_account(make_site(), "expired"))
    assert "sign-in has expired" in str(err.value)


def test_token_verifier_asks_the_site(monkeypatch):
    from mcp_server import server

    monkeypatch.setattr(server, "_site", make_site())
    good = run(server.SiteTokenVerifier().verify_token("good"))
    assert good is not None and good.subject == "1" and "summit:read" in good.scopes
    assert run(server.SiteTokenVerifier().verify_token("nope")) is None


def test_signed_in_connector_asks_for_sign_in_and_public_one_does_not(monkeypatch):
    from starlette.testclient import TestClient

    from mcp_server import server

    monkeypatch.setattr(server, "_site", make_site())
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    with TestClient(server.Connectors(server.mcp.streamable_http_app(), server.mcp_account.streamable_http_app())) as c:
        r = c.post("/mcp/account", json=init, headers=headers)
        assert r.status_code == 401
        assert "oauth-protected-resource/mcp/account" in r.headers["www-authenticate"]
        meta = c.get("/.well-known/oauth-protected-resource/mcp/account").json()
        assert meta["resource"].endswith("/mcp/account") and meta["authorization_servers"]
        assert c.post("/mcp/account", json=init, headers={**headers, "Authorization": "Bearer nope"}).status_code == 401
        assert c.post("/mcp/account", json=init, headers={**headers, "Authorization": "Bearer good"}).status_code == 200
        assert c.post("/mcp", json=init, headers=headers).status_code == 200


def test_my_decks_shows_own_lists_only_to_the_signed_in_player():
    result = run(tools.my_decks(make_site(), "good"))
    deck = result["decks"][0]
    assert deck["cards"]["spellbook"] == [{"name": "Fireball", "quantity": 3}]
    assert deck["elements"] == "Air / Fire" and deck["win_rate"] == 66.7
    assert run(tools.my_decks(make_site(), "other"))["decks"] == []
    with pytest.raises(SiteError):
        run(tools.my_decks(make_site(), "nope"))


def test_public_connector_has_no_deck_list_tool():
    from mcp_server import server

    assert "my_decks" not in {t.name for t in run(server.mcp.list_tools())}


# ----------------------------------------------------------------------
# Usage log (admin page "AI Apps (MCP)")
# ----------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _usage_db(tmp_path, monkeypatch):
    """Every test logs to its own throwaway file, never web-app/mcp_usage.db."""
    from mcp_server import usage

    monkeypatch.setattr(usage, "DB_PATH", tmp_path / "mcp_usage.db")
    return tmp_path / "mcp_usage.db"


def _rows(path):
    import sqlite3

    conn = sqlite3.connect(str(path))
    try:
        return conn.execute("SELECT connector, tool, outcome, caller, calls FROM mcp_usage_daily "
                            "ORDER BY connector, tool, outcome").fetchall()
    finally:
        conn.close()


def _call_tool(client, path, name, arguments, token=None):
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
               "X-Real-IP": "9.9.9.9"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    return client.post(path, json=body, headers=headers)


def test_tool_calls_are_counted_by_connector_tool_and_outcome(monkeypatch, _usage_db):
    import time as _time

    from starlette.testclient import TestClient

    from mcp_server import server, usage

    monkeypatch.setattr(server, "_site", make_site())
    # A session manager can only run once; another test already ran these
    monkeypatch.setattr(server.mcp, "_session_manager", None)
    monkeypatch.setattr(server.mcp_account, "_session_manager", None)
    with TestClient(server.create_app()) as c:
        assert _call_tool(c, "/mcp", "avatar_stats", {}).status_code == 200
        assert _call_tool(c, "/mcp", "avatar_stats", {}).status_code == 200
        assert _call_tool(c, "/mcp", "avatar_stats", {"avatar": "Nobody"}).status_code == 200
        assert _call_tool(c, "/mcp/account", "my_account", {}, token="good").status_code == 200
        assert _call_tool(c, "/mcp/account", "avatar_stats", {}, token="good").status_code == 200
        for _ in range(50):  # logging runs off the event loop
            if sum(r[4] for r in _rows(_usage_db)) >= 5:
                break
            _time.sleep(0.02)

    rows = _rows(_usage_db)
    public_ip = usage.caller_key(ip="9.9.9.9")
    player = usage.caller_key(player_id="1")
    assert ("public", "avatar_stats", "ok", public_ip, 2) in rows
    assert ("public", "avatar_stats", "no_result", public_ip, 1) in rows
    assert ("account", "my_account", "ok", player, 1) in rows
    assert ("account", "avatar_stats", "ok", player, 1) in rows
    # Only one-way keys are stored: no IP address or player id
    assert all("9.9.9.9" not in r[3] and r[3] not in ("1", "p:1") for r in rows)

    s = usage.summary(7)
    assert s["totals"]["calls"] == 5 and s["totals"]["public"] == 3 and s["totals"]["account"] == 2
    assert s["totals"]["players"] == 1 and s["totals"]["visitors"] == 1 and s["totals"]["no_result"] == 1
    top = s["by_tool"][0]
    assert top["tool"] == "avatar_stats" and top["calls"] == 4 and top["players"] == 1 and top["visitors"] == 1


def test_rate_limited_calls_are_counted(_usage_db):
    import time as _time

    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from mcp_server import usage
    from mcp_server.server import RateLimit

    inner = Starlette(routes=[Route("/mcp", lambda r: PlainTextResponse("ok"), methods=["POST"])])
    client = TestClient(RateLimit(inner, limit=1))
    assert [client.post("/mcp", headers={"X-Real-IP": "1.1.1.1"}).status_code for _ in range(3)] == [200, 429, 429]
    for _ in range(50):
        if _rows(_usage_db) and _rows(_usage_db)[0][4] >= 2:
            break
        _time.sleep(0.02)
    assert _rows(_usage_db) == [("public", usage.RATE_LIMITED_TOOL, "limited", usage.caller_key(ip="1.1.1.1"), 2)]


def test_usage_summary_days_and_pruning(tmp_path):
    from datetime import datetime, timedelta, timezone

    from mcp_server import usage

    db = tmp_path / "u.db"
    now = datetime(2026, 11, 28, 12, tzinfo=timezone.utc)
    usage._last_prune = 0.0
    usage.record("public", "meta_report", "ok", "ip:a", 120, now=now - timedelta(days=100), path=db)
    usage._last_prune = 0.0
    usage.record("public", "meta_report", "ok", "ip:a", 100, now=now - timedelta(days=2), path=db)
    usage.record("account", "my_decks", "error", "p:x", 300, now=now, path=db)
    s = usage.summary(7, now=now, path=db)
    assert len(s["by_day"]) == 7 and s["totals"]["calls"] == 2 and s["totals"]["error"] == 1
    assert {t["tool"]: t["avg_ms"] for t in s["by_tool"]} == {"meta_report": 100, "my_decks": 300}
    assert s["by_day"][-1]["players"] == 1
    assert usage.summary(1, now=now, path=db)["totals"]["calls"] == 1
    # The 100-day-old row was pruned
    assert usage.summary(90, now=now, path=db)["totals"]["calls"] == 2


def test_usage_summary_with_no_file_yet(tmp_path):
    from mcp_server import usage

    s = usage.summary(7, path=tmp_path / "missing.db")
    assert s["totals"]["calls"] == 0 and len(s["by_day"]) == 7 and s["by_tool"] == []
