"""Tests for GET /api/elements/avatar-meta (Elements page Meta chart)."""

import json
import sqlite3

import pytest


@pytest.fixture(autouse=True)
def _fresh_timeline_cache(monkeypatch, tmp_path):
    import routes.api.cards as cards
    monkeypatch.setattr(cards, "_TIMELINE_CACHE_DIR", tmp_path / "cache")
    cards.reset_timeline_cache()
    yield
    cards.reset_timeline_cache()


def _deck(avatar):
    return json.dumps({"avatar": [{"name": avatar}]})


@pytest.fixture()
def patched(monkeypatch, match_db, client):
    import routes.api.cards as cards
    monkeypatch.setattr(cards, "MATCH_RECORDS_DB_PATH", match_db)

    conn = sqlite3.connect(str(match_db))
    conn.execute("""
        CREATE TABLE match_records_archive (
            event_id INTEGER,
            timestamp TEXT,
            json_deck_data_winner TEXT,
            json_deck_data_loser TEXT
        )
    """)
    live = [
        ("2026-09-01 12:00:00", _deck("Sorcerer"), _deck("Druid"), "Discord"),
        ("2026-09-03 18:30:00", _deck("Sorcerer"), "{}", "Discord"),
        # Paper/web matches are not part of the online meta
        ("2026-09-03 19:00:00", _deck("Druid"), _deck("Druid"), "Paper"),
        # Unparseable timestamp is skipped
        ("not a date", _deck("Druid"), _deck("Druid"), "Discord"),
    ]
    for ts, w, l, src in live:
        conn.execute(
            "INSERT INTO match_records (timestamp, json_deck_data_winner, json_deck_data_loser, source) "
            "VALUES (?, ?, ?, ?)", (ts, w, l, src),
        )
    conn.execute(
        "INSERT INTO match_records_archive (event_id, timestamp, json_deck_data_winner, json_deck_data_loser) "
        "VALUES (7, '2026-08-30 10:00:00', ?, ?)", (_deck("Geomancer"), _deck("Sorcerer")),
    )
    conn.commit()
    conn.close()
    return client


def test_counts_each_deck_by_day_across_live_and_archive(patched):
    data = patched.get("/api/elements/avatar-meta").get_json()
    assert data["dates"] == ["2026-08-30", "2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03"]
    assert data["avatars"] == {
        "Sorcerer": {"2026-08-30": 1, "2026-09-01": 1, "2026-09-03": 1},
        "Druid": {"2026-09-01": 1},
        "Geomancer": {"2026-08-30": 1},
    }
    assert data["daily_totals"] == {"2026-08-30": 2, "2026-09-01": 2, "2026-09-03": 1}


def test_public_without_login(patched):
    assert patched.get("/api/elements/avatar-meta").status_code == 200


def test_empty_database(monkeypatch, match_db, client):
    import routes.api.cards as cards
    monkeypatch.setattr(cards, "MATCH_RECORDS_DB_PATH", match_db)
    data = client.get("/api/elements/avatar-meta").get_json()
    assert data == {"dates": [], "avatars": {}, "pairs": {}, "daily_totals": {}}


def test_event_filter_limits_to_that_event(patched):
    data = patched.get("/api/elements/avatar-meta?event=7").get_json()
    assert data["dates"] == ["2026-08-30"]
    assert data["avatars"] == {"Geomancer": {"2026-08-30": 1}, "Sorcerer": {"2026-08-30": 1}}


# --- /api/elements/timeline ---

def _spellbook(*cards):
    return json.dumps({"avatar": [{"name": "Sorcerer"}],
                       "spellbook": [{"name": n, "quantity": q} for n, q in cards]})


@pytest.fixture()
def timeline(monkeypatch, match_db, client):
    import routes.api.cards as cards
    monkeypatch.setattr(cards, "MATCH_RECORDS_DB_PATH", match_db)
    monkeypatch.setattr(cards, "_load_card_elements", lambda: {
        "fireball": ["Fire"], "tide": ["Water"], "boulder": ["Earth"],
    })
    conn = sqlite3.connect(str(match_db))
    rows = [
        # Fire-heavy Fire/Water deck beats an Earth deck
        ("2026-09-01 12:00:00", _spellbook(("Fireball", 3), ("Tide", 1)), _spellbook(("Boulder", 2))),
        ("2026-09-03 12:00:00", _spellbook(("Boulder", 2)), _spellbook(("Tide", 2))),
    ]
    for ts, w, l in rows:
        conn.execute(
            "INSERT INTO match_records (timestamp, json_deck_data_winner, json_deck_data_loser, source) "
            "VALUES (?, ?, ?, 'Discord')", (ts, w, l),
        )
    conn.commit()
    conn.close()
    return client


def test_meta_pairs_split_avatar_by_top_two_elements(timeline):
    data = timeline.get("/api/elements/avatar-meta").get_json()
    assert data["pairs"] == {
        "Sorcerer|Fire / Water": {"2026-09-01": 1},
        "Sorcerer|Earth": {"2026-09-01": 1, "2026-09-03": 1},
        "Sorcerer|Water": {"2026-09-03": 1},
    }


def test_element_pair_keeps_top_two_alphabetical():
    from routes.api.cards import _element_pair
    assert _element_pair({"Water": 9, "Fire": 3, "Air": 1}) == "Fire / Water"
    assert _element_pair({"Earth": 4}) == "Earth"
    assert _element_pair({}) == ""


def test_timeline_daily_counts_public(timeline):
    data = timeline.get("/api/elements/timeline").get_json()
    assert data["dates"] == ["2026-09-01", "2026-09-02", "2026-09-03"]
    assert data["days"]["2026-09-01"] == {
        "el": {"Fire": [1, 0], "Water": [1, 0], "Earth": [0, 1]},
        "dom": {"Fire": [1, 0], "Earth": [0, 1]},
    }
    assert data["days"]["2026-09-03"]["el"] == {"Earth": [1, 0], "Water": [0, 1]}
    assert data["is_admin"] is False


def test_timeline_admin_gets_splash_and_combos(timeline, admin_session):
    day = timeline.get("/api/elements/timeline").get_json()["days"]["2026-09-01"]
    assert day["spl"] == {"Water": [1, 0]}
    assert day["combo"] == {"Fire, Water": [1, 0], "Earth": [0, 1]}


# --- caching ---

def test_timeline_is_built_once_and_shared_by_both_endpoints(timeline, monkeypatch):
    import routes.api.cards as cards
    calls = []
    real = cards._build_timeline
    monkeypatch.setattr(cards, "_build_timeline", lambda ev: calls.append(ev) or real(ev))
    timeline.get("/api/elements/timeline")
    timeline.get("/api/elements/avatar-meta")
    timeline.get("/api/elements/timeline")
    assert calls == ["all"]
    timeline.get("/api/elements/timeline?event=7")
    assert calls == ["all", "7"]


def test_stale_cache_serves_old_data_while_rebuilding(timeline, monkeypatch):
    import routes.api.cards as cards
    first = timeline.get("/api/elements/avatar-meta").get_json()

    started = []

    class FakeThread:
        def __init__(self, target, args, name, daemon):
            self.target, self.args = target, args

        def start(self):
            started.append(self.args[0])

    monkeypatch.setattr(cards.threading, "Thread", FakeThread)
    monkeypatch.setattr(cards, "_TIMELINE_TTL", 0)
    again = timeline.get("/api/elements/avatar-meta").get_json()
    assert again == first
    assert started == ["all"]
    # A second request while that rebuild is running doesn't start another
    timeline.get("/api/elements/avatar-meta")
    assert started == ["all"]


def test_other_workers_reuse_the_shared_cache_file(timeline, monkeypatch):
    import routes.api.cards as cards
    first = timeline.get("/api/elements/timeline").get_json()
    # A fresh worker: empty memory, same cache directory
    cards.reset_timeline_cache()
    calls = []
    monkeypatch.setattr(cards, "_build_timeline", lambda ev: calls.append(ev))
    assert timeline.get("/api/elements/timeline").get_json() == first
    assert calls == []


def test_made_up_event_filters_share_the_all_events_build(timeline, monkeypatch):
    import routes.api.cards as cards
    calls = []
    real = cards._build_timeline
    monkeypatch.setattr(cards, "_build_timeline", lambda ev: calls.append(ev) or real(ev))
    for junk in ("x" * 500, "../etc", "1; drop", "all"):
        assert timeline.get("/api/elements/timeline", query_string={"event": junk}).status_code == 200
    assert calls == ["all"]


def test_concurrent_first_visits_wait_on_one_build(timeline, monkeypatch):
    import threading
    import time as time_mod
    import routes.api.cards as cards
    calls = []
    real = cards._build_timeline

    def slow(ev):
        calls.append(ev)
        time_mod.sleep(0.3)
        return real(ev)

    monkeypatch.setattr(cards, "_build_timeline", slow)
    results = []
    threads = [threading.Thread(target=lambda: results.append(cards._timeline_data("all"))) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert calls == ["all"]
    assert len(results) == 4 and all(r == results[0] for r in results)


def test_failed_first_build_answers_503(timeline, monkeypatch):
    import routes.api.cards as cards

    def boom(ev):
        raise RuntimeError("db gone")

    monkeypatch.setattr(cards, "_build_timeline", boom)
    assert timeline.get("/api/elements/timeline").status_code == 503
