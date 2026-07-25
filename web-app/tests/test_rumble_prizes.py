"""Tests for rumble prize ordering / reorder behavior."""

import sqlite3

import pytest

from repositories.rumble_repo import RumbleRepository


@pytest.fixture()
def rumble_db(tmp_path):
    """Create a temporary rumble DB with the prizes table."""
    db_path = tmp_path / "rumble.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE rumble_prizes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            cost INTEGER NOT NULL DEFAULT 0,
            stock INTEGER,
            description TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()
    return db_path


class TestPrizeReorder:
    def test_swap_moves_prizes_with_duplicate_sort_order(self, rumble_db):
        """Regression: arrows did nothing when all prizes had sort_order=0."""
        repo = RumbleRepository(db_path=rumble_db)
        conn = sqlite3.connect(str(rumble_db))
        conn.executemany(
            "INSERT INTO rumble_prizes (name, cost, sort_order) VALUES (?, ?, ?)",
            [("Alpha", 1, 0), ("Beta", 2, 0), ("Gamma", 3, 0)],
        )
        conn.commit()
        conn.close()

        prizes = repo.get_prizes()
        assert [p["name"] for p in prizes] == ["Alpha", "Beta", "Gamma"]

        # Move Beta up (swap with Alpha) — previously a no-op when both were 0
        assert repo.swap_prize_order(prizes[1]["id"], prizes[0]["id"]) is True

        reordered = repo.get_prizes()
        assert [p["name"] for p in reordered] == ["Beta", "Alpha", "Gamma"]
        assert [p["sort_order"] for p in reordered] == [0, 1, 2]

    def test_swap_moves_prizes_with_distinct_sort_order(self, rumble_db):
        repo = RumbleRepository(db_path=rumble_db)
        id_a = repo.add_prize("First", cost=1)
        id_b = repo.add_prize("Second", cost=2)
        id_c = repo.add_prize("Third", cost=3)

        assert [p["name"] for p in repo.get_prizes()] == ["First", "Second", "Third"]

        assert repo.swap_prize_order(id_b, id_c) is True
        assert [p["name"] for p in repo.get_prizes()] == ["First", "Third", "Second"]
        assert [p["id"] for p in repo.get_prizes()] == [id_a, id_c, id_b]

    def test_add_prize_assigns_unique_sort_order(self, rumble_db):
        repo = RumbleRepository(db_path=rumble_db)
        repo.add_prize("A")
        repo.add_prize("B")
        repo.add_prize("C")

        prizes = repo.get_prizes()
        orders = [p["sort_order"] for p in prizes]
        assert orders == [0, 1, 2]
        assert len(set(orders)) == 3

    def test_swap_missing_prize_returns_false(self, rumble_db):
        repo = RumbleRepository(db_path=rumble_db)
        id_a = repo.add_prize("Only")
        assert repo.swap_prize_order(id_a, 99999) is False
