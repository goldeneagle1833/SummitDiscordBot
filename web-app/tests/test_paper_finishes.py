"""Tests for paper tournament finishes: Top 8 results matched to Summit profiles."""

import json
import sqlite3

import pytest


def _event(root, folder, decks, history=None):
    path = root / folder
    path.mkdir(parents=True)
    with open(path / f"{folder}top8.json", "w", encoding="utf-8") as f:
        json.dump(decks, f)
    if history:
        with open(path / "_match_history.json", "w", encoding="utf-8") as f:
            json.dump({"players": history}, f)


def _deck(deck_id, owner, avatar="Druid"):
    return {"id": deck_id, "name": f"{owner} deck", "username": owner, "avatar": [{"name": avatar}]}


def _player(elo_db, user_id, name):
    conn = sqlite3.connect(str(elo_db))
    conn.execute(
        "INSERT INTO overall_standings (user_id, user_display_name) VALUES (?, ?)", (user_id, name)
    )
    conn.commit()
    conn.close()


@pytest.fixture()
def setup(client, elo_db, match_db, tmp_path, monkeypatch):
    """Event files in a temp folder; the link tables in the test match DB."""
    import repositories.events
    import repositories.paper_links
    from services import paper_finishes

    root = tmp_path / "events"
    root.mkdir()
    monkeypatch.setattr(repositories.events, "TOP_8_DIR", root)
    monkeypatch.setattr(repositories.paper_links, "MATCH_RECORDS_DB_PATH", match_db)
    paper_finishes.reset_cache()
    yield root
    paper_finishes.reset_cache()


def test_labels():
    from services.paper_finishes import finish_label, name_key

    assert [finish_label(p) for p in (1, 2, 3, 4, 5, 8, 9, 17, 40)] == [
        "Winner", "Finalist", "Top 4", "Top 4", "Top 8", "Top 8", "Top 16", "Top 32", "Top 64",
    ]
    assert name_key(" Peter The-Great ") == "peterthegreat"
    assert name_key("Fünfrappe") == "funfrappe"


def test_exact_name_earns_badge_and_rules(setup, elo_db):
    from services.paper_finishes import get_finishes_by_player

    _player(elo_db, "1", "Peter The Great")
    _player(elo_db, "2", "Duo")  # too short to link on its own
    _player(elo_db, "3", "Sam Smith")
    _player(elo_db, "4", "sam_smith")  # two players share this name
    _event(setup, "SCG Con Atlanta 2026", [
        _deck("d1", "PeterTheGreat"),
        _deck("d2", "Duo"),
        _deck("d3", "samsmith"),
        _deck("d4", "Nobody Here"),
    ])
    finishes = get_finishes_by_player()
    assert list(finishes) == ["1"]
    assert finishes["1"][0]["label"] == "Winner"
    assert finishes["1"][0]["title"].lower() == "winner · scg con atlanta"


def test_registered_name_beats_deck_owner_and_shared_uploader_skipped(setup, elo_db):
    from services.paper_finishes import admin_review, get_finishes_by_player

    _player(elo_db, "1", "Geoffrey")
    _player(elo_db, "2", "luix")
    _event(setup, "EU Crossroads 2025", [_deck("a", "luix"), _deck("b", "luix")])
    _event(setup, "Cold Foil 2026", [_deck("c", "someoneelse"), _deck("d", "x2")],
           history=[{"deck_id": "c", "display_name": "Geoffrey", "username": "geoff"}])
    finishes = get_finishes_by_player()
    assert "2" not in finishes  # luix posted both decks, so is not the pilot
    assert finishes["1"][0]["event"].startswith("Cold Foil")
    statuses = {(r["folder"], r["place"]): r["status"] for r in admin_review()["results"]}
    assert statuses[("EU Crossroads 2025", 1)] == "shared_uploader"


def test_admin_calls(setup, elo_db):
    from repositories.paper_links import PaperLinkRepository
    from services.paper_finishes import get_finishes_by_player, name_key, reset_cache

    _player(elo_db, "1", "Ringslayer")
    _player(elo_db, "2", "Bruce")
    _event(setup, "SCG Con Portland 2026", [_deck("p1", "grish"), _deck("p2", "RingSlayer")])
    assert [f["label"] for f in get_finishes_by_player()["1"]] == ["Finalist"]

    repo = PaperLinkRepository()
    repo.reject_name(name_key("RingSlayer"), "RingSlayer", "1")
    repo.link_name(name_key("grish"), "grish", "2")
    reset_cache()
    finishes = get_finishes_by_player()
    assert "1" not in finishes
    assert finishes["2"][0]["label"] == "Winner"

    repo.assign_result("SCG Con Portland 2026", "p1", "")  # nobody
    repo.set_event_awards("SCG Con Portland 2026", True)
    reset_cache()
    assert get_finishes_by_player() == {}


def test_repeat_pages_and_online_events(setup, elo_db):
    from repositories.paper_links import PaperLinkRepository
    from services.paper_finishes import get_finishes_by_player, reset_cache

    _player(elo_db, "1", "Avaloneer")
    _event(setup, "Sorcery Con Constructed 2026", [_deck("w", "Avaloneer")])
    _event(setup, "Top 32 Sorcery Con Constructed 2026", [_deck("w", "Avaloneer")] + [_deck(f"x{i}", f"p{i}") for i in range(31)])
    _event(setup, "Summit Gothic Season 3 2026", [_deck("s", "Avaloneer")])
    finishes = get_finishes_by_player()["1"]
    assert len(finishes) == 1  # same deck, counted once; Summit seasons start off
    assert finishes[0]["folder"] == "Sorcery Con Constructed 2026"

    PaperLinkRepository().set_event_awards("Summit Gothic Season 3 2026", True)
    reset_cache()
    assert len(get_finishes_by_player()["1"]) == 2


def test_public_and_admin_routes(setup, elo_db, client):
    _player(elo_db, "1", "Avaloneer")
    _event(setup, "LinCon May 14-16 2026", [_deck("w", "Avaloneer")])
    data = client.get("/api/paper-finishes").get_json()
    assert data["finishes"]["1"][0]["label"] == "Winner"
    assert client.get("/api/admin/paper-finishes").status_code in (200, 403)


def test_event_profiles_route(setup, elo_db, client):
    from repositories.paper_links import PaperLinkRepository
    from services.paper_finishes import reset_cache

    _player(elo_db, "1", "Avaloneer")
    _player(elo_db, "2", "Bruce")
    _event(setup, "LinCon May 14-16 2026", [_deck("w", "Avaloneer"), _deck("f", "Stranger")])
    entries = client.get("/api/paper-finishes/event/LinCon May 14-16 2026").get_json()["entries"]
    assert entries[0]["player"] == {"user_id": "1", "name": "Avaloneer"}
    assert entries[1]["player"] is None and entries[1]["status"] == "unmatched"

    PaperLinkRepository().assign_result("LinCon May 14-16 2026", "f", "2")
    reset_cache()
    entries = client.get("/api/paper-finishes/event/LinCon May 14-16 2026").get_json()["entries"]
    assert entries[1]["player"]["user_id"] == "2" and entries[1]["status"] == "assigned"
    assert client.get("/api/paper-finishes/event/Nope").get_json()["entries"] == []


def test_manual_results(setup, elo_db, admin_session):
    client = admin_session
    _player(elo_db, "1", "Avaloneer")
    _event(setup, "LinCon May 14-16 2026", [_deck("x", "Someone"), _deck("w", "Avaloneer")])

    # Missing player or event, bad placement or date are refused.
    assert client.post("/api/admin/paper-finishes/manual", json={"event": "Store night"}).status_code == 400
    assert client.post("/api/admin/paper-finishes/manual", json={"user_id": "1", "event": "X", "place": 3}).status_code == 400
    assert client.post("/api/admin/paper-finishes/manual",
                       json={"user_id": "1", "event": "X", "event_date": "soon"}).status_code == 400

    # Placement defaults to Winner.
    res = client.post("/api/admin/paper-finishes/manual",
                      json={"user_id": "google_1", "event": "Store Champs", "event_date": "2026-10-04", "avatar": "Druid"})
    assert res.status_code == 200
    manual_id = res.get_json()["id"]

    finishes = client.get("/api/paper-finishes").get_json()["finishes"]["1"]
    assert [f["label"] for f in finishes] == ["Winner", "Finalist"]
    assert finishes[0]["manual"] is True and finishes[0]["event"] == "Store Champs"
    assert finishes[0]["event_date_display"] == "Oct 4, 2026" and finishes[0]["avatar"] == "Druid"
    assert finishes[1]["folder"] == "LinCon May 14-16 2026"

    review = client.get("/api/admin/paper-finishes").get_json()
    assert review["manual"][0]["player"]["user_id"] == "1" and review["manual"][0]["label"] == "Winner"

    res = client.put(f"/api/admin/paper-finishes/manual/{manual_id}",
                     json={"user_id": "1", "event": "Store Champs", "event_date": "2026-10-04", "place": 8})
    assert res.status_code == 200
    finishes = client.get("/api/paper-finishes").get_json()["finishes"]["1"]
    assert [f["label"] for f in finishes] == ["Finalist", "Top 8"]

    assert client.delete(f"/api/admin/paper-finishes/manual/{manual_id}").status_code == 200
    assert client.delete(f"/api/admin/paper-finishes/manual/{manual_id}").status_code == 404
    finishes = client.get("/api/paper-finishes").get_json()["finishes"]["1"]
    assert [f["label"] for f in finishes] == ["Finalist"]


# -- badges-only events from sorcerytcg.com ---------------------------------

def _seat(result):
    return {"round": {"number": 1, "phase": {"structure": "Swiss"}}, "result": {"result": result, "score": 3 if result == "Win" else 0}}


def _sorcery_player(reg_id, name, username, wins):
    return {
        "id": reg_id,
        "status": "Ready",
        "user": {"displayname": name, "username": username},
        "seats": [_seat("Win") for _ in range(wins)] + [_seat("Loss")],
    }


@pytest.fixture()
def sorcery_event(monkeypatch):
    """A deck-less sorcerytcg.com event: no snapshots may be fetched."""
    from services.curiosa import CuriosaService

    event = {
        "title": "Store Champs Columbus",
        "startsAt": "2026-10-25T14:00:00Z",
        "topcut": {"size": 4},
        "players": [
            _sorcery_player("r1", "Avaloneer", "avaloneer", 4),
            _sorcery_player("r2", "Kevin F", "kevinf", 3),
            _sorcery_player("r3", "Peter The Great", "ptg", 2),
            _sorcery_player("r4", "Someone Else", "someone", 1),
            _sorcery_player("r5", "Fifth Place", "fifth", 0),
        ],
    }

    def no_snapshots(*_a, **_k):
        raise AssertionError("a badges-only import must not fetch deck snapshots")

    monkeypatch.setattr(CuriosaService, "_fetch_event_trpc", lambda self, _id: event)
    monkeypatch.setattr(CuriosaService, "_fetch_page_html", staticmethod(lambda _url: ""))
    monkeypatch.setattr(CuriosaService, "_fetch_player_snapshots_batch", no_snapshots)
    return event


URL = "https://sorcerytcg.com/events/cmtstorechamps01"


def test_fetch_standings_without_decks(sorcery_event):
    from services.curiosa import CuriosaService

    data = CuriosaService().fetch_event_deck_ids(URL, with_decks=False)
    assert data["players"] == [] and data["errors"] == []
    assert data["top_cut_size"] == 4 and data["event_date"] == "2026-10-25"
    assert [p["display_name"] for p in data["match_history"]] == [
        "Avaloneer", "Kevin F", "Peter The Great", "Someone Else", "Fifth Place",
    ]


def test_badge_only_import_gives_badges_and_is_listed_nowhere(setup, elo_db, admin_session, sorcery_event):
    from repositories.events import EventRepository

    client = admin_session
    _player(elo_db, "1", "Avaloneer")
    _player(elo_db, "2", "Peter The Great")
    _player(elo_db, "5", "Fifth Place")  # outside the top 4: no badge

    assert client.post("/api/admin/paper-finishes/badge-only", json={"event_url": "https://example.com/x"}).status_code == 400
    res = client.post("/api/admin/paper-finishes/badge-only", json={"event_url": URL})
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["name"] == "Store Champs Columbus" and body["top_cut"] == 4 and body["players"] == 5

    finishes = client.get("/api/paper-finishes").get_json()["finishes"]
    assert sorted(finishes) == ["1", "2"]
    win = finishes["1"][0]
    assert win["label"] == "Winner" and win["event"] == "Store Champs Columbus"
    assert win["badge_only"] is True and win["event_url"] == URL
    assert win["event_date_display"] == "Oct 25, 2026"
    assert finishes["2"][0]["label"] == "Top 4"

    # Nothing that lists events sees it.
    assert EventRepository().get_all_events() == []
    assert list(setup.iterdir()) == []  # no folder on the Top 8 page
    listed = client.get("/api/top-8-events").get_json()
    assert "Store Champs" not in json.dumps(listed)

    review = client.get("/api/admin/paper-finishes").get_json()
    assert review["badge_only"][0]["top_cut_names"] == ["Avaloneer", "Kevin F", "Peter The Great", "Someone Else"]
    event_row = next(e for e in review["events"] if e["badge_only"])
    assert event_row["awards_badges"] is True
    kevin = next(r for r in review["results"] if r["names"][0] == "Kevin F")
    assert kevin["status"] == "unmatched" and kevin["deck_id"] == "r2"

    # Admin calls work on these results like any other.
    folder = event_row["folder"]
    assert client.post("/api/admin/paper-finishes/assign", json={"folder": folder, "deck_id": "r2", "user_id": "5"}).status_code == 200
    assert client.get("/api/paper-finishes").get_json()["finishes"]["5"][0]["label"] == "Finalist"

    # Edit: rename and widen the cut.
    eid = body["event_id"]
    assert client.put(f"/api/admin/paper-finishes/badge-only/{eid}", json={"name": "Columbus Store Champs", "top_cut": 3}).status_code == 400
    assert client.put(f"/api/admin/paper-finishes/badge-only/{eid}",
                      json={"name": "Columbus Store Champs", "event_date": "2026-10-25", "top_cut": 8}).status_code == 200
    finishes = client.get("/api/paper-finishes").get_json()["finishes"]
    assert finishes["5"][0]["event"] == "Columbus Store Champs"
    assert sorted(finishes) == ["1", "2", "5"]

    # Re-sync keeps the admin's name and cut.
    res = client.post("/api/admin/paper-finishes/badge-only", json={"event_url": URL})
    assert res.get_json()["updated"] is True and res.get_json()["name"] == "Columbus Store Champs"
    assert res.get_json()["top_cut"] == 8

    # Remove takes the badges (and the admin call on it) away.
    assert client.delete(f"/api/admin/paper-finishes/badge-only/{eid}").status_code == 200
    assert client.delete(f"/api/admin/paper-finishes/badge-only/{eid}").status_code == 404
    assert client.get("/api/paper-finishes").get_json()["finishes"] == {}


def test_badge_only_refuses_event_already_on_top8(setup, elo_db, admin_session, sorcery_event):
    path = setup / "Store Champs Columbus"
    path.mkdir()
    (path / "Store Champs Columbustop8.json").write_text(json.dumps([_deck("d1", "Avaloneer")]))
    (path / "_match_history.json").write_text(json.dumps({"event_id": "cmtstorechamps01", "players": []}))
    res = admin_session.post("/api/admin/paper-finishes/badge-only", json={"event_url": URL})
    assert res.status_code == 409
    assert "Top 8 page" in res.get_json()["error"]
