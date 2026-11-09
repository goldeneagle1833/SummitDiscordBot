"""sorcerytcg.com event imports when the player snapshot has no sourceDeck.

Since Nov 2026 event.playerSnapshot answers with the frozen event list
({name, format, decklist, frozen}) and no longer names the deck it came from,
so the importer builds each deck straight from the snapshot.
"""

import json

import pytest

import routes.api.events as events_routes
from repositories.events import EventRepository
from services.curiosa import CuriosaService, EVENT_SNAPSHOT_DECK_SOURCE

EVENT_URL = "https://sorcerytcg.com/events/evt123"


def _entry(board, name, card_type="Minion", quantity=1, elements=("Fire",)):
    return {
        "board": board,
        "quantity": quantity,
        "card": {
            "name": name,
            "engine": {"type": card_type, "rarity": "Ordinary", "cost": 2,
                       "elements": list(elements), "category": card_type},
        },
        "printing": {"meta": {"image": f"https://img/{name}.png"}},
    }


def _snapshot(deck_name, avatar):
    return {
        "name": deck_name,
        "format": "Constructed",
        "frozen": True,
        "decklist": [
            _entry("Avatar", avatar, "Avatar", elements=("None",)),
            _entry("Main", "Poison Nova", "Magic", quantity=2),
            _entry("Main", "Arid Desert", "Site"),
            _entry("Collection", "Gift of the Serpent", "Magic"),
        ],
    }


def _player(reg_id, username, display, score):
    return {
        "id": reg_id,
        "status": "Ready",
        "user": {"username": username, "displayname": display},
        "seats": [{
            "round": {"number": 1, "phase": {"structure": "Swiss"}},
            "result": {"score": score, "result": "Win" if score else "Loss"},
            "pairing": {"seats": []},
        }],
    }


@pytest.fixture()
def service(monkeypatch):
    svc = CuriosaService()
    event = {
        "title": "Trials",
        "startsAt": "2026-11-07T17:00:00.000Z",
        "topcut": {"size": 8},
        "players": [
            _player("reg-b", "bob", "Bob B", 0),
            _player("reg-a", "alice", "Alice A", 3),
        ],
    }
    snapshots = {
        "reg-a": _snapshot("Thirst Trap", "Avatar of Water"),
        "reg-b": _snapshot("fire path", "Pathfinder"),
    }
    monkeypatch.setattr(svc, "_fetch_event_trpc", lambda event_id: event)
    monkeypatch.setattr(svc, "_fetch_page_html", lambda url: "")
    monkeypatch.setattr(
        svc, "_fetch_player_snapshots_batch",
        lambda event_id, players: [snapshots.get(p["id"]) for p in players],
    )
    svc.snapshots = snapshots
    return svc


def test_decks_are_built_from_the_snapshot_list(service):
    result = service.fetch_event_deck_ids(EVENT_URL)

    assert result["errors"] == []
    assert [p["name"] for p in result["players"]] == ["Alice A", "Bob B"]
    alice = result["players"][0]
    assert alice["deck_id"] == "reg-a"
    deck = alice["deck"]
    assert deck["id"] == "reg-a"
    assert deck["name"] == "Thirst Trap"
    assert deck["username"] == "alice"
    assert deck["source"] == EVENT_SNAPSHOT_DECK_SOURCE
    assert [c["name"] for c in deck["avatar"]] == ["Avatar of Water"]
    assert [(c["name"], c["quantity"]) for c in deck["spellbook"]] == [("Poison Nova", 2)]
    assert [c["name"] for c in deck["atlas"]] == ["Arid Desert"]
    assert [c["name"] for c in deck["sideboard"]] == ["Gift of the Serpent"]
    # The pairings link each player to the same deck id
    by_reg = {p["registration_id"]: p["deck_id"] for p in result["match_history"]}
    assert by_reg == {"reg-a": "reg-a", "reg-b": "reg-b"}


def test_a_snapshot_that_still_names_its_source_deck_keeps_the_old_path(service):
    service.snapshots["reg-a"] = {"sourceDeck": {"id": "real-deck-1"}}

    players = {p["name"]: p for p in service.fetch_event_deck_ids(EVENT_URL)["players"]}

    assert players["Alice A"]["deck_id"] == "real-deck-1"
    assert "deck" not in players["Alice A"]
    assert players["Bob B"]["deck"]["name"] == "fire path"


def test_a_player_with_no_list_is_reported(service):
    service.snapshots["reg-b"] = {"name": "x", "decklist": []}

    result = service.fetch_event_deck_ids(EVENT_URL)

    assert [p["name"] for p in result["players"]] == ["Alice A"]
    assert result["errors"] == ["No deck list found for Bob B"]


def test_badge_only_discovery_does_not_touch_snapshots(service, monkeypatch):
    def boom(*args):
        raise AssertionError("snapshots fetched")

    monkeypatch.setattr(service, "_fetch_player_snapshots_batch", boom)
    result = service.fetch_event_deck_ids(EVENT_URL, with_decks=False)
    assert result["players"] == []
    assert len(result["match_history"]) == 2


class _FakeCuriosa:
    fetched = []

    def __init__(self):
        pass

    def fetch_event_deck_ids(self, event_url, on_progress=None):
        deck = {"id": "reg-a", "name": "Thirst Trap", "username": "alice",
                "avatar": [{"name": "Avatar of Water"}], "spellbook": [],
                "source": EVENT_SNAPSHOT_DECK_SOURCE}
        return {
            "event_name": "Trials", "event_date": None, "event_id": "evt123",
            "top_cut_size": 8,
            "players": [{"name": "Alice A", "deck_id": "reg-a", "standing": 1, "deck": deck}],
            "match_history": [], "errors": [],
        }

    @staticmethod
    def get_event_id_from_url(url):
        return "evt123"

    def fetch_deck_by_id(self, deck_id):
        _FakeCuriosa.fetched.append(deck_id)
        return None


class _FakeRepo:
    created = []

    def check_new_folder_name(self, title):
        return title, None

    def create_event(self, title, top8, bulk):
        _FakeRepo.created.append((title, top8, bulk))
        return {"success": True}


def test_import_job_uses_snapshot_decks_without_fetching(tmp_path, monkeypatch):
    import services.curiosa as curiosa_module

    jobs = tmp_path / "jobs"
    jobs.mkdir()
    monkeypatch.setattr(events_routes, "_JOBS_DIR", str(jobs))
    monkeypatch.setattr(events_routes, "_JOB_HEARTBEAT_SECONDS", 3600)
    monkeypatch.setattr(curiosa_module, "CuriosaService", _FakeCuriosa)
    monkeypatch.setattr(events_routes, "EventRepository", _FakeRepo)
    _FakeCuriosa.fetched = []
    _FakeRepo.created = []

    events_routes._run_event_import("job1", "", EVENT_URL)

    assert events_routes._read_job("job1")["status"] == "completed"
    assert _FakeCuriosa.fetched == []
    title, top8, bulk = _FakeRepo.created[0]
    assert [d["name"] for d in top8] == ["Thirst Trap"]


def test_refresh_leaves_snapshot_decks_alone(tmp_path):
    snap = {"id": "reg-a", "name": "Snap", "source": EVENT_SNAPSHOT_DECK_SOURCE}
    real = {"id": "real-1", "name": "Old"}
    path = tmp_path / "top8.json"
    path.write_text(json.dumps([snap, real]))
    asked = []

    class Svc:
        def fetch_decks_by_ids(self, ids):
            asked.extend(ids)
            return [{"id": "real-1", "name": "New"}], []

    count, errors = EventRepository(tmp_path)._refresh_json_file(path, Svc(), "top 8")

    assert asked == ["real-1"]
    assert count == 1 and errors == []
    assert [d["name"] for d in json.loads(path.read_text())] == ["Snap", "New"]


def test_reimported_history_keeps_the_real_deck_ids(tmp_path):
    (tmp_path / "Trials").mkdir()
    repo = EventRepository(tmp_path)
    old = {"players": [
        {"registration_id": "reg-a", "deck_id": "real-a", "matches": []},
        {"registration_id": "reg-b", "deck_id": "real-b", "matches": []},
    ]}
    assert repo.save_match_history("Trials", old)["success"]

    new = {"players": [
        {"registration_id": "reg-a", "deck_id": "reg-a", "matches": [
            {"opponent": {"registration_id": "reg-b", "deck_id": "reg-b"}},
        ]},
        {"registration_id": "reg-c", "deck_id": "reg-c", "matches": []},
    ]}
    assert repo.save_match_history("Trials", new)["success"]

    saved = repo._load_match_history("Trials")
    assert saved["players"][0]["deck_id"] == "real-a"
    assert saved["players"][0]["matches"][0]["opponent"]["deck_id"] == "real-b"
    assert saved["players"][1]["deck_id"] == "reg-c"
