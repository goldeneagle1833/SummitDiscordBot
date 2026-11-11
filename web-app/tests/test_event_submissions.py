"""Player-submitted Top 8 events: held for approval, DMs queued, Local tag, badges-only."""

import sqlite3

import pytest

import routes.api.events as events_routes
import webapp_config

EVENT_URL = "https://sorcerytcg.com/events/evt123"


@pytest.fixture()
def env(app, match_db, tmp_path, monkeypatch):
    import repositories.event_submissions as sub_repo
    import repositories.paper_links as paper_links
    from services import paper_finishes

    monkeypatch.setattr(sub_repo, "MATCH_RECORDS_DB_PATH", match_db)
    monkeypatch.setattr(paper_links, "MATCH_RECORDS_DB_PATH", match_db)
    monkeypatch.setattr(webapp_config, "ARTICLES_DB_PATH", tmp_path / "articles.db")
    monkeypatch.setattr(webapp_config, "ADMINS", ["123456789", "admin_user_1"])
    monkeypatch.setattr(paper_finishes, "top8_event_ids", lambda: {})
    monkeypatch.setattr(events_routes, "_JOBS_DIR", str(tmp_path))
    monkeypatch.setattr(events_routes, "_JOB_HEARTBEAT_SECONDS", 3600)
    started = []
    monkeypatch.setattr(events_routes, "_start_job", lambda fn, args: started.append((fn.__name__, args)))
    return {"started": started, "articles_db": tmp_path / "articles.db"}


def _dms(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM article_notifications ORDER BY id")]
    conn.close()
    return rows


def _login(client, user_id="555000111", provider="discord"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = "Ruben"
        sess["auth_provider"] = provider
    return client


def test_must_be_logged_in(client, env):
    resp = client.post("/api/events/submissions", json={"event_url": EVENT_URL})
    assert resp.status_code == 401


def test_rejects_non_sorcery_links(client, env):
    resp = _login(client).post("/api/events/submissions", json={"event_url": "https://example.com/x"})
    assert resp.status_code == 400


def test_submission_is_held_and_previewed(client, env):
    resp = _login(client).post("/api/events/submissions", json={"event_url": EVENT_URL, "note": "Columbus weekly"})
    assert resp.status_code == 201
    body = resp.get_json()["submission"]
    assert body["status"] == "pending"
    assert env["started"][0][0] == "_run_submission_preview"

    # Same event again is refused while it waits
    again = client.post("/api/events/submissions", json={"event_url": EVENT_URL})
    assert again.status_code == 409

    mine = client.get("/api/events/submissions/mine").get_json()["submissions"]
    assert [s["status"] for s in mine] == ["pending"]


def test_waiting_limit_per_player(client, env):
    _login(client)
    for i in range(3):
        assert client.post("/api/events/submissions", json={"event_url": f"https://sorcerytcg.com/events/e{i}"}).status_code == 201
    resp = client.post("/api/events/submissions", json={"event_url": "https://sorcerytcg.com/events/e9"})
    assert resp.status_code == 429


def test_only_admins_list_and_approve(client, env):
    _login(client)
    client.post("/api/events/submissions", json={"event_url": EVENT_URL})
    assert client.get("/api/events/submissions").status_code == 403
    assert client.post("/api/events/submissions/1/approve").status_code == 403


def test_preview_queues_admin_dm(app, env, monkeypatch):
    from repositories.event_submissions import EventSubmissionRepository
    import services.curiosa as curiosa_module

    class FakeCuriosa:
        def fetch_event_deck_ids(self, url, with_decks=True, on_progress=None):
            return {"event_name": "Columbus Weekly", "event_date": "2026-11-08", "event_id": "evt123",
                    "player_count": 12, "players": [], "match_history": []}

    monkeypatch.setattr(curiosa_module, "CuriosaService", FakeCuriosa)
    sub = EventSubmissionRepository().create(EVENT_URL, "evt123", "", "", "555000111", "Ruben", "discord")
    events_routes._run_submission_preview("job1", sub["id"])

    sub = EventSubmissionRepository().get(sub["id"])
    assert sub["player_count"] == 12
    dms = _dms(env["articles_db"])
    # Only the Discord-id admin can be DMed
    assert [d["recipient"] for d in dms] == ["123456789"]
    assert "Columbus Weekly" in dms[0]["body"]
    assert "tagged Local" in dms[0]["body"]
    assert dms[0]["article_id"] is None
    assert dms[0]["link_path"] == "/top-8?review=1"


def _snapshot_deck(i):
    return {"id": f"d{i}", "username": f"P{i}", "avatar": [], "spellbook": []}


class _Curiosa:
    def __init__(self, players, count, history=None):
        self._players = players
        self._count = count
        self._history = history or []

    def fetch_event_deck_ids(self, url, on_progress=None, with_decks=True):
        return {"event_name": "Columbus Weekly", "event_date": "2026-11-08", "event_id": "evt123",
                "top_cut_size": 4, "player_count": self._count, "players": self._players,
                "match_history": self._history, "errors": []}

    @staticmethod
    def get_event_id_from_url(url):
        return "evt123"


class _EventRepo:
    created, tagged = [], []

    def check_new_folder_name(self, title):
        return title, None

    def create_event(self, title, top8, bulk):
        _EventRepo.created.append(title)
        return {"success": True}

    def save_match_history(self, *a):
        pass

    def update_event_metadata(self, folder, **kw):
        if "tag" in kw:
            _EventRepo.tagged.append((folder, kw["tag"]))
        return {"success": True}


def _pending(repo):
    sub = repo.create(EVENT_URL, "evt123", "", "", "555000111", "Ruben", "discord")
    assert repo.claim_for_import(sub["id"], "Bruce", "Thanks!")
    return sub["id"]


@pytest.mark.parametrize("count,local", [(12, True), (16, False), (40, False)])
def test_approve_with_decks_goes_on_top8_and_tags_local(app, env, monkeypatch, count, local):
    from repositories.event_submissions import EventSubmissionRepository

    _EventRepo.created, _EventRepo.tagged = [], []
    monkeypatch.setattr(events_routes, "EventRepository", _EventRepo)
    players = [{"name": f"P{i}", "deck_id": f"d{i}", "standing": i, "deck": _snapshot_deck(i)} for i in range(1, 6)]
    repo = EventSubmissionRepository()
    sid = _pending(repo)

    result = events_routes.approve_submission(sid, curiosa=_Curiosa(players, count))

    assert result["success"]
    assert _EventRepo.created == ["Columbus Weekly"]
    assert bool(_EventRepo.tagged) is local
    sub = repo.get(sid)
    assert sub["status"] == "approved"
    dm = _dms(env["articles_db"])[-1]
    assert dm["recipient"] == "555000111"
    assert "added to the Top 8 page" in dm["body"]
    assert ("tagged Local" in dm["body"]) is local
    assert "Thanks!" in dm["body"]


def test_approve_without_decks_adds_profile_placings_only(app, env, monkeypatch):
    from repositories.event_submissions import EventSubmissionRepository
    from repositories.paper_links import PaperLinkRepository

    _EventRepo.created = []
    monkeypatch.setattr(events_routes, "EventRepository", _EventRepo)
    history = [{"registration_id": f"r{i}", "display_name": f"P{i}", "username": f"p{i}", "standing": i,
                "wins": 3, "losses": 1, "draws": 0} for i in range(1, 9)]
    repo = EventSubmissionRepository()
    sid = _pending(repo)

    result = events_routes.approve_submission(sid, curiosa=_Curiosa([], 8, history))

    assert result["success"] and result["badges_only"]
    assert _EventRepo.created == []
    saved = PaperLinkRepository().get_badge_only_events()
    assert [e["event_id"] for e in saved] == ["evt123"]
    assert "profiles" in _dms(env["articles_db"])[-1]["body"]


def test_failed_import_can_be_retried_and_does_not_dm_player(app, env, monkeypatch):
    from repositories.event_submissions import EventSubmissionRepository

    monkeypatch.setattr(events_routes, "EventRepository", _EventRepo)
    repo = EventSubmissionRepository()
    sid = _pending(repo)

    result = events_routes.approve_submission(sid, curiosa=_Curiosa([], 0, []))

    assert not result["success"]
    assert repo.get(sid)["status"] == "failed"
    assert _dms(env["articles_db"]) == [] if env["articles_db"].exists() else True
    assert repo.claim_for_import(sid, "Bruce", "")


def test_reject_tells_the_player_with_note(client, env):
    _login(client).post("/api/events/submissions", json={"event_url": EVENT_URL})
    with client.session_transaction() as sess:
        sess["user_id"] = "admin_user_1"
    resp = client.post("/api/events/submissions/1/reject", json={"note": "Duplicate of last week"})
    assert resp.status_code == 200
    dm = _dms(env["articles_db"])[-1]
    assert dm["recipient"] == "555000111"
    assert "not added" in dm["body"] and "Duplicate of last week" in dm["body"]
    # Can't approve after a reject
    assert client.post("/api/events/submissions/1/approve").status_code == 409


def test_google_submitter_gets_no_dm(client, env):
    _login(client, user_id="998877", provider="google").post("/api/events/submissions", json={"event_url": EVENT_URL})
    with client.session_transaction() as sess:
        sess["user_id"] = "admin_user_1"
    client.post("/api/events/submissions/1/reject", json={})
    dms = _dms(env["articles_db"]) if env["articles_db"].exists() else []
    assert all(d["recipient"] != "998877" for d in dms)


# -- Deck links + event page (events that only collect the top lists) -------

class _LinkCuriosa(_Curiosa):
    batches = []

    def fetch_decks_batch(self, urls):
        _LinkCuriosa.batches.append(list(urls))
        return [_snapshot_deck(i) for i in range(1, len(urls) + 1)], []


@pytest.mark.parametrize("count,local", [(30, False), (12, True)])
def test_submission_with_deck_links_uses_event_page_for_size(app, env, monkeypatch, count, local):
    from repositories.event_submissions import EventSubmissionRepository

    _EventRepo.created, _EventRepo.tagged = [], []
    sizes = []
    orig = _EventRepo.update_event_metadata

    def update(self, folder, **kw):
        if "attendance" in kw:
            sizes.append(kw["attendance"])
        return orig(self, folder, **kw)

    monkeypatch.setattr(_EventRepo, "update_event_metadata", update)
    monkeypatch.setattr(events_routes, "EventRepository", _EventRepo)
    links = [f"https://curiosa.io/decks/top{i}" for i in range(1, 5)]
    repo = EventSubmissionRepository()
    sub = repo.create(EVENT_URL, "evt123", "", "", "555000111", "Ruben", "discord", deck_urls=links)
    assert repo.get(sub["id"])["deck_urls"] == links
    repo.claim_for_import(sub["id"], "Bruce", "")
    _LinkCuriosa.batches = []

    # The event page has players but no deck lists; the links carry the decks
    result = events_routes.approve_submission(sub["id"], curiosa=_LinkCuriosa([], count))

    assert result["success"] and not result.get("badges_only")
    assert _LinkCuriosa.batches == [links]
    assert _EventRepo.created == ["Columbus Weekly"]
    assert sizes == [count]
    assert bool(_EventRepo.tagged) is local
    assert repo.get(sub["id"])["player_count"] == count


def test_submit_accepts_deck_links_and_rejects_other_sites(client, env):
    _login(client)
    bad = client.post("/api/events/submissions", json={"event_url": EVENT_URL, "deck_urls": ["https://evil.example/x"]})
    assert bad.status_code == 400
    ok = client.post("/api/events/submissions", json={
        "event_url": EVENT_URL, "deck_urls": "https://curiosa.io/decks/a\n\nhttps://curiosa.io/decks/b"})
    assert ok.status_code == 201
    assert ok.get_json()["submission"]["deck_links"] == 2


def test_manual_event_reads_size_from_event_page(app, env, monkeypatch, tmp_path):
    from repositories.events import EventRepository
    import services.curiosa as curiosa_module

    events_dir = tmp_path / "events"
    events_dir.mkdir()
    monkeypatch.setattr(events_routes, "EventRepository", lambda: EventRepository(events_dir))

    class Fake(_LinkCuriosa):
        def __init__(self):
            super().__init__([], 30, [{"registration_id": "r1", "display_name": "P1", "standing": 1}])

        def _rate_limit(self):
            pass

    monkeypatch.setattr(curiosa_module, "CuriosaService", Fake)
    links = [f"https://curiosa.io/decks/top{i}" for i in range(1, 5)]
    events_routes._run_event_creation("job-m", "Dayton Open", links, [], EVENT_URL)

    event = next(e for e in EventRepository(events_dir).get_all_events() if e["folder"] == "Dayton Open")
    assert event["player_count"] == 4      # decks on the page
    assert event["attendance"] == 30       # people who played
    assert event["tag"] is None            # 16+ is not Local
    assert event["event_date"] == "2026-11-08"
