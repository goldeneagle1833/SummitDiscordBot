"""CSV export of page views on the admin analytics dashboard."""

import csv
import io
import sqlite3
from datetime import datetime, timedelta

import pytest

import migrations.create_analytics_tables as analytics_migration
import repositories.analytics as analytics_mod
from repositories.analytics import AnalyticsRepository, page_pattern


def _ts(days_ago: int) -> str:
    return (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%d 12:00:00")


@pytest.fixture()
def seeded(app, tmp_path, monkeypatch):
    db = tmp_path / "analytics.db"
    monkeypatch.setattr(analytics_mod, "ANALYTICS_DB_PATH", db)
    monkeypatch.setattr(analytics_migration, "ANALYTICS_DB_PATH", db)
    analytics_migration.create_analytics_tables()
    AnalyticsRepository._session_views_ready = False
    AnalyticsRepository()._ensure_session_views_table()

    visits = [  # (session, path, days ago)
        ("s1", "/elo", 0), ("s1", "/player/111", 0), ("s2", "/player/222", 0),
        ("s2", "/elo", 1), ("s3", "/player/111", 2), ("s4", "/top-8/compare", 1),
        ("s5", "/elo", 40),
    ]
    conn = sqlite3.connect(str(db))
    for sid, path, ago in visits:
        conn.execute("INSERT INTO page_views (path, timestamp) VALUES (?, ?)", (path, _ts(ago)))
        conn.execute("INSERT INTO session_page_views (session_id, path, timestamp) VALUES (?, ?, ?)",
                     (sid, path, _ts(ago)))
    conn.commit()
    conn.close()
    yield
    AnalyticsRepository._session_views_ready = False


def _rows(resp):
    return list(csv.DictReader(io.StringIO(resp.get_data(as_text=True))))


def test_page_pattern_folds_ids():
    assert page_pattern("/player/123") == "/player/:id"
    assert page_pattern("/player/123/avatar/Seer") == "/player/:id/avatar/:name"
    assert page_pattern("/top-8/compare") == "/top-8/compare"
    assert page_pattern("/top-8/gothic-1") == "/top-8/:event"
    assert page_pattern("/elo") == "/elo"


def test_admin_only(seeded, client):
    assert client.get("/api/analytics/page-views.csv").status_code in (401, 403)


def test_by_page_all_time(seeded, admin_session):
    resp = admin_session.get("/api/analytics/page-views.csv")
    assert resp.status_code == 200
    assert "attachment" in resp.headers["Content-Disposition"]
    rows = {r["page"]: r for r in _rows(resp)}
    assert rows["/elo"] == {"page": "/elo", "views": "3", "visitors": "3", "urls": "1"}
    assert rows["/player/:id"] == {"page": "/player/:id", "views": "3", "visitors": "3", "urls": "2"}


def test_by_url_last_30_days(seeded, admin_session):
    rows = _rows(admin_session.get(f"/api/analytics/page-views.csv?by=url&hours={30 * 24}"))
    by_url = {r["url"]: r for r in rows}
    assert by_url["/elo"]["views"] == "2"
    assert by_url["/player/111"] == {"url": "/player/111", "page": "/player/:id", "views": "2", "visitors": "2"}
    assert rows[0]["views"] >= rows[-1]["views"]
