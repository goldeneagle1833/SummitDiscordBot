"""Event import: the official sorcerytcg.com standings order must drive placement.

Covers both consumers of the event page: the Explorer standings import
(ExplorerService) and the Top 8 deck import (CuriosaService).
"""

import json

from services.curiosa import CuriosaService
from services.explorer import ExplorerService

# Trimmed from the live sorcerytcg.com event page markup (Sept 2026).
_ROW = (
    '<div class="flex min-w-0 items-center gap-3">'
    '<span class="w-5 shrink-0 text-center font-title text-lg">{pos}</span>'
    '<div class="min-w-0"><div class="flex min-w-0 items-center gap-2">'
    '<button type="button" class="block cursor-pointer truncate font-title '
    'underline underline-offset-2 hover:text-primary">{name}</button>'
    '</div></div></div>'
)


def _page(*names):
    return "".join(_ROW.format(pos=i + 1, name=n) for i, n in enumerate(names))


def _rsc_page(*chunks):
    """Wrap payload text the way Next.js streams it into the page."""
    return "".join(
        "<script>self.__next_f.push([1,%s])</script>" % json.dumps(chunk)
        for chunk in chunks
    )


def _standings_payload(*entries):
    """Payload text carrying an event.standings array like the live page."""
    rows = [
        {
            "id": reg_id,
            "status": "Ready",
            "user": f"$1a:json:event:players:{i}:user",
            "position": i + 1,
            "score": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "avatar": {
                "name": avatar,
                # Nested arrays and a bracket inside a string must not confuse
                # the array extraction.
                "printings": [{"meta": {"image": f"https://cdn/{avatar}].png"}}],
            },
        }
        for i, (reg_id, avatar) in enumerate(entries)
    ]
    return '1a:{"json":{"event":{"phases":[],"standings":' + json.dumps(rows) + ',"topcut":null}}}\n'


def _player(uid, name, swiss_wins, reg_id=None):
    seats = [
        {"round": {"phase": {"structure": "Swiss"}}, "result": {"result": "Win", "score": 3}}
        for _ in range(swiss_wins)
    ]
    return {
        "id": reg_id or f"reg-{uid}",
        "status": "Ready",
        "user": {"id": uid, "displayname": name},
        "seats": seats,
    }


# ── Page parsing ──────────────────────────────────────────────────────────


def test_parses_current_page_markup():
    standings = ExplorerService._parse_page_standings(_page("Kevin F", "Tom &amp; Jerry", "Niraj A"))
    assert standings == {"Kevin F": 1, "Tom & Jerry": 2, "Niraj A": 3}


def test_parses_legacy_page_markup():
    legacy = (
        '<span class="w-4 text-center font-title text-lg">1</span>'
        '<span class="truncate font-title">Kevin F</span>'
    )
    assert ExplorerService._parse_page_standings(legacy) == {"Kevin F": 1}


def test_parses_embedded_standings_by_registration():
    page = _rsc_page(_standings_payload(("r1", "Pathfinder"), ("r2", "Battlemage")))
    assert ExplorerService._parse_registration_standings(page) == {"r1": 1, "r2": 2}


def test_embedded_standings_survive_chunk_boundary():
    payload = _standings_payload(("r1", "Pathfinder"), ("r2", "Battlemage"), ("r3", "Druid"))
    cut = payload.index('"r2"') + 2  # split mid-token, inside the array
    page = _rsc_page("0:[]\n", payload[:cut], payload[cut:])
    assert ExplorerService._parse_registration_standings(page) == {"r1": 1, "r2": 2, "r3": 3}


def test_embedded_standings_missing_returns_empty():
    assert ExplorerService._parse_registration_standings("") == {}
    assert ExplorerService._parse_registration_standings(_page("A", "B")) == {}
    assert ExplorerService._parse_registration_standings(_rsc_page('1a:{"json":{"standings":[]}}')) == {}


def test_top_cut_size_reads_object_or_number():
    assert ExplorerService.top_cut_size({"topcut": {"id": "x", "format": "Constructed", "size": 8}}) == 8
    assert ExplorerService.top_cut_size({"topcut": 4}) == 4
    assert ExplorerService.top_cut_size({"topcut": None}) == 0
    assert ExplorerService.top_cut_size({"topcut": None}, default=8) == 8
    assert ExplorerService.top_cut_size({"topcut": {"size": None}}, default=8) == 8


# ── Explorer standings import ─────────────────────────────────────────────


def test_official_order_overrides_swiss_points_ties():
    # B and C tie on Swiss points; the page ranks C ahead on tiebreakers.
    players = [_player("a", "A", 3), _player("b", "B", 2), _player("c", "C", 2)]
    event = {"players": players, "phases": [], "topcut": None}
    svc = ExplorerService()
    svc._fetch_event_trpc = lambda _id: event
    svc._fetch_page_html = lambda _url: _page("A", "C", "B")

    data = svc.fetch_event_data("https://sorcerytcg.com/events/abc123")

    assert [(r["final_standing"], r["display_name"]) for r in data["results"]] == [(1, "A"), (2, "C"), (3, "B")]
    assert data["standings_source"] == "official"
    assert data["unmatched_players"] == []


def test_duplicate_display_names_resolve_by_registration():
    # Grand Contest Italy: two "Luca M"s finished 2nd and 10th. The rendered
    # list can only map the name once, so the embedded payload must win.
    players = [
        _player("u-corr", "Luca M", 5, reg_id="reg-corruptor"),
        _player("u-val", "Valerio G", 7, reg_id="reg-valerio"),
        _player("u-batt", "Luca M", 7, reg_id="reg-battlemage"),
        _player("u-eric", "Eric D", 6, reg_id="reg-eric"),
    ]
    event = {"players": players, "phases": [], "topcut": {"size": 2}}
    page = _page("Valerio G", "Luca M", "Eric D", "Luca M") + _rsc_page(_standings_payload(
        ("reg-valerio", "Pathfinder"),
        ("reg-battlemage", "Battlemage"),
        ("reg-eric", "Geomancer"),
        ("reg-corruptor", "Corruptor"),
    ))
    svc = ExplorerService()
    svc._fetch_event_trpc = lambda _id: event
    svc._fetch_page_html = lambda _url: page

    data = svc.fetch_event_data("https://sorcerytcg.com/events/abc123")

    assert [(r["final_standing"], r["cardeio_user_id"]) for r in data["results"]] == [
        (1, "u-val"), (2, "u-batt"), (3, "u-eric"), (4, "u-corr"),
    ]
    assert data["standings_source"] == "official"
    assert data["top_cut_size"] == 2


def test_flags_estimated_order_when_scrape_fails():
    event = {"players": [_player("a", "A", 1), _player("b", "B", 2)], "phases": [], "topcut": None}
    svc = ExplorerService()
    svc._fetch_event_trpc = lambda _id: event
    svc._fetch_page_html = lambda _url: ""

    data = svc.fetch_event_data("https://sorcerytcg.com/events/abc123")

    assert [r["display_name"] for r in data["results"]] == ["B", "A"]
    assert data["standings_source"] == "estimated"
    assert set(data["unmatched_players"]) == {"A", "B"}
    assert "_official_rank" not in data["results"][0]


# ── Top 8 deck import ─────────────────────────────────────────────────────


def _snapshots(event_id, players):
    return [{"sourceDeck": {"id": f"deck-{p['id']}"}} for p in players]


def test_deck_import_orders_duplicate_names_by_registration():
    players = [
        _player("u-corr", "Luca M", 5, reg_id="reg-corruptor"),
        _player("u-val", "Valerio G", 7, reg_id="reg-valerio"),
        _player("u-batt", "Luca M", 7, reg_id="reg-battlemage"),
        _player("u-chris", "Christian S", 5, reg_id="reg-christian"),
    ]
    event = {
        "title": "GRAND CONTEST - ITALY",
        "startsAt": "2026-09-26T09:00:00.000Z",
        "topcut": {"id": "tc", "format": "Constructed", "size": 3},
        "players": players,
    }
    page = _page("Valerio G", "Luca M", "Christian S", "Luca M") + _rsc_page(_standings_payload(
        ("reg-valerio", "Pathfinder"),
        ("reg-battlemage", "Battlemage"),
        ("reg-christian", "Necromancer"),
        ("reg-corruptor", "Corruptor"),
    ))
    svc = CuriosaService()
    svc._fetch_event_trpc = lambda _id: event
    svc._fetch_page_html = lambda _url: page
    svc._fetch_player_snapshots_batch = _snapshots

    discovery = svc.fetch_event_deck_ids("https://sorcerytcg.com/events/abc123")

    assert discovery["top_cut_size"] == 3
    assert [(p["standing"], p["deck_id"]) for p in discovery["players"]] == [
        (1, "deck-reg-valerio"),
        (2, "deck-reg-battlemage"),
        (3, "deck-reg-christian"),
        (4, "deck-reg-corruptor"),
    ]
    # The Corruptor "Luca M" must not inherit the Battlemage's standing.
    assert discovery["errors"] == []


def test_deck_import_falls_back_to_name_order_without_payload():
    players = [_player("a", "A", 1, reg_id="ra"), _player("b", "B", 2, reg_id="rb")]
    event = {"title": "Local", "startsAt": None, "topcut": None, "players": players}
    svc = CuriosaService()
    svc._fetch_event_trpc = lambda _id: event
    svc._fetch_page_html = lambda _url: _page("A", "B")
    svc._fetch_player_snapshots_batch = _snapshots

    discovery = svc.fetch_event_deck_ids("https://sorcerytcg.com/events/abc123")

    assert discovery["top_cut_size"] == 8
    assert [(p["standing"], p["name"]) for p in discovery["players"]] == [(1, "A"), (2, "B")]
