"""Event order shared by the Top 8 page and Deck Rec's "Newest First"."""

import json

from repositories.events import EventRepository


def _make(tmp_path, *folders):
    for name in folders:
        (tmp_path / name).mkdir()
    return EventRepository(events_dir=tmp_path)


def test_newest_date_first_undated_last(tmp_path):
    repo = _make(tmp_path, "Cold Foil Heros 3 30 2026", "Ascanrask III 2026 4 4", "OchoaDecklists")
    ranks = repo.get_event_ranks()
    assert ranks == {"Ascanrask III 2026 4 4": 0, "Cold Foil Heros 3 30 2026": 1, "OchoaDecklists": 2}


def test_admin_order_and_date_override_win(tmp_path):
    repo = _make(tmp_path, "Cold Foil Heros 3 30 2026", "Ascanrask III 2026 4 4", "OchoaDecklists")
    (tmp_path / "_event_metadata.json").write_text(json.dumps({"OchoaDecklists": {"event_date": "2026-06-01"}}))
    assert repo.get_event_dates()["OchoaDecklists"] == "2026-06-01"
    assert repo.get_event_ranks()["OchoaDecklists"] == 0

    (tmp_path / "_event_order.json").write_text(json.dumps(["Cold Foil Heros 3 30 2026", "OchoaDecklists"]))
    ranks = repo.get_event_ranks()
    assert ranks["Cold Foil Heros 3 30 2026"] == 0
    assert ranks["OchoaDecklists"] == 1
    assert ranks["Ascanrask III 2026 4 4"] == 2
