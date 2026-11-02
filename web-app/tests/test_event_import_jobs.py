"""Event import jobs: failed decks are skipped, dead jobs report, reruns resume."""

import json
import os
import time

import pytest

import routes.api.events as events_routes


EVENT_URL = "https://sorcerytcg.com/events/evt123"


@pytest.fixture()
def jobs_dir(tmp_path, monkeypatch):
    path = tmp_path / "jobs"
    path.mkdir()
    monkeypatch.setattr(events_routes, "_JOBS_DIR", str(path))
    return path


def _players(n):
    return [{"name": f"P{i}", "deck_id": f"d{i}", "standing": i} for i in range(1, n + 1)]


class FakeCuriosa:
    """Stands in for CuriosaService; decks listed in `fail` come back None."""

    fetched = []
    fail = set()
    players = _players(5)

    def fetch_event_deck_ids(self, event_url, on_progress=None):
        return {
            "event_name": "Test Import",
            "event_date": None,
            "event_id": "evt123",
            "top_cut_size": 2,
            "players": list(self.players),
            "match_history": [],
            "errors": [],
        }

    @staticmethod
    def get_event_id_from_url(url):
        return "evt123"

    def fetch_deck_by_id(self, deck_id):
        FakeCuriosa.fetched.append(deck_id)
        if deck_id in FakeCuriosa.fail:
            return None
        return {"id": deck_id, "username": deck_id, "avatar": [], "spellbook": []}


class FakeRepo:
    created = []

    def check_new_folder_name(self, title):
        return title, None

    def create_event(self, title, top8, bulk):
        FakeRepo.created.append((title, top8, bulk))
        return {"success": True}


@pytest.fixture()
def fakes(monkeypatch):
    import services.curiosa as curiosa_module

    FakeCuriosa.fetched = []
    FakeCuriosa.fail = set()
    FakeRepo.created = []
    monkeypatch.setattr(curiosa_module, "CuriosaService", FakeCuriosa)
    monkeypatch.setattr(events_routes, "EventRepository", FakeRepo)
    # No heartbeat thread lingering past the test
    monkeypatch.setattr(events_routes, "_JOB_HEARTBEAT_SECONDS", 3600)


def test_a_deck_that_fails_is_skipped_and_reported(jobs_dir, fakes):
    FakeCuriosa.fail = {"d3"}

    events_routes._run_event_import("job1", "", EVENT_URL)

    job = events_routes._read_job("job1")
    assert job["status"] == "completed"
    title, top8, bulk = FakeRepo.created[0]
    assert [d["id"] for d in top8] == ["d1", "d2"]
    assert [d["id"] for d in bulk] == ["d4", "d5"]
    assert any("deck 3" in w and "P3" in w for w in job["result"]["warnings"])


def test_rerun_after_a_crash_only_fetches_the_missing_decks(jobs_dir, fakes, monkeypatch):
    # First run dies on deck 3 the way a killed worker would.
    original = FakeCuriosa.fetch_deck_by_id

    def dies_on_d3(self, deck_id):
        if deck_id == "d3":
            raise SystemExit("worker killed")
        return original(self, deck_id)

    monkeypatch.setattr(FakeCuriosa, "fetch_deck_by_id", dies_on_d3)
    with pytest.raises(SystemExit):
        events_routes._run_event_import("job1", "", EVENT_URL)
    assert events_routes._read_job("job1")["progress"] == "Fetching deck 3/5..."

    monkeypatch.setattr(FakeCuriosa, "fetch_deck_by_id", original)
    FakeCuriosa.fetched = []
    events_routes._run_event_import("job2", "", EVENT_URL)

    assert FakeCuriosa.fetched == ["d3", "d4", "d5"]
    assert events_routes._read_job("job2")["status"] == "completed"
    # A finished import leaves no cache behind
    assert not os.path.exists(events_routes._import_cache_path("evt123"))


def test_poll_reports_a_job_whose_worker_died(admin_session, jobs_dir):
    events_routes._write_job("dead", {"status": "processing", "progress": "Fetching deck 13/38..."})
    path = events_routes._job_path("dead")
    with open(path) as f:
        job = json.load(f)
    job["pid"] = 2 ** 22 + 12345  # beyond pid_max, so never a live process
    with open(path, "w") as f:
        json.dump(job, f)

    resp = admin_session.get("/api/events/jobs/dead")
    body = resp.get_json()
    assert body["status"] == "failed"
    assert "restarted" in body["result"]["error"]
    assert body["result"]["stopped_at"] == "Fetching deck 13/38..."
    assert events_routes._read_job("dead") is None


def test_poll_reports_a_job_that_went_quiet(admin_session, jobs_dir):
    events_routes._write_job("quiet", {"status": "processing", "progress": "Refreshing decks..."})
    old = time.time() - events_routes._JOB_STALE_SECONDS - 10
    os.utime(events_routes._job_path("quiet"), (old, old))

    body = admin_session.get("/api/events/jobs/quiet").get_json()
    assert body["status"] == "failed"


def test_poll_keeps_a_live_job_running(admin_session, jobs_dir):
    events_routes._write_job("live", {"status": "processing", "progress": "Fetching deck 2/38..."})

    body = admin_session.get("/api/events/jobs/live").get_json()
    assert body == {"status": "processing", "progress": "Fetching deck 2/38..."}


def test_heartbeat_keeps_a_long_quiet_job_fresh(jobs_dir, monkeypatch):
    monkeypatch.setattr(events_routes, "_JOB_HEARTBEAT_SECONDS", 0.05)
    events_routes._write_job("slow", {"status": "processing", "progress": "Refreshing decks..."})
    old = time.time() - 1000
    os.utime(events_routes._job_path("slow"), (old, old))

    @events_routes._job_worker
    def slow_job(job_id):
        time.sleep(0.3)

    slow_job("slow")
    assert time.time() - os.path.getmtime(events_routes._job_path("slow")) < 5


def test_jobs_run_in_their_own_process(jobs_dir):
    """A job outlives the gunicorn worker that started it."""
    events_routes._write_job("proc", {"status": "processing", "progress": "Refreshing decks..."})

    events_routes._start_job(events_routes._run_event_refresh, ("proc", "No Such Event"))

    deadline = time.time() + 60
    job = events_routes._read_job("proc")
    while job["status"] == "processing" and time.time() < deadline:
        time.sleep(0.2)
        job = events_routes._read_job("proc")
    assert job["status"] == "failed"
    assert job["result"]["error"] == "Event not found"
    assert job["pid"] != os.getpid()


def test_every_job_started_by_a_route_can_be_run_by_name():
    import inspect
    import re

    source = inspect.getsource(events_routes)
    started = set(re.findall(r"    _start_job\((_run_\w+),", source))
    assert started == set(events_routes.JOB_TARGETS)
