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


def test_no_games_and_nothing_set_shows_nothing(client, profile, fetched):
    assert client.get("/api/player/100/featured-deck").get_json() == {"deck": None, "mode": "auto"}
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


def test_owner_turns_it_off(client, profile, games, fetched):
    _login(client, "100")
    client.put("/api/player/100/featured-deck", json={"url": CURIOSA_URL})
    assert client.delete("/api/player/100/featured-deck").status_code == 200
    fetched.clear()
    # Off means off: not even the automatic pick
    assert client.get("/api/player/100/featured-deck").get_json() == {"deck": None, "mode": "off"}
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
    assert started == [("100", CURIOSA_URL, False)]
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


# -- Automatic pick: the most-played deck that is public on its site --------

PSO_URL = "https://playsorceryonline.com/?deck=Zx81ab_c"
PRIVATE_URL = "https://sorcerytcg.com/decks/private9"


@pytest.fixture
def games(match_db, monkeypatch):
    """Player 100: a private deck played most, then a public PSO deck, then CURIOSA_URL once."""
    monkeypatch.setattr(players_routes, "MATCH_RECORDS_DB_PATH", match_db)
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    rows = []
    for i in range(4):
        rows.append(("100", "200", PRIVATE_URL, None, now - timedelta(days=1, minutes=i)))
    for i in range(3):
        # Lost, so the deck is on the loser side
        rows.append(("200", "100", None, PSO_URL + "&tab=x", now - timedelta(days=2, minutes=i)))
    rows.append(("100", "200", CURIOSA_URL, None, now - timedelta(days=3)))
    # Played a lot, but long ago: doesn't count while there are recent games
    for i in range(9):
        rows.append(("100", "200", "https://sorcerytcg.com/decks/oldfave", None, now - timedelta(days=90, minutes=i)))
    conn = sqlite3.connect(str(match_db))
    for w, l, wurl, lurl, ts in rows:
        conn.execute(
            """INSERT INTO match_records
               (winner_id, winner_display_name, losser_id, losser_display_name,
                timestamp, match_type, reporter_id, curiosa_url_winner, curiosa_url_loser)
               VALUES (?, 'A', ?, 'B', ?, 'ranked', ?, ?, ?)""",
            (w, l, ts.strftime("%Y-%m-%d %H:%M:%S"), w, wurl, lurl),
        )
    conn.commit()
    conn.close()


def test_most_played_public_deck_is_featured_by_default(client, profile, games, fetched):
    data = client.get("/api/player/100/featured-deck").get_json()
    # The private deck is tried first and skipped
    assert fetched[:2] == [PRIVATE_URL, PSO_URL]
    assert data["mode"] == "auto"

    # Visitors see the pick, labelled as automatic
    deck = client.get("/api/player/100/featured-deck").get_json()["deck"]
    assert deck["url"] == PSO_URL
    assert deck["picked"] == "auto"
    # Picked once a day, not on every visit
    assert len(fetched) == 2


def test_old_games_count_when_there_are_no_recent_ones(client, profile, match_db, games, fetched):
    conn = sqlite3.connect(str(match_db))
    conn.execute("DELETE FROM match_records WHERE timestamp > '2026-01-01' AND curiosa_url_winner != 'https://sorcerytcg.com/decks/oldfave'")
    conn.execute("DELETE FROM match_records WHERE curiosa_url_winner IS NOT 'https://sorcerytcg.com/decks/oldfave'")
    conn.commit()
    conn.close()
    client.get("/api/player/100/featured-deck")
    assert fetched == ["https://sorcerytcg.com/decks/oldfave"]


def test_a_pasted_deck_wins_over_the_automatic_pick(client, profile, games, fetched):
    client.get("/api/player/100/featured-deck")
    _login(client, "100")
    client.put("/api/player/100/featured-deck", json={"url": CURIOSA_URL})
    deck = client.get("/api/player/100/featured-deck").get_json()["deck"]
    assert deck["url"] == CURIOSA_URL and deck["picked"] == "manual"


def test_owner_goes_back_to_the_automatic_pick(client, profile, games, fetched):
    _login(client, "100")
    client.put("/api/player/100/featured-deck", json={"url": CURIOSA_URL})
    assert client.put("/api/player/100/featured-deck", json={"mode": "auto"}).status_code == 200
    # The pick starts straight away (inline here), so the next visit has it
    data = client.get("/api/player/100/featured-deck").get_json()
    assert data["mode"] == "auto" and data["deck"]["url"] == PSO_URL


def test_no_public_deck_is_remembered_for_a_day(client, profile, games, monkeypatch):
    calls = []
    monkeypatch.setattr(players_routes, "_fetch_featured_deck", lambda url: calls.append(url) or {})
    assert client.get("/api/player/100/featured-deck").get_json()["deck"] is None
    tried = len(calls)
    assert tried == players_routes.FEATURED_DECK_AUTO_TRIES
    client.get("/api/player/100/featured-deck")
    assert len(calls) == tried
