import sqlite3

from cogs.lfg import persistent_confirm


def test_pending_confirmation_round_trips_avatar_names(tmp_path, monkeypatch):
    database_path = tmp_path / "pending-confirmations.db"
    monkeypatch.setattr(persistent_confirm, "DB_PATH", str(database_path))

    persistent_confirm.ensure_pending_confirmations_table()
    confirmation_id = persistent_confirm.save_pending_confirmation(
        {
            "reporter_id": 1,
            "opponent_id": 2,
            "winner_id": 2,
            "winner_global": "Winner",
            "loser_id": 1,
            "loser_global": "Loser",
            "is_winner": True,
            "winner_avatar": "Avatar of Earth",
            "loser_avatar": "Avatar of Fire",
        }
    )

    saved = persistent_confirm.load_pending_confirmation(confirmation_id)

    assert saved["winner_avatar"] == "Avatar of Earth"
    assert saved["loser_avatar"] == "Avatar of Fire"


def test_pending_confirmation_migration_adds_avatar_columns(tmp_path, monkeypatch):
    database_path = tmp_path / "old-pending-confirmations.db"
    connection = sqlite3.connect(database_path)
    connection.execute(
        "CREATE TABLE pending_confirmations (id INTEGER PRIMARY KEY, confirmer_comment TEXT)"
    )
    connection.commit()
    connection.close()
    monkeypatch.setattr(persistent_confirm, "DB_PATH", str(database_path))

    persistent_confirm.ensure_pending_confirmations_table()

    connection = sqlite3.connect(database_path)
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(pending_confirmations)").fetchall()
    }
    connection.close()
    assert {"winner_avatar", "loser_avatar"}.issubset(columns)
