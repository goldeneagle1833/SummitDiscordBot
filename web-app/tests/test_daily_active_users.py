"""Daily active users on the admin analytics endpoint."""

import sqlite3
from datetime import datetime, timedelta

import pytest

import migrations.create_analytics_tables as analytics_migration
import repositories.analytics as analytics_mod
from repositories.analytics import AnalyticsRepository


def _ts(days_ago: int, hour: int = 12) -> str:
    return (datetime.utcnow() - timedelta(days=days_ago)).strftime(f"%Y-%m-%d {hour:02d}:00:00")


@pytest.fixture()
def seeded_db(app, tmp_path, monkeypatch):
    """A session_page_views table with three days of traffic."""
    db = tmp_path / "analytics.db"
    monkeypatch.setattr(analytics_mod, "ANALYTICS_DB_PATH", db)
    monkeypatch.setattr(analytics_migration, "ANALYTICS_DB_PATH", db)
    analytics_migration.create_analytics_tables()  # same schema as production
    AnalyticsRepository._session_views_ready = False
    AnalyticsRepository()._ensure_session_views_table()

    rows = [
        # today: 3 sessions, 2 of them logged in (one user on two sessions)
        ("s1", "/elo", _ts(0), "u1", "alice"),
        ("s1", "/player/u1", _ts(0, 13), "u1", "alice"),
        ("s2", "/elo", _ts(0), "u1", "alice"),
        ("s3", "/top-8", _ts(0), None, None),
        ("s4", "/top-8", _ts(0), "u2", "bob"),
        # yesterday: 1 anonymous session
        ("s5", "/elo", _ts(1), None, None),
        # 10 days ago: 2 sessions, 1 user  (outside a 7d window)
        ("s6", "/elo", _ts(10), "u3", "carol"),
        ("s7", "/elo", _ts(10), "", None),
    ]
    conn = sqlite3.connect(str(db))
    conn.executemany(
        "INSERT INTO session_page_views (session_id, path, timestamp, user_id, username) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    yield db
    AnalyticsRepository._session_views_ready = False


class TestRepository:
    def test_counts_distinct_sessions_and_users_per_day(self, seeded_db):
        data = AnalyticsRepository().get_daily_active_users()
        by_day = {d["date"]: d for d in data["daily"]}
        today = datetime.utcnow().date().isoformat()
        assert by_day[today] == {"date": today, "visitors": 4, "users": 2}
        assert data["today"] == {"visitors": 4, "users": 2}
        # newest first
        assert [d["date"] for d in data["daily"]] == sorted(by_day, reverse=True)

    def test_blank_user_id_is_not_a_user(self, seeded_db):
        data = AnalyticsRepository().get_daily_active_users()
        ten_days = (datetime.utcnow().date() - timedelta(days=10)).isoformat()
        row = next(d for d in data["daily"] if d["date"] == ten_days)
        assert row == {"date": ten_days, "visitors": 2, "users": 1}

    def test_averages_treat_missing_days_as_zero(self, seeded_db):
        data = AnalyticsRepository().get_daily_active_users()
        # 7d window: today (4 visitors, 2 users) + yesterday (1, 0), five empty days
        assert data["avg_7d"] == {"visitors": round(5 / 7, 1), "users": round(2 / 7, 1)}
        # 30d window also includes the 10-days-ago row
        assert data["avg_30d"] == {"visitors": round(7 / 30, 1), "users": round(3 / 30, 1)}

    def test_hours_filter_drops_old_days(self, seeded_db):
        data = AnalyticsRepository().get_daily_active_users(hours=48)
        assert len(data["daily"]) == 2
        assert all(d["visitors"] >= 1 for d in data["daily"])

    def test_empty_table(self, app, tmp_path, monkeypatch):
        monkeypatch.setattr(analytics_mod, "ANALYTICS_DB_PATH", tmp_path / "empty.db")
        AnalyticsRepository._session_views_ready = False
        data = AnalyticsRepository().get_daily_active_users()
        assert data["daily"] == []
        assert data["today"] == {"visitors": 0, "users": 0}
        assert data["avg_7d"] == {"visitors": 0, "users": 0}
        AnalyticsRepository._session_views_ready = False


class TestEndpoint:
    def test_stats_includes_active_users_for_admin(self, admin_session, seeded_db):
        resp = admin_session.get("/api/analytics/stats")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["active_users"]["today"] == {"visitors": 4, "users": 2}
        assert "avg_7d" in body["active_users"] and "daily" in body["active_users"]

    def test_stats_requires_admin(self, client, seeded_db):
        assert client.get("/api/analytics/stats").status_code == 403
