"""Menu new-content dots: latest-content times per page and per-user "seen"."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

import webapp_config
from repositories.nav_seen import NavSeenRepository
from services import new_content

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture()
def sources(tmp_path, monkeypatch):
    """Point every source at empty temp data; tests fill in what they need."""
    top8 = tmp_path / "top8"
    top8.mkdir()
    monkeypatch.setattr(webapp_config, "TOP_8_DIR", top8)
    monkeypatch.setattr(webapp_config, "ARTICLES_DB_PATH", tmp_path / "articles.db")
    monkeypatch.setattr(webapp_config, "EXPLORER_DB_PATH", tmp_path / "explorer.db")
    monkeypatch.setattr(webapp_config, "MATCH_RECORDS_DB_PATH", tmp_path / "match.db")
    import repositories.store as store_mod
    monkeypatch.setattr(store_mod, "STORE_DB_PATH", tmp_path / "store.db")
    new_content.clear_cache()
    yield tmp_path
    new_content.clear_cache()


class TestParseTime:
    def test_utc_z(self):
        assert new_content.parse_time("2026-11-01T10:00:00Z", True) == datetime(2026, 11, 1, 10, tzinfo=timezone.utc)

    def test_sqlite_space_format_is_utc(self):
        assert new_content.parse_time("2026-11-01 10:00:00", True) == datetime(2026, 11, 1, 10, tzinfo=timezone.utc)

    def test_bad_value(self):
        assert new_content.parse_time("soon", True) is None
        assert new_content.parse_time(None, True) is None


class TestComputeLatest:
    def test_stats_release_is_1st_or_15th_at_0001_utc(self, sources):
        latest = new_content.compute_latest(NOW)
        assert latest["meta-report"] == "2026-11-01T00:01:00Z"
        assert latest["avatars"] == latest["card-stats"] == latest["meta-report"]
        notes = new_content.compute_new_content(NOW)["notes"]
        assert notes["avatars"]["text"] == "New stats batch: games through Oct 31"

    def test_old_content_is_outside_window(self, sources):
        added = (NOW - timedelta(days=20)).astimezone().replace(tzinfo=None)
        (sources / "top8" / "latest_event.json").write_text(
            json.dumps({"folder": "X", "added_at": added.strftime("%Y-%m-%dT%H:%M:%S")}))
        assert "top-8" not in new_content.compute_latest(NOW)

    def test_top8_import_dots_deck_pages(self, sources):
        added = (NOW - timedelta(days=1)).astimezone().replace(tzinfo=None)
        (sources / "top8" / "latest_event.json").write_text(
            json.dumps({"folder": "X", "added_at": added.strftime("%Y-%m-%dT%H:%M:%S")}))
        latest = new_content.compute_latest(NOW)
        assert latest["top-8"] == latest["deck-rec"] == latest["deck-archetypes"] == _iso(NOW - timedelta(days=1))
        note = new_content.compute_new_content(NOW)["notes"]["top-8"]
        assert note == {"text": "New Top 8 event: X", "link": "/top-8/X"}

    def test_approved_article_only(self, sources):
        from repositories.articles import ArticleRepository
        ArticleRepository()  # creates tables
        conn = sqlite3.connect(webapp_config.ARTICLES_DB_PATH)
        cols = "slug,title,summary,category,author_id,author_name,status,created_at,updated_at,submitted_at,published_at"
        conn.execute(f"INSERT INTO articles ({cols}) VALUES ('a','A','s','c','1','n','approved','x','x','x',?)",
                     (_iso(NOW - timedelta(days=2)),))
        conn.execute(f"INSERT INTO articles ({cols}) VALUES ('b','B','s','c','1','n','pending','x','x','x',?)",
                     (_iso(NOW - timedelta(hours=1)),))
        conn.commit()
        conn.close()
        assert new_content.compute_latest(NOW)["articles"] == _iso(NOW - timedelta(days=2))
        note = new_content.compute_new_content(NOW)["notes"]["articles"]
        assert note["text"] == "New article: A" and note["link"].endswith("-a")

    def test_store_ignores_hidden_products(self, sources):
        from repositories.store import StoreRepository
        repo = StoreRepository(sources / "store.db")
        with repo._connect() as conn:
            sf = conn.execute("SELECT id FROM storefronts WHERE is_active = 1 LIMIT 1").fetchone()
            if sf is None:
                conn.execute("INSERT INTO storefronts (slug, name, is_active, created_at) VALUES ('s','S',1,'x')")
                sf = conn.execute("SELECT id FROM storefronts WHERE is_active = 1 LIMIT 1").fetchone()
            for sku, active, when in (("a", 1, NOW - timedelta(days=3)), ("b", 0, NOW - timedelta(hours=1))):
                conn.execute(
                    "INSERT INTO products (sku, name, price_cents, is_active, created_at, updated_at, storefront_id) "
                    "VALUES (?, ?, 100, ?, ?, ?, ?)", (sku, sku, active, when.isoformat(), when.isoformat(), sf[0]))
        assert new_content.compute_latest(NOW)["store"] == _iso(NOW - timedelta(days=3))

    def test_missing_sources_are_skipped(self, sources):
        latest = new_content.compute_latest(NOW)
        for key in ("top-8", "articles", "brackets", "explorer", "store"):
            assert key not in latest


class TestSeenRepo:
    def test_mark_and_get(self, tmp_path):
        repo = NavSeenRepository(tmp_path / "m.db")
        assert repo.get_seen("u1") == {}
        repo.mark_seen("u1", ["top-8", "store"])
        seen = repo.get_seen("u1")
        assert set(seen) == {"top-8", "store"}
        assert repo.get_seen("u2") == {}


class TestRoutes:
    def test_logged_out_gets_latest_only(self, client, sources, monkeypatch):
        import routes.api.nav as nav
        fake = {"latest": {"top-8": "2026-11-08T00:00:00Z"}, "notes": {"top-8": {"text": "New Top 8 event: X", "link": "/top-8/X"}}}
        monkeypatch.setattr(nav, "get_new_content", lambda: fake)
        data = client.get("/api/nav/new-content").get_json()
        assert data == {**fake, "seen": None}

    def test_logged_in_mark_seen_round_trip(self, client, sources, monkeypatch):
        import routes.api.nav as nav
        monkeypatch.setattr(nav, "get_new_content", lambda: {"latest": {"top-8": "2026-11-08T00:00:00Z"}, "notes": {}})
        with client.session_transaction() as sess:
            sess["user_id"] = "123"
        assert client.get("/api/nav/new-content").get_json()["seen"] == {}
        res = client.post("/api/nav/seen", json={"pages": ["top-8", "bogus"]})
        assert res.status_code == 200
        assert res.get_json()["pages"] == ["top-8"]
        seen = client.get("/api/nav/new-content").get_json()["seen"]
        assert list(seen) == ["top-8"]

    def test_mark_seen_needs_login_and_known_page(self, client, sources):
        assert client.post("/api/nav/seen", json={"pages": ["top-8"]}).status_code == 401
        with client.session_transaction() as sess:
            sess["user_id"] = "123"
        assert client.post("/api/nav/seen", json={"pages": ["nope"]}).status_code == 400
        assert client.post("/api/nav/seen", json={}).status_code == 400
