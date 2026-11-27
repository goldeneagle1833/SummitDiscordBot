"""Open match history API: GET /api/public/players/<id>/matches and /api/public/players/search.

Uses the live table layouts: Season 9+ games in season_match_records (made by
the real create_season_match_table) and past seasons in match_records_archive.
"""

import json
import sqlite3

import pytest

from services import data_release
from services import glicko2_season as g2
from services import public_match_history as history

P1, P2, P3 = "111111111111111111", "222222222222222222", "333333333333333333"
URL = f"/api/public/players/{P1}/matches"
SITE = "https://example.com"


def _deck(avatar, *elements):
    return json.dumps({
        "avatar": [{"name": avatar, "type": "Avatar"}],
        "spellbook": [{"name": f"Card {e}", "elements": e} for e in elements],
        "atlas": [{"name": "Some Site"}],
    })


def _insert(conn, table, winner, loser, ts, **cols):
    base = {
        "winner_id": winner, "winner_display_name": f"Name{winner[0]}",
        "losser_id": loser, "losser_display_name": f"Name{loser[0]}",
        "winner_elo_change": 16, "loser_elo_change": -16,
        "timestamp": ts, "source": "Discord", "match_type": "ranked",
        "json_deck_data_winner": _deck("Sparkmage", "Fire", "Air"),
        "json_deck_data_loser": _deck("Geomancer", "Earth"),
        "curiosa_url_winner": "https://curiosa.io/decks/secret-winner",
        "curiosa_url_loser": "https://curiosa.io/decks/secret-loser",
    }
    base.update(cols)
    names = ", ".join(base)
    marks = ", ".join("?" for _ in base)
    conn.execute(f"INSERT INTO {table} ({names}) VALUES ({marks})", tuple(base.values()))


@pytest.fixture()
def seeded(app, client, elo_db, match_db, monkeypatch):
    history.clear_cache()
    # Every call must name the site showing the data
    client.environ_base["HTTP_X_SUMMIT_SITE"] = SITE
    # Everything up to the end of 2027-01-31 is released
    monkeypatch.setattr(data_release, "cutoff_timestamp", lambda now=None: "2027-02-01T00:00:00")
    elo = sqlite3.connect(str(elo_db))
    elo.execute("INSERT INTO events (event_id, event_name, start_date, is_active) "
                "VALUES (8, 'Season 8', '2026-09-01T00:00:00', 0)")
    elo.execute("INSERT INTO events (event_id, event_name, start_date, is_active) "
                "VALUES (9, 'Gothic Season 9', '2027-01-01T00:00:00', 1)")
    elo.commit()
    elo.close()

    conn = sqlite3.connect(str(match_db))
    conn.execute("CREATE TABLE match_records_archive AS SELECT * FROM match_records WHERE 0")
    conn.execute("ALTER TABLE match_records_archive ADD COLUMN original_match_id INTEGER")
    _insert(conn, "match_records_archive", P1, P2, "2026-09-05T12:00:00", event_id=8)
    g2.create_season_match_table(conn)
    _insert(conn, "season_match_records", P2, P1, "2027-01-10T12:00:00", event_id=9,
            winner_went_first="Yes", loser_went_first="No", match_time=31)
    _insert(conn, "season_match_records", P1, P3, "2027-01-12T12:00:00", event_id=9,
            winner_event_games=3, loser_event_games=12)  # P1 provisional
    _insert(conn, "season_match_records", P1, P3, "2027-01-13T12:00:00", event_id=9, match_type="casual")
    _insert(conn, "season_match_records", P3, P1, "2027-02-03T12:00:00", event_id=9)  # not released
    conn.commit()
    conn.close()
    yield
    history.clear_cache()


def test_lists_ranked_matches_newest_first(client, seeded):
    r = client.get(URL)
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert r.headers["Access-Control-Allow-Origin"] == "*"
    assert body["player"] == {"id": P1, "name": "Name1"}
    assert body["terms_of_use"].endswith("/data-terms")
    dates = [m["date"] for m in body["matches"]]
    assert dates == sorted(dates, reverse=True)
    assert len(dates) == 4  # the casual game is left out
    assert body["record"] == {"wins": 2, "losses": 2, "games": 4, "win_rate": 50.0}


def test_avatar_and_elements_but_never_deck_lists(client, seeded):
    body = client.get(URL).get_json()
    loss = next(m for m in body["matches"] if m["date"] == "2027-01-10T12:00:00")
    assert loss["result"] == "loss"
    assert loss["player"] == {"avatar": "Geomancer", "elements": ["Earth"]}
    assert loss["opponent"] == {"id": P2, "name": "Name2", "avatar": "Sparkmage", "elements": ["Air", "Fire"]}
    assert loss["on_play"] is False and loss["match_time_minutes"] == 31
    assert loss["season"] == "Gothic Season 9" and loss["season_id"] == 9
    raw = json.dumps(body)
    assert "curiosa" not in raw and "secret" not in raw and "Card Fire" not in raw
    assert "Some Site" not in raw and "spellbook" not in raw


def test_unreleased_games_hide_deck_info(client, seeded):
    newest = client.get(URL).get_json()["matches"][0]
    assert newest["date"] == "2027-02-03T12:00:00"
    assert newest["deck_info_released"] is False
    assert newest["player"]["avatar"] is None and newest["opponent"]["elements"] is None
    assert newest["result"] == "loss"


def test_provisional_change_is_hidden(client, seeded):
    body = client.get(URL).get_json()
    game = next(m for m in body["matches"] if m["date"] == "2027-01-12T12:00:00")
    assert game["rating_change"] is None and game["rating_change_hidden"] is True
    other = next(m for m in body["matches"] if m["date"] == "2027-01-10T12:00:00")
    assert other["rating_change"] == -16


def test_archived_games_use_the_site_ids_and_season_filter(client, seeded):
    body = client.get(URL, query_string={"season": "8"}).get_json()
    assert [m["season"] for m in body["matches"]] == ["Season 8"]
    assert body["matches"][0]["match_id"] > history.ARCHIVE_ID_OFFSET
    current = client.get(URL, query_string={"season": "current"}).get_json()
    assert {m["season_id"] for m in current["matches"]} == {9}


def test_paging(client, seeded):
    body = client.get(URL, query_string={"per_page": 3, "page": 2}).get_json()
    assert len(body["matches"]) == 1
    assert body["pagination"] == {"page": 2, "per_page": 3, "total_matches": 4,
                                  "total_pages": 2, "has_next": False}


def test_profile_reset_hides_older_games(client, seeded, match_db):
    from repositories.user_profiles import UserProfileRepository

    repo = UserProfileRepository()
    conn = sqlite3.connect(str(match_db))
    conn.execute("INSERT INTO user_profiles (user_id, provider, display_name, first_login_at, last_login_at) "
                 "VALUES (?, 'discord', 'Name1', '2026-01-01', '2026-01-01')", (P1,))
    conn.commit()
    conn.close()
    repo.get_profile_visibility(P1)  # makes sure the extra profile columns exist
    conn = sqlite3.connect(str(match_db))
    conn.execute("UPDATE user_profiles SET profile_reset_at = '2027-01-11T00:00:00' WHERE user_id = ?", (P1,))
    conn.commit()
    conn.close()
    body = client.get(URL).get_json()
    # The season started 2027-01-01, before the reset, so the season's games stay
    assert all(m["date"] >= "2027-01-01" for m in body["matches"])
    assert len(body["matches"]) == 3


@pytest.mark.parametrize("query", [{"season": "drop"}, {"per_page": 0}, {"per_page": 101}, {"page": 0}])
def test_bad_params(client, seeded, query):
    assert client.get(URL, query_string=query).status_code == 400


def test_bad_id_and_unknown_player(client, seeded):
    assert client.get("/api/public/players/abc/matches").status_code == 400
    assert client.get("/api/public/players/999/matches").status_code == 404


def test_rate_limited(client, seeded, monkeypatch):
    from services import ranked_analytics

    monkeypatch.setattr(ranked_analytics, "claim_request", lambda key: False)
    assert client.get(URL).status_code == 429


def test_open_without_key_or_site_token(app, seeded):
    app.config["SITE_GATE_ENABLED"] = True
    try:
        assert app.test_client().get(URL, query_string={"site": SITE}).status_code == 200
        assert app.test_client().get("/api/public/players/search?q=Na&site=example.com").status_code == 200
    finally:
        app.config["SITE_GATE_ENABLED"] = False


def test_deck_info_reads_only_avatar_and_elements():
    deck = _deck("Pathfinder", "Water", "Water,Air", "None")
    assert history.deck_info(deck) == ("Pathfinder", ["Air", "Water"])
    assert history.deck_info("not json") == (None, [])
    assert history.deck_info(None) == (None, [])


# -- API usage log (admin page "API Usage") --------------------------------

def test_calls_are_logged_for_the_admin_page(client, seeded, admin_session, monkeypatch):
    from services import ranked_analytics

    client.get(URL, headers={"CF-Connecting-IP": "203.0.113.5", "User-Agent": "TestBot/1.0"})
    client.get(URL, headers={"CF-Connecting-IP": "203.0.113.5", "User-Agent": "TestBot/1.0"})
    client.get("/api/public/players/search?q=Na&site=https://Stats.Example.org/",
               headers={"CF-Connecting-IP": "198.51.100.7"})
    client.get(URL, query_string={"per_page": 500}, headers={"CF-Connecting-IP": "198.51.100.7"})
    monkeypatch.setattr(ranked_analytics, "claim_request", lambda key: False)
    client.get(URL, headers={"CF-Connecting-IP": "203.0.113.5"})

    r = admin_session.get("/api/admin/api-usage?days=7")
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["totals"]["calls"] == 5 and body["totals"]["callers"] == 2
    assert body["totals"]["ok"] == 3 and body["totals"]["limited"] == 1 and body["totals"]["bad_request"] == 1
    endpoints = {e["endpoint"]: e["calls"] for e in body["by_endpoint"]}
    assert endpoints == {"Match history": 4, "Player search": 1, "Staples": 0}
    top = body["top_callers"][0]
    assert top["ip"] == "203.0.113.5" and top["calls"] == 3 and top["limited"] == 1
    assert top["user_agent"] == "TestBot/1.0"
    assert len(body["by_day"]) == 7 and body["by_day"][-1]["calls"] == 5
    assert top["sites"] == [SITE]
    sites = {x["site"]: x for x in body["by_site"]}
    assert sites[SITE]["calls"] == 4 and sites[SITE]["callers"] == 2
    assert sites["https://stats.example.org"]["calls"] == 1  # header overridden by ?site=, cleaned up
    assert body["totals"]["sites"] == 2


def test_usage_is_admin_only(client, user_session):
    assert client.get("/api/admin/api-usage").status_code in (401, 403)
    assert user_session.get("/api/admin/api-usage").status_code in (401, 403)


def test_old_usage_rows_are_pruned(app):
    from datetime import datetime, timedelta, timezone

    from services import api_usage

    with app.test_request_context():
        now = datetime.now(timezone.utc)
        api_usage._last_prune = 0.0
        api_usage.record("api.staples.get_staples", 200, "1.2.3.4", None, now=now - timedelta(days=200))
        api_usage._last_prune = 0.0
        api_usage.record("api.staples.get_staples", 200, "1.2.3.4", None, now=now)
        assert api_usage.summary(90)["totals"]["calls"] == 1
        conn = api_usage._connect()
        assert conn.execute("SELECT COUNT(*) FROM api_usage_daily").fetchone()[0] == 1
        conn.close()


def test_site_is_required(client, seeded):
    client.environ_base.pop("HTTP_X_SUMMIT_SITE")
    for path in (URL, "/api/public/players/search?q=Na"):
        r = client.get(path)
        assert r.status_code == 400 and "site is required" in r.get_json()["error"]
    assert client.get(URL, query_string={"site": "not a url"}).status_code == 400
    assert client.get(URL, query_string={"site": "localhost"}).status_code == 400
    assert client.get(URL, query_string={"site": "mysite.gg"}).status_code == 200


def test_parse_site():
    from services.api_usage import parse_site

    assert parse_site("https://Example.COM/stats/") == "https://example.com/stats"
    assert parse_site("example.com") == "https://example.com"
    assert parse_site("http://example.com:8080?x=1") == "http://example.com:8080"
    for bad in ("", None, "ftp://example.com", "https://user:pw@example.com", "no spaces.com x",
                "localhost", "https://exa_mple.com", "x" * 300):
        assert parse_site(bad) is None
