"""Peak activity hours are bucketed in Eastern time, daylight saving included."""
import time

import pytest

from services.activity_hours import activity_by_hour, eastern_slot


@pytest.fixture()
def utc_server(monkeypatch):
    """Pretend the server clock runs on UTC."""
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_summer_slot_is_four_hours_behind_utc(utc_server):
    # Tue Oct 13 2026, 01:00 UTC is Mon Oct 12, 9 PM EDT
    assert eastern_slot("2026-10-13 01") == ("2026-10-12", 1, 21)


def test_winter_slot_is_five_hours_behind_utc(utc_server):
    # Tue Jan 13 2026, 01:00 UTC is Mon Jan 12, 8 PM EST
    assert eastern_slot("2026-01-13 01") == ("2026-01-12", 1, 20)


def test_rows_and_grid_combine_slots(utc_server):
    rows, grid = activity_by_hour([
        ("2026-10-13 01", 3),
        ("2026-10-13 01", 2),  # same slot from another table
        ("2026-10-13 15", 4),
        (None, 9),
        ("bad", 1),
    ])
    assert rows == [["2026-10-12", 21, 5], ["2026-10-13", 11, 4]]
    assert grid[1][21] == 5  # Monday 9 PM
    assert grid[2][11] == 4  # Tuesday 11 AM
    assert sum(map(sum, grid)) == 9
