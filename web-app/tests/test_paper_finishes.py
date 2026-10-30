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
