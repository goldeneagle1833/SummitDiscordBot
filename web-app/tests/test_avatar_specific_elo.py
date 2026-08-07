"""Tests for paper avatar-specific event Elo."""

import datetime
import sqlite3

from services import paper_elo
from utils import avatar_elo


def test_paper_avatar_event_keeps_one_lifetime_rating_and_multiple_avatar_ratings(
    tmp_path, monkeypatch
):
    elo_path = tmp_path / "elo.db"
    monkeypatch.setattr(paper_elo, "ELO_DB_PATH", elo_path)
    monkeypatch.setattr(avatar_elo, "ELO_DB_PATH", elo_path)

    conn = sqlite3.connect(elo_path)
    conn.executescript("""
        CREATE TABLE events (
            event_id INTEGER PRIMARY KEY,
            event_name TEXT,
            start_date TEXT,
            is_active BOOLEAN,
            avatar_specific BOOLEAN
        );
        CREATE TABLE card_catalog (name TEXT, card_type TEXT);
        CREATE TABLE event_avatar_standings (
            event_id INTEGER,
            source TEXT,
            user_id TEXT,
            user_display_name TEXT,
            avatar_name TEXT COLLATE NOCASE,
            event_elo INTEGER,
            PRIMARY KEY (event_id, source, user_id, avatar_name)
        );
    """)
    conn.execute(
        "INSERT INTO events VALUES (1, 'Avatar League', ?, 1, 1)",
        (datetime.datetime.now().isoformat(),),
    )
    conn.executemany(
        "INSERT INTO card_catalog VALUES (?, 'Avatar')",
        [("Impostor",), ("Persecutor",), ("Battlemage",)],
    )
    conn.commit()
    conn.close()

    paper_elo.update_paper_elo(
        "1", "Alice", True, "2", "Impostor", "Battlemage"
    )
    paper_elo.update_paper_elo(
        "2", "Bob", False, "1", "Battlemage", "Impostor"
    )
    paper_elo.update_paper_elo(
        "1", "Alice", True, "2", "Persecutor", "Battlemage"
    )
    paper_elo.update_paper_elo(
        "2", "Bob", False, "1", "Battlemage", "Persecutor"
    )

    conn = sqlite3.connect(elo_path)
    rows = conn.execute(
        """SELECT user_id, avatar_name, event_elo FROM event_avatar_standings
           ORDER BY user_id, avatar_name"""
    ).fetchall()
    alice_lifetime, alice_legacy_event = conn.execute(
        "SELECT paper_elo, paper_event_elo FROM paper_standings WHERE user_id = '1'"
    ).fetchone()
    conn.close()

    assert ("1", "Impostor", 1508) in rows
    assert ("1", "Persecutor", 1508) in rows
    assert alice_lifetime > 1516
    assert alice_legacy_event == 1500
