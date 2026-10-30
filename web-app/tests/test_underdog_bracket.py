"""Tests for the underdog bracket: best player on each of a season's weakest avatars."""

import json
import sqlite3

import pytest

import webapp_config
from repositories.brackets import BracketRepository
from services.brackets import BracketError, BracketService
from services.underdog_bracket import underdog_field

ENDED = 8


@pytest.fixture()
def dbs(tmp_path, monkeypatch):
    elo_db = tmp_path / "elo.db"
    match_db = tmp_path / "match_records.db"
    monkeypatch.setattr(webapp_config, "ELO_DB_PATH", elo_db)
    monkeypatch.setattr(webapp_config, "MATCH_RECORDS_DB_PATH", match_db)

    conn = sqlite3.connect(str(elo_db))
    conn.execute(
        "CREATE TABLE events (event_id INTEGER PRIMARY KEY, event_name TEXT, start_date TEXT,"
        " end_date TEXT, is_active INTEGER)"
    )
    conn.execute("INSERT INTO events VALUES (7, 'Season 7', '2026-06-01', '2026-08-01', 0)")
    conn.execute("INSERT INTO events VALUES (8, 'Season 8', '2026-08-01', '2026-10-28', 0)")
    conn.commit()
    conn.close()

    conn = sqlite3.connect(str(match_db))
    for table in ("match_records", "match_records_archive"):
        conn.execute(
            f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, winner_id TEXT, winner_display_name TEXT,"
            " losser_id TEXT, losser_display_name TEXT, json_deck_data_winner TEXT,"
            " json_deck_data_loser TEXT, source TEXT, event_id INTEGER, timestamp TEXT)"
        )
    conn.commit()
    conn.close()
    return elo_db, match_db


def deck(avatar):
    return json.dumps({"avatar": [{"name": avatar}], "spellbook": []})


def games(match_db, player, avatar, wins, losses, event_id=ENDED, source="Discord",
          opponent="900", opponent_avatar="Sparkmage"):
    """``player`` on ``avatar`` goes wins-losses against a filler opponent."""
    conn = sqlite3.connect(str(match_db))
    rows = []
    for won in [True] * wins + [False] * losses:
        me = (player, f"Name{player}", deck(avatar))
        them = (opponent, f"Name{opponent}", deck(opponent_avatar))
        w, l = (me, them) if won else (them, me)
        rows.append((w[0], w[1], l[0], l[1], w[2], l[2], source, event_id))
    conn.executemany(
        "INSERT INTO match_records_archive (winner_id, winner_display_name, losser_id,"
        " losser_display_name, json_deck_data_winner, json_deck_data_loser, source, event_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


def build_season(match_db):
    """Ten weak avatars, one strong filler avatar (Sparkmage) everyone plays against."""
    # Weakest first: fewer games and worse records mean lower Avatar Scores.
    games(match_db, "1", "Lavamancer", 6, 8)
    games(match_db, "1", "Frostmage", 7, 7)   # player 1 is best on both
    games(match_db, "2", "Lavamancer", 5, 6)  # next best on Lavamancer
    games(match_db, "3", "Pathfinder", 2, 3)  # nobody has 10 games here
    for i, avatar in enumerate(
        ["Druid", "Witch", "Seer", "Geomancer", "Battlemage", "Avatar of Air", "Enchantress"], start=4
    ):
        games(match_db, str(i), avatar, 6 + i, 8 + i)


def test_field_is_eight_weakest_with_one_slot_per_player(dbs):
    _, match_db = dbs
    build_season(match_db)

    field = underdog_field(ENDED)

    assert field["event"]["event_name"] == "Season 8"
    picked = {p["avatar"]: p["user_id"] for p in field["players"]}
    assert len(picked) == 8
    # Player 1 keeps Frostmage, where their score is higher; player 2 gets Lavamancer.
    assert picked["Frostmage"] == "1"
    assert picked["Lavamancer"] == "2"
    assert len(set(picked.values())) == 8
    # No 10-game player on Pathfinder, so it is skipped; the strong filler avatar is out.
    assert "Pathfinder" not in picked
    assert "Sparkmage" not in picked
    notes = {a["avatar"]: a["note"] for a in field["avatars"]}
    assert notes["Pathfinder"] == "Nobody has 10 games"
    # Seeds go by the player's Avatar Score on their avatar.
    scores = [p["avatar_score"] for p in field["players"]]
    assert scores == sorted(scores, reverse=True)


def test_bracket_games_do_not_count(dbs):
    _, match_db = dbs
    build_season(match_db)
    # Lots of Bracket wins would lift Lavamancer far above the others.
    games(match_db, "1", "Lavamancer", 40, 0, source="Bracket")

    before = [a["avatar"] for a in underdog_field(ENDED)["avatars"]]
    assert before.index("Lavamancer") < before.index("Sparkmage")


def test_player_on_two_avatars_where_nobody_else_qualifies(dbs):
    _, match_db = dbs
    games(match_db, "1", "Lavamancer", 6, 8)
    games(match_db, "1", "Frostmage", 7, 7)

    field = underdog_field(ENDED)

    assert sorted(p["user_id"] for p in field["players"]) == ["1", "900"]
    dropped = next(a for a in field["avatars"] if a["avatar"] in ("Lavamancer", "Frostmage") and not a["player"])
    assert dropped["note"] == "Its players took other avatars"


def test_create_underdog_bracket(dbs):
    _, match_db = dbs
    build_season(match_db)
    BracketRepository().ensure_tables()
    service = BracketService()

    result = service.create_bracket("Season 8 Underdog Bracket", 8, source="underdog", event=ENDED)

    bracket = service._repo.get_bracket(slug=result["slug"])
    assert bracket["format"] == "underdog"
    assert bracket["seeded_from"] == "underdog"
    assert bracket["elo_event_name"] == "Season 8"
    assert result["entrant_count"] == 8
    assert "Lavamancer" in bracket["description"]
    assert service.finish_label(1, "underdog") == "Underdog Champion"


def test_underdog_bracket_stays_off_top8_page(dbs):
    _, match_db = dbs
    build_season(match_db)
    BracketRepository().ensure_tables()
    service = BracketService()
    result = service.create_bracket("Season 8 Underdog Bracket", 8, source="underdog", event=ENDED)
    bracket_id = service._repo.get_bracket(slug=result["slug"])["bracket_id"]
    service._repo.set_status(bracket_id, "complete")

    with pytest.raises(BracketError, match="Top 8 page"):
        service.publish_to_top8(bracket_id)



def test_underdog_finish_has_its_own_marks(dbs):
    _, match_db = dbs
    build_season(match_db)
    BracketRepository().ensure_tables()
    service = BracketService()
    service._elo_repo_override = type("Names", (), {"get_display_names": lambda self, ids: {}})()
    service._profile_repo_override = type("Names", (), {"get_custom_display_names": lambda self, ids: {}})()
    result = service.create_bracket("Season 8 Underdog Bracket", 8, source="underdog", event=ENDED)
    bracket_id = service._repo.get_bracket(slug=result["slug"])["bracket_id"]
    service._repo.set_status(bracket_id, "complete")
    service.placements = lambda _id: {1: 1, 2: 2}
    champion = service._repo.get_entrants(bracket_id)[0]["user_id"]

    marks = service.get_player_marks()[champion]

    assert marks["wins"] == 0 and marks["best"] is None
    assert marks["underdog_wins"] == 1
    assert marks["underdog_best_label"] == "Underdog Champion"
    assert marks["entries"][0]["label"] == "Underdog Champion"


def test_left_out_avatars_make_room_for_the_next_weakest(dbs):
    _, match_db = dbs
    build_season(match_db)
    BracketRepository().ensure_tables()

    field = underdog_field(ENDED, exclude=["frostmage", "Lavamancer"])

    picked = {p["avatar"] for p in field["players"]}
    assert not picked & {"Frostmage", "Lavamancer"}
    assert len(picked) == 8
    assert "Sparkmage" in picked  # the next weakest moved up
    notes = {a["avatar"]: a["note"] for a in field["avatars"]}
    assert notes["Frostmage"] == notes["Lavamancer"] == "Left out"

    service = BracketService()
    result = service.create_bracket(
        "Season 8 Underdog Bracket", 8, source="underdog", event=ENDED, exclude=["Frostmage", "Lavamancer"]
    )
    description = service._repo.get_bracket(slug=result["slug"])["description"]
    assert description.endswith("Left out: Frostmage, Lavamancer.")


def test_standings_endpoint_matches_the_admin_preview(dbs, monkeypatch):
    """The Discord card reads this: same pick as the admin preview, left-outs honoured."""
    from flask import Flask

    from routes.api.brackets import brackets_bp

    _, match_db = dbs
    build_season(match_db)
    BracketRepository().ensure_tables()
    app = Flask(__name__)
    app.register_blueprint(brackets_bp, url_prefix="/api")
    client = app.test_client()

    import utils.auth

    monkeypatch.setattr(utils.auth, "VALID_API_KEYS", ["bot-key"])
    url = f"/api/brackets/underdog-standings?event={ENDED}&exclude=Frostmage,Lavamancer"
    assert client.get(url).status_code == 401
    resp = client.get(url, headers={"X-API-Key": "bot-key"})
    assert resp.status_code == 200
    data = resp.get_json()
    preview = BracketService().get_seed_pool("underdog", ENDED, ["Frostmage", "Lavamancer"])
    assert data["players"] == preview["players"]
    assert data["avatars"] == preview["avatars"]
    assert data["event"]["event_id"] == ENDED
    assert not {p["avatar"] for p in data["players"]} & {"Frostmage", "Lavamancer"}
