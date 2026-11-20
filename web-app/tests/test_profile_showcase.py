"""Profile showcase: the player's short bio, favorite card and rival."""

import sqlite3

import pytest

import routes.api.players as players_routes


@pytest.fixture
def profile(match_db):
    conn = sqlite3.connect(str(match_db))
    conn.execute(
        "INSERT INTO user_profiles (user_id, provider, display_name, first_login_at, last_login_at)"
        " VALUES ('100', 'discord', 'A', 'now', 'now')"
    )
    conn.commit()
    conn.close()


@pytest.fixture(autouse=True)
def cards(monkeypatch):
    from repositories.card_catalog import CardCatalogRepository
    monkeypatch.setattr(CardCatalogRepository, "get_all_card_names", lambda self: ["Pudge Butcher", "No Art"])
    monkeypatch.setattr(
        players_routes, "resolve_card_image",
        lambda name: "bet-pudge_butcher-b-s.png" if name == "Pudge Butcher" else None,
    )


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


EMPTY = {"bio": None, "favorite_card": None, "rival": None}


def test_nothing_shows_until_the_player_fills_it_in(client, profile):
    assert client.get("/api/player/100/showcase").get_json() == EMPTY


def test_owner_fills_every_box_and_visitors_see_them(client, profile):
    _login(client, "100")
    resp = client.put("/api/player/100/showcase", json={
        "bio": "  Ohio  Earth player.\nLoves big golems. ",
        "favorite_card": "pudge butcher",
    })
    assert resp.status_code == 200
    _login(client, "200")
    assert client.get("/api/player/100/showcase").get_json() == {
        "bio": "Ohio Earth player. Loves big golems.",
        "favorite_card": {"name": "Pudge Butcher", "image": "bet-pudge_butcher-b-s.png"},
        "rival": None,
    }


def test_fields_change_one_at_a_time_and_empty_clears(client, profile):
    _login(client, "100")
    client.put("/api/player/100/showcase", json={"bio": "Hi", "favorite_card": "Pudge Butcher"})
    client.put("/api/player/100/showcase", json={"bio": ""})
    body = client.get("/api/player/100/showcase").get_json()
    assert body["bio"] is None
    assert body["favorite_card"]["name"] == "Pudge Butcher"
    client.put("/api/player/100/showcase", json={"favorite_card": None})
    assert client.get("/api/player/100/showcase").get_json() == EMPTY


@pytest.mark.parametrize("body", [
    {"bio": "x" * 161},
    {"bio": "Join my server discord.gg/abc"},
    {"bio": "see https://example.com"},
    {"bio": "visit mysite.com"},
    {"rival": "999"},
    {"rival": "100"},
    {"favorite_card": "Not A Card"},
    {"favorite_card": "No Art"},
])
def test_rejects_long_text_links_and_unknown_cards(client, profile, body):
    _login(client, "100")
    assert client.put("/api/player/100/showcase", json=body).status_code == 400
    assert client.get("/api/player/100/showcase").get_json() == EMPTY


def test_only_the_owner_or_an_admin_can_change_it(client, profile):
    assert client.put("/api/player/100/showcase", json={"bio": "x"}).status_code == 401
    _login(client, "200")
    assert client.put("/api/player/100/showcase", json={"bio": "x"}).status_code == 403


def _game(match_db, winner, loser, ts, winner_name=None, loser_name=None):
    # The real match_records layout (winner_id / losser_id), not a made-up one
    conn = sqlite3.connect(str(match_db))
    conn.execute(
        "INSERT INTO match_records (match_id, winner_id, winner_display_name, losser_id,"
        " losser_display_name, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (f"{winner}-{loser}-{ts}", winner, winner_name or f"P{winner}", loser, loser_name or f"P{loser}", ts),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def played(match_db, profile):
    _game(match_db, "100", "300", "2026-11-01")
    _game(match_db, "300", "100", "2026-11-02")
    _game(match_db, "100", "300", "2026-11-03", loser_name="Rivalry Rob")
    _game(match_db, "400", "100", "2026-11-04")


def test_rival_options_are_people_they_played_most_first(client, played):
    _login(client, "100")
    players = client.get("/api/player/100/rival-options").get_json()["players"]
    assert [(p["id"], p["name"], p["wins"], p["losses"]) for p in players] == [
        ("300", "Rivalry Rob", 2, 1),
        ("400", "P400", 0, 1),
    ]
    _login(client, "200")
    assert client.get("/api/player/100/rival-options").status_code == 403


def test_rival_shows_head_to_head_record_to_visitors(client, played):
    _login(client, "100")
    assert client.put("/api/player/100/showcase", json={"rival": "300"}).status_code == 200
    _login(client, "200")
    rival = client.get("/api/player/100/showcase").get_json()["rival"]
    assert rival == {"id": "300", "name": "Rivalry Rob", "avatar_url": None, "wins": 2, "losses": 1}


def test_rival_who_blocked_the_player_is_hidden(client, played):
    from repositories.blocked_users_repo import BlockedUsersRepository
    _login(client, "100")
    client.put("/api/player/100/showcase", json={"rival": "300"})
    BlockedUsersRepository().block_user("300", "100")
    assert client.get("/api/player/100/showcase").get_json()["rival"] is None


def test_admin_edit_is_audit_logged(client, played, monkeypatch):
    monkeypatch.setattr(players_routes, "is_admin", lambda: True)
    _login(client, "999")
    assert client.put("/api/player/100/showcase", json={"bio": ""}).status_code == 200
    from repositories.audit import AuditRepository
    assert AuditRepository().get_logs()[0]["action"] == "edit_profile_showcase"
