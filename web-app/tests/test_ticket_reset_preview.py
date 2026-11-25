"""Checkout warning for late tickets: mirrors the bot's 1500 reset rules."""

import datetime
import sqlite3

import pytest

import webapp_config
from repositories.elo import EloRepository
from services.ticket_reset_preview import is_current_season_ticket, preview_ticket_reset

BUYER = "222222222222222222"
OTHER = "333333333333333333"
ROLE_S9 = "111111111111111119"
ROLE_S10 = "111111111111111110"


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / "elo.db"
    monkeypatch.setattr(webapp_config, "ELO_DB_PATH", path)
    conn = sqlite3.connect(path)
    conn.executescript(
        """CREATE TABLE events (event_id INTEGER PRIMARY KEY, event_name TEXT, start_date TEXT,
                                is_active INTEGER, elo_mode TEXT, scheduled_end_at INTEGER,
                                rating_system TEXT);
           CREATE TABLE event_avatar_standings (event_id INTEGER, user_id INTEGER, avatar TEXT,
                                user_display_name TEXT, event_elo INTEGER, games_played INTEGER,
                                last_played_at TEXT);
           CREATE TABLE season_ticket_roles (role_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                                status TEXT NOT NULL, event_id INTEGER, created_by TEXT,
                                created_at TEXT NOT NULL, activated_at TEXT);"""
    )
    conn.commit()
    conn.close()
    return path


def _season(path, days_in):
    start = (datetime.datetime.now() - datetime.timedelta(days=days_in)).isoformat()
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO events VALUES (9, 'Gothic Season 9', ?, 1, 'avatar', NULL, 'glicko2')", (start,))
    conn.commit()
    conn.close()


def _entry(path, user_id, avatar, elo, games):
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO event_avatar_standings VALUES (9, ?, ?, 'P', ?, ?, NULL)",
                 (int(user_id), avatar, elo, games))
    conn.commit()
    conn.close()


def _preview(path, user=BUYER):
    return preview_ticket_reset(user, elo_repo=EloRepository(path))


def test_grace_week_has_no_warning(db):
    _season(db, 3)
    _entry(db, BUYER, "Imposter", 1612, 10)
    result = _preview(db)
    assert not result["will_reset"] and result["reason"] == "grace"


def test_after_grace_lists_only_entries_above_1500(db):
    _season(db, 10)
    _entry(db, BUYER, "Imposter", 1612, 4)
    _entry(db, BUYER, "Witch", 1470, 2)
    _entry(db, OTHER, "Imposter", 1700, 9)
    result = _preview(db)
    assert result["will_reset"] and result["games"] == 6
    assert result["entries"] == [{"avatar": "Imposter", "from": 1612, "to": 1500}]
    assert result["event_name"] == "Gothic Season 9"


def test_two_or_fewer_games_no_warning(db):
    _season(db, 10)
    _entry(db, BUYER, "Imposter", 1560, 2)
    assert _preview(db)["reason"] == "few_games"


def test_nothing_above_1500_no_warning(db):
    _season(db, 10)
    _entry(db, BUYER, "Imposter", 1490, 6)
    assert _preview(db)["reason"] == "nothing_above_cap"


def test_already_reset_this_season_no_warning(db):
    _season(db, 10)
    _entry(db, BUYER, "Imposter", 1560, 6)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE ticket_resets (event_id INTEGER, user_id INTEGER, reset_at TEXT, details TEXT)")
    conn.execute("INSERT INTO ticket_resets VALUES (9, ?, 'x', '')", (int(BUYER),))
    conn.commit()
    conn.close()
    assert _preview(db)["reason"] == "already_reset"


def _role(path, role_id, status):
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO season_ticket_roles (role_id, name, status, created_at) VALUES (?, ?, ?, 'x')",
                 (role_id, "Ticket", status))
    conn.commit()
    conn.close()


def test_which_listings_count_as_this_seasons_ticket(db, monkeypatch):
    monkeypatch.setattr(webapp_config, "ALWAYS_TICKET_ROLE_IDS", set())
    _role(db, ROLE_S9, "active")
    ticket = {"product_type": "discord_role", "discord_role_id": "season_ticket"}
    assert is_current_season_ticket(ticket)
    assert is_current_season_ticket({"product_type": "bundle", "discord_role_id": ROLE_S9})
    assert not is_current_season_ticket({"product_type": "physical", "discord_role_id": None})
    assert not is_current_season_ticket({"product_type": "discord_role", "discord_role_id": "999999999999999999"})
    # Once next season's ticket is on sale, the listing sells that one: no reset this season
    _role(db, ROLE_S10, "on_sale")
    assert not is_current_season_ticket(ticket)
