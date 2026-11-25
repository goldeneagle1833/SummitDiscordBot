"""Background polling clean-up: the combined top bar check and heartbeat sessions."""

import sqlite3

import pytest

import repositories.analytics as analytics_mod
from repositories.analytics import AnalyticsRepository


# ----------------------------------------------------------------------
# /api/nav/checks
# ----------------------------------------------------------------------

def test_nav_checks_needs_login(client):
    assert client.get("/api/nav/checks").status_code == 401


def test_nav_checks_matches_the_three_old_endpoints(user_session, monkeypatch, tmp_path):
    import repositories.store as store_mod
    import routes.api.match_reporting as mr
    import routes.api.streamers as streamers_mod

    import routes.api.store as store_routes
    store = store_mod.StoreRepository(db_path=tmp_path / "store.db")
    monkeypatch.setattr(store_routes, "_repo", lambda: store)
    fake_pending = [{"id": 7, "submitter_display_name": "Opp"}]
    monkeypatch.setattr(mr, "pending_confirmations_for_user", lambda uid: list(fake_pending))
    monkeypatch.setattr(streamers_mod, "get_active_streamers", lambda: [{
        "display_name": "Streamer", "avatar_url": None, "stream_url": "https://x",
        "stream_title": "t", "game_name": "g", "platform": "Discord",
    }])
    store.create_web_notification("regular_user_1", "order", "Order shipped", "b")

    # Act like the live site, so the banner shows real (patched) data, not the demo streamer
    monkeypatch.setattr(streamers_mod, "_is_local_request", lambda: False)
    base = {}
    data = user_session.get("/api/nav/checks", **base).get_json()
    assert data["pending_confirmations"] == fake_pending
    assert [n["title"] for n in data["notifications"]] == ["Order shipped"]
    assert data["streamer"]["display_name"] == "Streamer"

    # Old endpoints still answer the same way
    old_notifs = user_session.get("/api/store/notifications", **base).get_json()
    assert old_notifs["notifications"] == data["notifications"]
    banner = user_session.get("/api/streamers/banner", **base)
    assert banner.get_json()["streamer"] == data["streamer"]
    assert "max-age=60" in banner.headers["Cache-Control"]


def test_nav_checks_parts_fail_independently(user_session, monkeypatch, tmp_path):
    import repositories.store as store_mod
    import routes.api.match_reporting as mr
    import routes.api.streamers as streamers_mod

    import routes.api.store as store_routes
    store = store_mod.StoreRepository(db_path=tmp_path / "store.db")
    monkeypatch.setattr(store_routes, "_repo", lambda: store)

    def boom(uid):
        raise RuntimeError("db down")

    monkeypatch.setattr(mr, "pending_confirmations_for_user", boom)
    monkeypatch.setattr(streamers_mod, "get_active_streamers", lambda: [])
    store.create_web_notification("regular_user_1", "order", "Hi", "b")

    monkeypatch.setattr(streamers_mod, "_is_local_request", lambda: False)
    resp = user_session.get("/api/nav/checks")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["pending_confirmations"] == []
    assert len(data["notifications"]) == 1
    assert data["streamer"] is None


# ----------------------------------------------------------------------
# Heartbeat sessions -> Session Analytics
# ----------------------------------------------------------------------

@pytest.fixture()
def analytics(tmp_path, monkeypatch):
    db = tmp_path / "analytics.db"
    monkeypatch.setattr(analytics_mod, "ANALYTICS_DB_PATH", db)
    monkeypatch.setattr(analytics_mod, "_last_persist_time", 0)
    AnalyticsRepository._completed_sessions_ready = False
    AnalyticsRepository._session_views_ready = False
    repo = AnalyticsRepository()
    repo._ensure_active_sessions_table()
    return repo, db


def _age_session(db, sid, first_ago, last_ago):
    conn = sqlite3.connect(db)
    conn.execute(
        """UPDATE active_sessions
           SET first_seen = strftime('%Y-%m-%d %H:%M:%S', 'now', ?),
               last_seen = strftime('%Y-%m-%d %H:%M:%S', 'now', ?)
           WHERE session_id = ?""",
        (f"-{first_ago} seconds", f"-{last_ago} seconds", sid),
    )
    conn.commit()
    conn.close()


def _rows(db, sql, *args):
    conn = sqlite3.connect(db)
    rows = conn.execute(sql, args).fetchall()
    conn.close()
    return rows


def test_active_count_counts_a_once_a_minute_heartbeat(analytics):
    repo, db = analytics
    repo.record_heartbeat("tab-1")
    _age_session(db, "tab-1", 300, 70)  # last check-in 70 s ago, next due ~now
    assert repo.get_active_user_count() == 1
    assert len(repo.get_active_sessions()) == 1


def test_ended_session_is_saved_before_it_is_cleared(analytics, monkeypatch):
    repo, db = analytics
    repo.record_heartbeat("tab-1")
    _age_session(db, "tab-1", 600, 200)  # ended 200 s ago, lasted 400 s
    monkeypatch.setattr(analytics_mod, "_last_persist_time", 0)  # a minute has passed
    repo.record_heartbeat("tab-2")       # any later heartbeat triggers the save

    saved = _rows(db, "SELECT session_id, duration_seconds FROM completed_sessions")
    assert saved == [("tab-1", 400)]
    active = {r[0] for r in _rows(db, "SELECT session_id FROM active_sessions")}
    assert active == {"tab-2"}


def test_returning_tab_adds_to_its_saved_visit(analytics, monkeypatch):
    repo, db = analytics
    repo.record_heartbeat("tab-1")
    _age_session(db, "tab-1", 1000, 900)  # first stretch: 100 s
    repo.persist_expired_sessions()

    repo.record_heartbeat("tab-1")        # tab shown again later, same id
    _age_session(db, "tab-1", 400, 300)   # second stretch: 100 s
    repo.persist_expired_sessions()

    assert _rows(db, "SELECT duration_seconds FROM completed_sessions WHERE session_id='tab-1'") == [(200,)]
    assert _rows(db, "SELECT COUNT(*) FROM active_sessions") == [(0,)]
