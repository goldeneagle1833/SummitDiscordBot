"""Tests for repository data access layer."""

import sqlite3
import pytest
from tests.conftest import seed_elo_data, seed_matches

from repositories.elo import EloRepository
from repositories.matches import MatchRepository
from repositories.user_profiles import UserProfileRepository


# ── EloRepository ────────────────────────────────────────────


class TestEloRepository:
    def test_get_all_standings_empty(self, elo_db):
        repo = EloRepository(db_path=elo_db)
        assert repo.get_all_standings() == []

    def test_get_all_standings_returns_players(self, elo_db):
        seed_elo_data(elo_db, [
            {"user_id": "1", "name": "Alice", "online_elo": 1800, "paper_elo": 1500},
            {"user_id": "2", "name": "Bob", "online_elo": 1600, "paper_elo": 1700},
        ])
        repo = EloRepository(db_path=elo_db)
        standings = repo.get_all_standings()
        assert len(standings) == 2
        assert standings[0]["display_name"] == "Alice"
        assert standings[0]["elo"] == 1800
        assert standings[0]["primary_mode"] == "Online"

    def test_primary_mode_paper_when_paper_higher(self, elo_db):
        seed_elo_data(elo_db, [
            {"user_id": "1", "name": "PaperPro", "online_elo": 1400, "paper_elo": 1700},
        ])
        repo = EloRepository(db_path=elo_db)
        standings = repo.get_all_standings()
        assert standings[0]["primary_mode"] == "Paper"

    def test_get_user_elo(self, elo_db):
        seed_elo_data(elo_db, [
            {"user_id": "42", "name": "Player42", "online_elo": 1650},
        ])
        repo = EloRepository(db_path=elo_db)
        elo = repo.get_user_elo("42")
        assert elo == 1650

    def test_get_user_elo_not_found(self, elo_db):
        repo = EloRepository(db_path=elo_db)
        assert repo.get_user_elo("nonexistent") is None

    def test_get_active_event_none(self, elo_db):
        repo = EloRepository(db_path=elo_db)
        assert repo.get_active_event() is None

    def test_get_active_event(self, elo_db):
        conn = sqlite3.connect(str(elo_db))
        conn.execute("""
            INSERT INTO events (event_name, start_date, end_date, is_active)
            VALUES ('Test Event', '2025-01-01', NULL, 1)
        """)
        conn.commit()
        conn.close()

        repo = EloRepository(db_path=elo_db)
        event = repo.get_active_event()
        assert event is not None
        assert event["event_name"] == "Test Event"

    def test_get_all_events(self, elo_db):
        conn = sqlite3.connect(str(elo_db))
        conn.execute("INSERT INTO events (event_name, start_date, is_active) VALUES ('E1', '2024-01-01', 0)")
        conn.execute("INSERT INTO events (event_name, start_date, is_active) VALUES ('E2', '2025-01-01', 1)")
        conn.commit()
        conn.close()

        repo = EloRepository(db_path=elo_db)
        events = repo.get_all_events()
        assert len(events) == 2

    def test_get_event_standings(self, elo_db):
        seed_elo_data(elo_db, [
            {"user_id": "1", "name": "Alice", "online_event_elo": 1600},
            {"user_id": "2", "name": "Bob", "online_event_elo": 1700},
        ])
        repo = EloRepository(db_path=elo_db)
        standings = repo.get_event_standings()
        assert len(standings) == 2
        assert standings[0]["display_name"] == "Bob"
        assert standings[0]["event_elo"] == 1700

    def test_get_all_standings_with_event(self, elo_db):
        seed_elo_data(elo_db, [
            {"user_id": "1", "name": "Alice", "online_elo": 1800, "online_event_elo": 1600,
             "paper_elo": 1500, "paper_event_elo": 1500},
        ])
        repo = EloRepository(db_path=elo_db)
        standings = repo.get_all_standings_with_event()
        assert len(standings) == 1
        assert standings[0]["event_elo"] == 1600
        assert standings[0]["paper_event_elo"] == 1500

    def test_delete_player(self, elo_db):
        seed_elo_data(elo_db, [{"user_id": "1", "name": "Deleteme"}])
        repo = EloRepository(db_path=elo_db)
        assert repo.get_user_elo("1") is not None
        repo.delete_player("1")
        assert repo.get_user_elo("1") is None

    def test_upsert_user_elo(self, elo_db):
        repo = EloRepository(db_path=elo_db)
        repo.upsert_user_elo("new_player", "NewPlayer", 1600)
        assert repo.get_user_elo("new_player") == 1600
        # Update existing
        repo.upsert_user_elo("new_player", "NewPlayer", 1700)
        assert repo.get_user_elo("new_player") == 1700

    def test_get_all_elos(self, elo_db):
        seed_elo_data(elo_db, [
            {"user_id": "1", "name": "A", "online_elo": 1200},
            {"user_id": "2", "name": "B", "online_elo": 1800},
        ])
        repo = EloRepository(db_path=elo_db)
        elos = repo.get_all_elos()
        assert sorted(elos) == [1200, 1800]


# ── MatchRepository ──────────────────────────────────────────


class TestMatchRepository:
    def test_get_available_dates_empty(self, match_db):
        MatchRepository._columns_ensured = False
        repo = MatchRepository(db_path=match_db)
        assert repo.get_available_dates() == []

    def test_get_available_dates_with_data(self, match_db):
        seed_matches(match_db, [
            {"winner_id": "1", "loser_id": "2", "timestamp": "2025-01-15 12:00:00"},
            {"winner_id": "3", "loser_id": "4", "timestamp": "2025-01-16 14:00:00"},
        ])
        MatchRepository._columns_ensured = False
        repo = MatchRepository(db_path=match_db)
        dates = repo.get_available_dates()
        assert len(dates) == 2
        assert "2025-01-16" in dates

    def test_get_wins_count(self, match_db):
        seed_matches(match_db, [
            {"winner_id": "player1", "loser_id": "player2"},
            {"winner_id": "player1", "loser_id": "player3"},
            {"winner_id": "player2", "loser_id": "player1"},
        ])
        MatchRepository._columns_ensured = False
        repo = MatchRepository(db_path=match_db)
        assert repo.get_wins_count("player1") == 2
        assert repo.get_wins_count("player2") == 1

    def test_get_losses_count(self, match_db):
        seed_matches(match_db, [
            {"winner_id": "player1", "loser_id": "player2"},
            {"winner_id": "player3", "loser_id": "player2"},
        ])
        MatchRepository._columns_ensured = False
        repo = MatchRepository(db_path=match_db)
        assert repo.get_losses_count("player2") == 2
        assert repo.get_losses_count("player1") == 0

    def test_ensure_columns_idempotent(self, match_db):
        """Calling _ensure_columns twice shouldn't raise."""
        MatchRepository._columns_ensured = False
        repo1 = MatchRepository(db_path=match_db)
        MatchRepository._columns_ensured = False
        repo2 = MatchRepository(db_path=match_db)
        assert repo2.get_available_dates() == []


# ── UserProfileRepository ────────────────────────────────────


class TestUserProfileRepository:
    def test_upsert_and_get_profile(self, match_db):
        repo = UserProfileRepository(db_path=match_db)
        repo.upsert_profile(
            user_id="12345",
            display_name="TestUser",
            avatar="abc.png",
            provider="discord",
        )
        profile = repo.get_by_user_id("12345")
        assert profile is not None
        assert profile["display_name"] == "TestUser"

    def test_upsert_updates_existing(self, match_db):
        repo = UserProfileRepository(db_path=match_db)
        repo.upsert_profile(user_id="12345", display_name="OldName", provider="discord")
        repo.upsert_profile(user_id="12345", display_name="NewName", provider="discord")
        profile = repo.get_by_user_id("12345")
        assert profile["display_name"] == "NewName"

    def test_get_nonexistent_profile(self, match_db):
        repo = UserProfileRepository(db_path=match_db)
        assert repo.get_by_user_id("nonexistent") is None

    def test_custom_display_name_stored(self, match_db):
        repo = UserProfileRepository(db_path=match_db)
        repo.upsert_profile(user_id="99", display_name="OAuth", provider="discord")
        conn = sqlite3.connect(str(match_db))
        conn.execute("UPDATE user_profiles SET custom_display_name = 'Custom' WHERE user_id = '99'")
        conn.commit()
        conn.close()
        profile = repo.get_by_user_id("99")
        assert profile["custom_display_name"] == "Custom"

    def test_ensure_table_idempotent(self, match_db):
        """Creating repo twice doesn't fail (table already exists)."""
        repo1 = UserProfileRepository(db_path=match_db)
        repo2 = UserProfileRepository(db_path=match_db)
        assert repo2.get_by_user_id("nope") is None

    def test_search_by_display_name(self, match_db):
        repo = UserProfileRepository(db_path=match_db)
        repo.upsert_profile(user_id="1", display_name="AliceWonder", provider="discord")
        repo.upsert_profile(user_id="2", display_name="BobBuilder", provider="discord")
        results = repo.search_by_display_name("Alice")
        assert len(results) == 1
        assert results[0]["display_name"] == "AliceWonder"
