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


class InlineThread:
    """Runs a background refresh straight away, so tests can see its result."""

    started = []

    def __init__(self, target, args, daemon):
        self.target, self.args = target, args

    def start(self):
        InlineThread.started.append(self.args)
        self.target(*self.args)


@pytest.fixture(autouse=True)
def inline_threads(monkeypatch):
    InlineThread.started = []
    monkeypatch.setattr(players_routes.threading, "Thread", InlineThread)
    return InlineThread.started


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


def test_nothing_is_featured_until_the_player_chooses(client, profile, games, fetched):
    # Even with games on public-looking decks, the site never picks one
    assert client.get("/api/player/100/featured-deck").get_json() == {"deck": None}
    assert fetched == []


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
    assert client.get("/api/player/100/featured-deck").get_json()["deck"] is None


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


def test_owner_removes_it(client, profile, games, fetched):
    _login(client, "100")
    client.put("/api/player/100/featured-deck", json={"url": CURIOSA_URL})
    assert client.delete("/api/player/100/featured-deck").status_code == 200
    fetched.clear()
    assert client.get("/api/player/100/featured-deck").get_json() == {"deck": None}
    assert fetched == []


def test_kept_updated_deck_refreshes_when_stale(client, profile, match_db, fetched, monkeypatch, inline_threads):
    from repositories.user_profiles import UserProfileRepository

    repo = UserProfileRepository(match_db)
    repo.set_featured_deck("100", CURIOSA_URL, DECK, auto_update=True)
    conn = sqlite3.connect(str(match_db))
    conn.execute("UPDATE user_profiles SET featured_deck_checked_at = '2020-01-01T00:00:00+00:00'")
    conn.commit()
    conn.close()

    updated = dict(DECK, name="Fire Druid v2")
    monkeypatch.setattr(players_routes, "_fetch_featured_deck", lambda url: updated)

    client.get("/api/player/100/featured-deck")
    started = inline_threads
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


@pytest.fixture
def games(match_db, monkeypatch):
    """Player 100 has games on a deck link."""
    monkeypatch.setattr(players_routes, "MATCH_RECORDS_DB_PATH", match_db)
    conn = sqlite3.connect(str(match_db))
    for _ in range(3):
        conn.execute(
            """INSERT INTO match_records
               (winner_id, winner_display_name, losser_id, losser_display_name,
                timestamp, match_type, reporter_id, curiosa_url_winner)
               VALUES ('100', 'A', '200', 'B', '2026-10-29 12:00:00', 'ranked', '100', ?)""",
            ("https://sorcerytcg.com/decks/played",),
        )
    conn.commit()
    conn.close()


def test_decks_the_site_picked_are_cleared(client, profile, match_db, fetched):
    """Picks saved by the removed automatic default never show, and are wiped."""
    from repositories.user_profiles import UserProfileRepository

    conn = sqlite3.connect(str(match_db))
    conn.execute(
        "INSERT INTO user_profiles (user_id, provider, display_name, first_login_at, last_login_at)"
        " VALUES ('300', 'discord', 'C', 'now', 'now')"
    )
    conn.commit()
    conn.close()
    repo = UserProfileRepository(match_db)
    repo.set_featured_deck("100", CURIOSA_URL, DECK, auto_update=True)  # chosen by the player
    repo.set_featured_deck("300", "https://sorcerytcg.com/decks/private9", DECK, True, source="auto")

    # Hidden straight away...
    assert client.get("/api/player/300/featured-deck").get_json() == {"deck": None}
    # ...and gone once the repository starts up again (as on deploy)
    UserProfileRepository(match_db)
    assert UserProfileRepository(match_db).get_featured_deck("300") is None
    assert UserProfileRepository(match_db).get_featured_deck("100")["url"] == CURIOSA_URL
