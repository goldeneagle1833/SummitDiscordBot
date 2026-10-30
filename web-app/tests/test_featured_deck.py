"""Featured deck: a public deck the player pastes onto their own profile."""

import sqlite3

import pytest

import routes.api.players as players_routes

CURIOSA_URL = "https://sorcerytcg.com/decks/abc123"
DECK = {
    "name": "Fire Druid",
    "avatar": [{"name": "Druid", "type": "Avatar"}],
    "spellbook": [{"name": "Raging Taurus", "quantity": 2, "type": "Minion"}],
    "atlas": [{"name": "Arid Desert", "quantity": 4, "type": "Site"}],
    "sideboard": [],
}


@pytest.fixture
def profile(match_db):
    conn = sqlite3.connect(str(match_db))
    conn.execute(
        "INSERT INTO user_profiles (user_id, provider, display_name, first_login_at, last_login_at)"
        " VALUES ('100', 'discord', 'A', 'now', 'now')"
    )
    conn.commit()
    conn.close()


@pytest.fixture
def fetched(monkeypatch):
    calls = []

    def fake_fetch(url):
        calls.append(url)
        return dict(DECK) if "private" not in url else {}

    monkeypatch.setattr(players_routes, "_fetch_featured_deck", fake_fetch)
    return calls


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def test_unset_featured_deck_is_null(client, profile):
    assert client.get("/api/player/100/featured-deck").get_json() == {"deck": None}


def test_owner_features_a_public_deck_and_visitors_see_it(client, profile, fetched):
    _login(client, "100")
    resp = client.put(
        "/api/player/100/featured-deck",
        json={"url": CURIOSA_URL + "/edit?x=1", "auto_update": True},
    )
    assert resp.status_code == 200
    assert fetched == [CURIOSA_URL]

    _login(client, "200")
    deck = client.get("/api/player/100/featured-deck").get_json()["deck"]
    assert deck["url"] == CURIOSA_URL
    assert deck["name"] == "Fire Druid"
    assert deck["avatar"] == "Druid"
    assert deck["source"] == "curiosa"
    assert deck["auto_update"] is True
    assert [c["name"] for c in deck["spellbook"]] == ["Raging Taurus"]


def test_pso_links_are_accepted(client, profile, fetched):
    _login(client, "100")
    resp = client.put(
        "/api/player/100/featured-deck",
        json={"url": "https://playsorceryonline.com/?deck=Zx81ab_c"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["deck"]["source"] == "sorcery_online"


def test_unreadable_or_private_deck_is_refused(client, profile, fetched):
    _login(client, "100")
    resp = client.put("/api/player/100/featured-deck", json={"url": "https://sorcerytcg.com/decks/private1"})
    assert resp.status_code == 400
    assert "public" in resp.get_json()["error"]
    assert client.get("/api/player/100/featured-deck").get_json() == {"deck": None}


def test_only_deck_links_are_accepted(client, profile, fetched):
    _login(client, "100")
    resp = client.put("/api/player/100/featured-deck", json={"url": "https://example.com/decks/abc"})
    assert resp.status_code == 400
    assert fetched == []


def test_only_the_owner_can_change_it(client, profile, fetched):
    assert client.put("/api/player/100/featured-deck", json={"url": CURIOSA_URL}).status_code == 401
    assert client.delete("/api/player/100/featured-deck").status_code == 401
    _login(client, "200")
    assert client.put("/api/player/100/featured-deck", json={"url": CURIOSA_URL}).status_code == 403
    assert client.delete("/api/player/100/featured-deck").status_code == 403


def test_owner_removes_it(client, profile, fetched):
    _login(client, "100")
    client.put("/api/player/100/featured-deck", json={"url": CURIOSA_URL})
    assert client.delete("/api/player/100/featured-deck").status_code == 200
    assert client.get("/api/player/100/featured-deck").get_json() == {"deck": None}


def test_kept_updated_deck_refreshes_when_stale(client, profile, match_db, fetched, monkeypatch):
    from repositories.user_profiles import UserProfileRepository

    repo = UserProfileRepository(match_db)
    repo.set_featured_deck("100", CURIOSA_URL, DECK, auto_update=True)
    conn = sqlite3.connect(str(match_db))
    conn.execute("UPDATE user_profiles SET featured_deck_checked_at = '2020-01-01T00:00:00+00:00'")
    conn.commit()
    conn.close()

    started = []

    class InlineThread:
        def __init__(self, target, args, daemon):
            self.target, self.args = target, args

        def start(self):
            started.append(self.args)
            self.target(*self.args)

    monkeypatch.setattr(players_routes.threading, "Thread", InlineThread)
    updated = dict(DECK, name="Fire Druid v2")
    monkeypatch.setattr(players_routes, "_fetch_featured_deck", lambda url: updated)

    client.get("/api/player/100/featured-deck")
    assert started == [("100", CURIOSA_URL)]
    assert client.get("/api/player/100/featured-deck").get_json()["deck"]["name"] == "Fire Druid v2"
    # Freshly checked, so no second refresh
    assert len(started) == 1


def test_deck_left_alone_is_not_refreshed(client, profile, match_db, monkeypatch):
    from repositories.user_profiles import UserProfileRepository

    UserProfileRepository(match_db).set_featured_deck("100", CURIOSA_URL, DECK, auto_update=False)
    conn = sqlite3.connect(str(match_db))
    conn.execute("UPDATE user_profiles SET featured_deck_checked_at = '2020-01-01T00:00:00+00:00'")
    conn.commit()
    conn.close()
    monkeypatch.setattr(players_routes.threading, "Thread", lambda **kw: pytest.fail("refreshed"))
    assert client.get("/api/player/100/featured-deck").get_json()["deck"]["name"] == "Fire Druid"
