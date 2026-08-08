"""Tests for paper avatar-specific event Elo."""

import datetime
import sqlite3

from services import paper_elo
from services import avatar_event_elo
from utils import avatar_elo
from repositories.elo import EloRepository


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


def test_player_event_elo_returns_every_avatar_with_overall_ladder_rank(tmp_path):
    elo_path = tmp_path / "elo.db"
    conn = sqlite3.connect(elo_path)
    conn.executescript("""
        CREATE TABLE events (
            event_id INTEGER PRIMARY KEY,
            event_name TEXT,
            avatar_specific BOOLEAN
        );
        CREATE TABLE event_avatar_standings (
            event_id INTEGER,
            source TEXT,
            user_id TEXT,
            user_display_name TEXT,
            avatar_name TEXT COLLATE NOCASE,
            event_elo INTEGER
        );
    """)
    conn.execute("INSERT INTO events VALUES (4, 'Avatar League', 1)")
    conn.executemany(
        "INSERT INTO event_avatar_standings VALUES (4, 'online', ?, ?, ?, ?)",
        [
            ("2", "Bob", "Battlemage", 1660),
            ("1", "Alice", "Impostor", 1640),
            ("3", "Cara", "Persecutor", 1600),
            ("1", "Alice", "Persecutor", 1530),
        ],
    )
    conn.commit()
    conn.close()

    result = EloRepository(elo_path).get_player_event_elo("1", 4)

    assert result == {
        "avatar_specific": True,
        "event_name": "Avatar League",
        "avatar_elos": [
            {"avatar": "Impostor", "elo": 1640, "rank": 2},
            {"avatar": "Persecutor", "elo": 1530, "rank": 4},
        ],
    }


def test_atomic_paper_avatar_match_uses_one_pre_match_snapshot(tmp_path, monkeypatch):
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
        CREATE TABLE paper_standings (
            user_id TEXT PRIMARY KEY,
            user_display_name TEXT,
            paper_elo INTEGER,
            paper_event_elo INTEGER
        );
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
        [("Impostor",), ("Battlemage",)],
    )
    conn.executemany(
        "INSERT INTO paper_standings VALUES (?, ?, ?, 1500)",
        [("1", "Alice", 1600), ("2", "Bob", 1400)],
    )
    conn.commit()
    conn.close()

    winner, loser = paper_elo.update_paper_match_elos(
        "1", "Alice", "2", "Bob", "Impostor", "Battlemage"
    )

    assert winner[:4] == (1608, 8, 1508, 8)
    assert loser[:4] == (1392, -8, 1492, -8)
    conn = sqlite3.connect(elo_path)
    stored = conn.execute(
        "SELECT user_id, paper_elo FROM paper_standings ORDER BY user_id"
    ).fetchall()
    conn.close()
    assert stored == [("1", 1608), ("2", 1392)]


def test_avatar_paper_replay_rebuilds_the_shared_ladder(tmp_path, monkeypatch):
    elo_path = tmp_path / "elo.db"
    match_path = tmp_path / "matches.db"
    monkeypatch.setattr(avatar_event_elo, "ELO_DB_PATH", elo_path)
    monkeypatch.setattr(avatar_event_elo, "MATCH_RECORDS_DB_PATH", match_path)
    start = datetime.datetime.now() - datetime.timedelta(days=1)

    conn = sqlite3.connect(elo_path)
    conn.executescript("""
        CREATE TABLE events (
            event_id INTEGER PRIMARY KEY,
            start_date TEXT,
            end_date TEXT,
            avatar_specific BOOLEAN
        );
        CREATE TABLE event_avatar_standings (
            event_id INTEGER,
            source TEXT,
            user_id TEXT,
            user_display_name TEXT,
            avatar_name TEXT,
            event_elo INTEGER,
            PRIMARY KEY (event_id, source, user_id, avatar_name)
        );
    """)
    conn.execute(
        "INSERT INTO events VALUES (1, ?, NULL, 1)", (start.isoformat(),)
    )
    conn.execute(
        "INSERT INTO event_avatar_standings VALUES (1, 'paper', 'old', 'Old', 'Impostor', 999)"
    )
    conn.commit()
    conn.close()

    conn = sqlite3.connect(match_path)
    conn.execute("""CREATE TABLE match_reports_web (
        winner_id TEXT, winner_display_name TEXT, winner_avatar TEXT,
        losser_id TEXT, losser_display_name TEXT, loser_avatar TEXT,
        timestamp TEXT, match_type TEXT,
        winner_elo_change INTEGER, loser_elo_change INTEGER,
        winner_elo_multiplier REAL DEFAULT 1.0,
        loser_elo_multiplier REAL DEFAULT 1.0
    )""")
    conn.execute("""CREATE TABLE admin_audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, target_id TEXT,
        target_name TEXT, action TEXT, new_state TEXT
    )""")
    conn.executemany(
        "INSERT INTO match_reports_web VALUES (?, ?, ?, ?, ?, ?, ?, 'ranked', 8, -8, ?, ?)",
        [
            ("1", "Alice", "Impostor", "2", "Bob", "Battlemage", (start + datetime.timedelta(hours=1)).isoformat(), 2.0, 0.5),
            ("2", "Bob", "Battlemage", "1", "Alice", "Persecutor", (start + datetime.timedelta(hours=2)).isoformat(), 1.0, 1.0),
        ],
    )
    conn.execute(
        """INSERT INTO admin_audit_log
           (timestamp, target_id, target_name, action, new_state)
           VALUES (?, '2', 'Bob', 'web_reset_elo', ?)""",
        (
            (start + datetime.timedelta(hours=3)).isoformat(),
            '{"elo": 1700, "source": "paper", "avatar": "Battlemage"}',
        ),
    )
    conn.commit()
    conn.close()

    assert avatar_event_elo.recalculate_avatar_event_standings(1, "paper") == 2
    conn = sqlite3.connect(elo_path)
    rows = conn.execute(
        "SELECT user_id, avatar_name, event_elo FROM event_avatar_standings ORDER BY user_id, avatar_name"
    ).fetchall()
    conn.close()
    assert rows == [
        ("1", "Impostor", 1516),
        ("1", "Persecutor", 1492),
        ("2", "Battlemage", 1700),
    ]
