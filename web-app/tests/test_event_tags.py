"""Admin-set event type tags (Grand Contest / Cornerstone / Local) on Top 8 events."""

import json

from repositories.events import EventRepository


def _repo(tmp_path, name="Cold Foil Heros 3 30 2026"):
    folder = tmp_path / name
    folder.mkdir()
    (folder / "top8.json").write_text(json.dumps([{"username": "a", "avatar": []}]))
    return EventRepository(events_dir=tmp_path), name


def _event(repo, name):
    return next(e for e in repo.get_all_events() if e["folder"] == name)


def test_untagged_by_default(tmp_path):
    repo, name = _repo(tmp_path)
    assert _event(repo, name)["tag"] is None


def test_set_change_and_clear_tag(tmp_path):
    repo, name = _repo(tmp_path)
    assert repo.update_event_metadata(name, tag="Cornerstone")["success"]
    assert _event(repo, name)["tag"] == "Cornerstone"

    assert repo.update_event_metadata(name, tag="Grand Contest")["success"]
    assert _event(repo, name)["tag"] == "Grand Contest"

    # Saving other fields without a tag keeps it
    assert repo.update_event_metadata(name, rating=3)["success"]
    ev = _event(repo, name)
    assert ev["tag"] == "Grand Contest" and ev["rating"] == 3

    assert repo.update_event_metadata(name, tag="")["success"]
    assert _event(repo, name)["tag"] is None


def test_unknown_tag_rejected(tmp_path):
    repo, name = _repo(tmp_path)
    result = repo.update_event_metadata(name, tag="Regional")
    assert not result["success"]
    assert _event(repo, name)["tag"] is None
