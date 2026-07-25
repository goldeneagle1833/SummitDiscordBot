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
    def test_set_prize_order_reassigns_sort_values(self, rumble_db):
        repo = RumbleRepository(db_path=rumble_db)
        # Legacy rows that all share sort_order=0
        conn = sqlite3.connect(str(rumble_db))
        conn.executemany(
            "INSERT INTO rumble_prizes (name, cost, sort_order) VALUES (?, ?, ?)",
            [("Alpha", 1, 0), ("Beta", 2, 0), ("Gamma", 3, 0)],
        )
        conn.commit()
        conn.close()

        prizes = repo.get_prizes()
        ids = [p["id"] for p in prizes]
        # Move Beta to the front: Beta, Alpha, Gamma
        new_order = [ids[1], ids[0], ids[2]]
        assert repo.set_prize_order(new_order) is True

        reordered = repo.get_prizes()
        assert [p["name"] for p in reordered] == ["Beta", "Alpha", "Gamma"]
        assert [p["sort_order"] for p in reordered] == [0, 1, 2]

    def test_set_prize_order_rejects_unknown_id(self, rumble_db):
        repo = RumbleRepository(db_path=rumble_db)
        id_a = repo.add_prize("Only")
        assert repo.set_prize_order([id_a, 99999]) is False

    def test_swap_moves_prizes_with_duplicate_sort_order(self, rumble_db):
        """Legacy pairwise swap still works when all prizes had sort_order=0."""
        repo = RumbleRepository(db_path=rumble_db)
        conn = sqlite3.connect(str(rumble_db))
        conn.executemany(
            "INSERT INTO rumble_prizes (name, cost, sort_order) VALUES (?, ?, ?)",
            [("Alpha", 1, 0), ("Beta", 2, 0), ("Gamma", 3, 0)],
        )
        conn.commit()
        conn.close()

        prizes = repo.get_prizes()
        assert repo.swap_prize_order(prizes[1]["id"], prizes[0]["id"]) is True
        assert [p["name"] for p in repo.get_prizes()] == ["Beta", "Alpha", "Gamma"]

    def test_add_prize_assigns_unique_sort_order(self, rumble_db):
        repo = RumbleRepository(db_path=rumble_db)
        repo.add_prize("A")
        repo.add_prize("B")
        repo.add_prize("C")

        prizes = repo.get_prizes()
        orders = [p["sort_order"] for p in prizes]
        assert orders == [0, 1, 2]
        assert len(set(orders)) == 3
