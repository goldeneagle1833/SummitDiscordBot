"""Tests for the Deck Archetypes grouping (services/deck_archetypes.py) and its API."""

import json
import sqlite3

import pytest

from repositories.archetype_decks import ArchetypeDeckRepository
from services import deck_archetypes


def card(name, qty=1, elements="Fire"):
    return {"name": name, "quantity": qty, "elements": elements}


def deck(deck_id, avatar, cards, name=None, user="player", elements="Fire"):
    return {
        "id": deck_id,
        "name": name or deck_id,
        "username": user,
        "avatar": [{"name": avatar}],
        "spellbook": [card(c, 2, elements) for c in cards],
        "atlas": [card("Common Site", 4, "None")],
        "sideboard": [],
    }


FIRE = [f"Fire card {i}" for i in range(20)]
WATER = [f"Water card {i}" for i in range(20)]


def fire_deck(deck_id, swap=0, **kw):
    cards = FIRE[: 20 - swap] + [f"{deck_id} tech {i}" for i in range(swap)]
    return deck(deck_id, "Sorcerer", cards, **kw)


def water_deck(deck_id, **kw):
    return deck(deck_id, "Sorcerer", WATER, elements="Water", **kw)


def write_event(top8_dir, folder, top8=None, full=None):
    path = top8_dir / folder
    path.mkdir(parents=True)
    if top8 is not None:
        (path / f"{folder}top8.json").write_text(json.dumps(top8))
    if full is not None:
        (path / f"{folder}.json").write_text(json.dumps(full))


def make_match_db(path, rows):
    conn = sqlite3.connect(path)
    cols = ("json_deck_data_winner, json_deck_data_loser, curiosa_url_winner, curiosa_url_loser, "
            "winner_display_name, losser_display_name, match_type")
    conn.execute(f"CREATE TABLE match_records ({cols})")
    conn.execute(f"CREATE TABLE match_records_archive ({cols})")
    for winner, loser, match_type in rows:
        conn.execute(
            "INSERT INTO match_records VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                json.dumps(winner), json.dumps(loser),
                f"https://sorcerytcg.com/decks/{winner['id']}", f"https://sorcerytcg.com/decks/{loser['id']}",
                "Winner", "Loser", match_type,
            ),
        )
    conn.commit()
    conn.close()


@pytest.fixture()
def repo(tmp_path):
    top8_dir = tmp_path / "events"
    top8_dir.mkdir()
    return ArchetypeDeckRepository(
        top8_dir=top8_dir,
        db_path=tmp_path / "match_records.db",
        seed_events_path=tmp_path / "seed.json",
        seed_cache_path=tmp_path / "seed.cache.json",
    )


def groups_by_member(snapshot):
    out = {}
    for group in snapshot["groups"]:
        for deck_id in snapshot["details"][group["id"]]["members"]:
            out[deck_id] = group
    return out


def test_similar_decks_group_and_different_decks_do_not(repo):
    write_event(repo._top8_dir, "Cup", top8=[fire_deck("f1"), fire_deck("f2", swap=2), water_deck("w1")])

    snapshot = deck_archetypes.build_snapshots(repo)["tournament"]
    member = groups_by_member(snapshot)

    assert member["f1"]["id"] == member["f2"]["id"]
    assert member["w1"]["id"] != member["f1"]["id"]


def test_decks_with_different_avatars_never_group(repo):
    other = fire_deck("f2")
    other["avatar"] = [{"name": "Druid"}]
    write_event(repo._top8_dir, "Cup", top8=[fire_deck("f1"), other])

    member = groups_by_member(deck_archetypes.build_snapshots(repo)["tournament"])

    assert member["f1"]["id"] != member["f2"]["id"]


def test_placements_count_wins_and_top8(repo):
    field = [fire_deck(f"f{i}", swap=1) for i in range(10)]
    write_event(repo._top8_dir, "Cup", top8=field)

    group = groups_by_member(deck_archetypes.build_snapshots(repo)["tournament"])["f0"]

    assert group["size"] == 10
    assert group["wins"] == 1
    assert group["top8"] == 8
    assert group["topCut"] == 10
    assert group["events"] == 1


def test_ranked_record_merges_into_tournament_deck_and_casual_is_ignored(repo):
    f1, w1 = fire_deck("f1"), water_deck("w1")
    write_event(repo._top8_dir, "Cup", top8=[f1])
    make_match_db(repo._db_path, [
        (f1, w1, "ranked"),
        (f1, w1, "ranked"),
        (w1, f1, None),
        (w1, f1, "casual"),
    ])

    snapshots = deck_archetypes.build_snapshots(repo)
    group = groups_by_member(snapshots["all"])["f1"]
    detail = snapshots["all"]["details"][group["id"]]

    assert detail["decks"]["f1"]["ranked"]["wins"] == 2
    assert detail["decks"]["f1"]["ranked"]["losses"] == 1
    assert detail["decks"]["f1"]["entries"][0]["placement"] == 1
    assert snapshots["all"]["meta"]["rankedGames"] == 3


def test_tournament_source_leaves_out_ranked_only_decks(repo):
    write_event(repo._top8_dir, "Cup", top8=[fire_deck("f1")])
    make_match_db(repo._db_path, [(water_deck("w1"), water_deck("w2"), "ranked")])

    snapshots = deck_archetypes.build_snapshots(repo)

    assert set(groups_by_member(snapshots["tournament"])) == {"f1"}
    assert {"w1", "w2"} <= set(groups_by_member(snapshots["all"]))


def test_one_off_ranked_decks_are_dropped_from_all(repo):
    lonely = deck("x1", "Druid", [f"Odd card {i}" for i in range(20)])
    make_match_db(repo._db_path, [(lonely, water_deck("w1"), "ranked")])

    member = groups_by_member(deck_archetypes.build_snapshots(repo)["all"])

    assert "x1" not in member
    assert "w1" not in member


def test_seed_decks_wait_for_their_card_lists(repo):
    repo._seed_events_path.write_text(json.dumps({"decks": [
        {"id": "s1", "name": "Seed", "avatar": "Sorcerer",
         "entries": [{"event": "Grand Contest", "date": "2026-01-01", "player": "p", "placement": 1, "top8": True, "topCut": True}]},
        {"id": "s2", "name": "Gone", "avatar": "Sorcerer", "entries": []},
        {"id": "s3", "name": "Later", "avatar": "Sorcerer", "entries": []},
    ]}))
    repo.save_seed_cache_entry("s1", fire_deck("s1"))
    repo.save_seed_cache_entry("s2", {"unavailable": True})

    snapshot = deck_archetypes.build_snapshots(repo)["tournament"]
    group = groups_by_member(snapshot)["s1"]

    assert snapshot["meta"]["pendingDecks"] == 1
    assert snapshot["meta"]["unavailableDecks"] == 1
    assert snapshot["meta"]["tournamentCount"] == 1
    assert group["wins"] == 1
    assert snapshot["details"][group["id"]]["decks"]["s1"]["name"] == "Seed"


def test_cluster_stops_at_threshold():
    import numpy as np

    sim = np.array([
        [1.0, 0.9, 0.1],
        [0.9, 1.0, 0.1],
        [0.1, 0.1, 1.0],
    ], dtype=np.float32)

    groups = sorted(sorted(g) for g in deck_archetypes.cluster(sim, 0.5))

    assert groups == [[0, 1], [2]]


class TestApi:
    SNAPSHOT = {
        "meta": {"source": "all"},
        "groups": [{"id": "g1", "name": "Sorcerer · Fire"}],
        "details": {"g1": {"patterns": {}, "recommendations": [], "members": [], "decks": {}}},
    }

    def test_building_returns_202(self, client, monkeypatch):
        monkeypatch.setattr(deck_archetypes, "get_snapshot", lambda source: None)
        res = client.get("/api/deck-archetypes")
        assert res.status_code == 202
        assert res.get_json()["status"] == "building"

    def test_list_and_detail(self, client, monkeypatch):
        seen = []

        def fake(source):
            seen.append(source)
            return self.SNAPSHOT

        monkeypatch.setattr(deck_archetypes, "get_snapshot", fake)
        listing = client.get("/api/deck-archetypes?source=tournament").get_json()
        detail = client.get("/api/deck-archetypes/g1?source=bogus")
        missing = client.get("/api/deck-archetypes/nope")

        assert listing["groups"][0]["id"] == "g1"
        assert detail.status_code == 200
        assert missing.status_code == 404
        assert seen == ["tournament", "all", "all"]


def test_decks_with_different_elements_never_group(repo):
    # Same cards, but one deck's element pair differs.
    write_event(repo._top8_dir, "Cup", top8=[fire_deck("f1"), deck("f2", "Sorcerer", FIRE, elements="Air")])

    member = groups_by_member(deck_archetypes.build_snapshots(repo)["tournament"])

    assert member["f1"]["id"] != member["f2"]["id"]
    assert member["f2"]["name"] == "Sorcerer · Air"
