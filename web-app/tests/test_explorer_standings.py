"""Explorer event import: official standings order must drive final_standing."""

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


def _player(uid, name, swiss_wins):
    seats = [
        {"round": {"phase": {"structure": "Swiss"}}, "result": {"result": "Win", "score": 3}}
        for _ in range(swiss_wins)
    ]
    return {"status": "Ready", "user": {"id": uid, "displayname": name}, "seats": seats}


def test_parses_current_page_markup():
    standings = ExplorerService._parse_page_standings(_page("Kevin F", "Tom &amp; Jerry", "Niraj A"))
    assert standings == {"Kevin F": 1, "Tom & Jerry": 2, "Niraj A": 3}


def test_parses_legacy_page_markup():
    legacy = (
        '<span class="w-4 text-center font-title text-lg">1</span>'
        '<span class="truncate font-title">Kevin F</span>'
    )
    assert ExplorerService._parse_page_standings(legacy) == {"Kevin F": 1}


def test_official_order_overrides_swiss_points_ties():
    # B and C tie on Swiss points; the page ranks C ahead on tiebreakers.
    players = [_player("a", "A", 3), _player("b", "B", 2), _player("c", "C", 2)]
    event = {"players": players, "phases": [], "topcut": None}
    svc = ExplorerService()
    svc._fetch_event_trpc = lambda _id: event
    svc._fetch_page_standings = lambda _url: ExplorerService._parse_page_standings(_page("A", "C", "B"))

    data = svc.fetch_event_data("https://sorcerytcg.com/events/abc123")

    assert [(r["final_standing"], r["display_name"]) for r in data["results"]] == [(1, "A"), (2, "C"), (3, "B")]
    assert data["standings_source"] == "official"
    assert data["unmatched_players"] == []


def test_flags_estimated_order_when_scrape_fails():
    event = {"players": [_player("a", "A", 1), _player("b", "B", 2)], "phases": [], "topcut": None}
    svc = ExplorerService()
    svc._fetch_event_trpc = lambda _id: event
    svc._fetch_page_standings = lambda _url: {}

    data = svc.fetch_event_data("https://sorcerytcg.com/events/abc123")

    assert [r["display_name"] for r in data["results"]] == ["B", "A"]
    assert data["standings_source"] == "estimated"
    assert set(data["unmatched_players"]) == {"A", "B"}
    assert "_official_rank" not in data["results"][0]
