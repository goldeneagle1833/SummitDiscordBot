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


# ── FartRepository ───────────────────────────────────────────


class TestFartRepositoryReset:
    def _seed_full_fart_db(self, db_path):
        """Create every known tracking table plus config + a future unknown table."""
        conn = sqlite3.connect(str(db_path))
        schema = {
            "fart_scores": """
                CREATE TABLE fart_scores (
                    user_id INTEGER PRIMARY KEY,
                    user_display_name TEXT,
                    date_last_updated TEXT,
                    score INTEGER
                )
            """,
            "fart_history": """
                CREATE TABLE fart_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    fart_type TEXT NOT NULL,
                    roll INTEGER NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """,
            "command_usage": """
                CREATE TABLE command_usage (
                    user_id INTEGER,
                    command_name TEXT,
                    last_used TEXT,
                    PRIMARY KEY (user_id, command_name)
                )
            """,
            "lucky_charms": """
                CREATE TABLE lucky_charms (
                    user_id INTEGER PRIMARY KEY,
                    activated_at TEXT
                )
            """,
            "lucky_charm_usage": """
                CREATE TABLE lucky_charm_usage (
                    user_id INTEGER,
                    command_name TEXT,
                    last_used TEXT,
                    PRIMARY KEY (user_id, command_name)
                )
            """,
            "fart_leader_only_once": """
                CREATE TABLE fart_leader_only_once (
                    user_id INTEGER PRIMARY KEY,
                    user_display_name TEXT
                )
            """,
            "evil_star_usage": """
                CREATE TABLE evil_star_usage (
                    user_id INTEGER PRIMARY KEY,
                    used_at TEXT NOT NULL
                )
            """,
            "fart_donation_usage": """
                CREATE TABLE fart_donation_usage (
                    donor_id INTEGER NOT NULL,
                    recipient_id INTEGER NOT NULL,
                    donated_at TEXT NOT NULL,
                    PRIMARY KEY (donor_id, recipient_id)
                )
            """,
            "fart_gift_usage": """
                CREATE TABLE fart_gift_usage (
                    gifter_id INTEGER NOT NULL,
                    recipient_id INTEGER NOT NULL,
                    gifted_at TEXT NOT NULL,
                    PRIMARY KEY (gifter_id, recipient_id)
                )
            """,
            "protection_status": """
                CREATE TABLE protection_status (
                    user_id INTEGER PRIMARY KEY,
                    protected_until TIMESTAMP
                )
            """,
            "shop_blocks": """
                CREATE TABLE shop_blocks (
                    user_id INTEGER PRIMARY KEY,
                    blocked_until TIMESTAMP
                )
            """,
            "gas_shields": """
                CREATE TABLE gas_shields (
                    user_id INTEGER PRIMARY KEY
                )
            """,
            "fart_traps": """
                CREATE TABLE fart_traps (
                    user_id INTEGER PRIMARY KEY,
                    set_by INTEGER NOT NULL
                )
            """,
            "frost_shart_freeze": """
                CREATE TABLE frost_shart_freeze (
                    user_id INTEGER PRIMARY KEY,
                    frozen_until TEXT NOT NULL
                )
            """,
            "uber_rare_curio_claimed": """
                CREATE TABLE uber_rare_curio_claimed (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    claimed_by_user_id INTEGER,
                    variant TEXT NOT NULL,
                    claimed_at TEXT NOT NULL
                )
            """,
            "frostshart_legacy_repair": """
                CREATE TABLE frostshart_legacy_repair (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    repaired_at TEXT NOT NULL
                )
            """,
            "uber_rare_curio_season": """
                CREATE TABLE uber_rare_curio_season (
                    user_id INTEGER NOT NULL,
                    variant TEXT NOT NULL,
                    rolled_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, variant)
                )
            """,
            "yourt_rampage": """
                CREATE TABLE yourt_rampage (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    started_at TEXT NOT NULL,
                    ends_at TEXT NOT NULL,
                    attacks_done INTEGER NOT NULL DEFAULT 0,
                    channel_id INTEGER NOT NULL,
                    summoned_by_user_id INTEGER
                )
            """,
            # Config tables — must survive reset
            "fart_game_commands": """
                CREATE TABLE fart_game_commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    label TEXT NOT NULL
                )
            """,
            "fart_shop_items": """
                CREATE TABLE fart_shop_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    label TEXT NOT NULL
                )
            """,
            # Future tracker that must still be wiped even if not listed
            "future_season_tracker": """
                CREATE TABLE future_season_tracker (
                    user_id INTEGER PRIMARY KEY,
                    used_at TEXT NOT NULL
                )
            """,
        }
        for ddl in schema.values():
            conn.execute(ddl)

        conn.execute(
            "INSERT INTO fart_scores VALUES (1, 'Alice', '2026-08-01T00:00:00', 100)"
        )
        conn.execute(
            "INSERT INTO fart_history (user_id, username, fart_type, roll, timestamp) "
            "VALUES (1, 'Alice', 'ordinary', 10, '2026-08-01T00:00:00')"
        )
        # !bullfart weekly + shop daily/weekly items
        conn.execute(
            "INSERT INTO command_usage VALUES (1, 'bullfart', '2026-08-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO command_usage VALUES (1, 'blue_shell', '2026-08-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO command_usage VALUES (1, 'thunder_fart', '2026-08-01T00:00:00')"
        )
        # !mushroom once/week + active buff
        conn.execute(
            "INSERT INTO lucky_charm_usage VALUES (1, 'mushroom', '2026-08-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO lucky_charms VALUES (1, '2026-08-01T00:00:00')"
        )
        # !taxes / !wealth once/reign
        conn.execute(
            "INSERT INTO fart_leader_only_once VALUES (1, 'Alice')"
        )
        conn.execute(
            "INSERT INTO evil_star_usage VALUES (1, '2026-08-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO fart_donation_usage VALUES (1, 2, '2026-08-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO fart_gift_usage VALUES (1, 2, '2026-08-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO protection_status VALUES (1, '2099-01-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO shop_blocks VALUES (2, '2099-01-01T00:00:00')"
        )
        conn.execute("INSERT INTO gas_shields VALUES (1)")
        conn.execute("INSERT INTO fart_traps VALUES (2, 1)")
        conn.execute(
            "INSERT INTO frost_shart_freeze VALUES (2, '2099-01-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO uber_rare_curio_claimed VALUES (1, 1, 'lavashart', '2026-08-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO frostshart_legacy_repair VALUES (1, '2026-08-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO uber_rare_curio_season VALUES (1, 'lavashart', '2026-08-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO uber_rare_curio_season VALUES (1, 'frostshart', '2026-08-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO yourt_rampage VALUES (1, '2026-08-01T00:00:00', '2026-08-01T01:00:00', 2, 1, 1)"
        )
        conn.execute(
            "INSERT INTO fart_game_commands (name, label) VALUES ('fart', 'Fart')"
        )
        conn.execute(
            "INSERT INTO fart_shop_items (name, label) VALUES ('mushroom', 'Mushroom')"
        )
        conn.execute(
            "INSERT INTO future_season_tracker VALUES (1, '2026-08-01T00:00:00')"
        )
        conn.commit()
        conn.close()

    def test_reset_game_clears_gift_and_donation_usage(self, tmp_path):
        from repositories.fart import FartRepository

        db_path = tmp_path / "fart_scores.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE fart_gift_usage (
                gifter_id INTEGER NOT NULL,
                recipient_id INTEGER NOT NULL,
                gifted_at TEXT NOT NULL,
                PRIMARY KEY (gifter_id, recipient_id)
            )
        """)
        conn.execute("""
            CREATE TABLE fart_donation_usage (
                donor_id INTEGER NOT NULL,
                recipient_id INTEGER NOT NULL,
                donated_at TEXT NOT NULL,
                PRIMARY KEY (donor_id, recipient_id)
            )
        """)
        conn.execute(
            "INSERT INTO fart_gift_usage VALUES (1, 2, '2026-01-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO fart_donation_usage VALUES (1, 2, '2026-01-01T00:00:00')"
        )
        conn.commit()
        conn.close()

        repo = FartRepository(db_path=db_path)
        cleared = repo.reset_game()

        assert cleared["fart_gift_usage"] == 1
        assert cleared["fart_donation_usage"] == 1

        conn = sqlite3.connect(str(db_path))
        assert conn.execute("SELECT COUNT(*) FROM fart_gift_usage").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM fart_donation_usage").fetchone()[0] == 0
        conn.close()

    def test_reset_game_clears_mushroom_bullfart_and_all_tracking(self, tmp_path):
        from repositories.fart import FartRepository

        db_path = tmp_path / "fart_scores.db"
        self._seed_full_fart_db(db_path)

        repo = FartRepository(db_path=db_path)
        cleared = repo.reset_game()

        # Item/action cooldowns the UI was missing
        assert cleared["lucky_charm_usage"] == 1  # !mushroom
        assert cleared["lucky_charms"] == 1
        assert cleared["command_usage"] == 3  # bullfart + blue_shell + thunder_fart
        assert cleared["fart_leader_only_once"] == 1  # taxes/wealth once/reign
        assert cleared["evil_star_usage"] == 1
        assert cleared["fart_scores"] == 1
        assert cleared["frost_shart_freeze"] == 1
        assert cleared["uber_rare_curio_season"] == 2
        assert cleared["yourt_rampage"] == 1
        assert cleared["future_season_tracker"] == 1  # unknown tables also wiped
        # Permanent one-time flag must NOT be wiped
        assert "uber_rare_curio_claimed" not in cleared
        assert "frostshart_legacy_repair" not in cleared

        # Config must NOT be wiped
        assert "fart_game_commands" not in cleared
        assert "fart_shop_items" not in cleared

        conn = sqlite3.connect(str(db_path))
        tracking = [
            "fart_scores",
            "fart_history",
            "command_usage",
            "lucky_charms",
            "lucky_charm_usage",
            "fart_leader_only_once",
            "evil_star_usage",
            "fart_donation_usage",
            "fart_gift_usage",
            "protection_status",
            "shop_blocks",
            "gas_shields",
            "fart_traps",
            "frost_shart_freeze",
            "uber_rare_curio_season",
            "yourt_rampage",
            "future_season_tracker",
        ]
        for table in tracking:
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
        assert conn.execute("SELECT COUNT(*) FROM fart_game_commands").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM fart_shop_items").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM uber_rare_curio_claimed").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM frostshart_legacy_repair").fetchone()[0] == 1
        conn.close()

    def test_reset_game_known_tracking_tables_match_docs(self):
        from repositories.fart import FartRepository

        # Guardrail: if someone adds a tracker constant, keep docs in sync
        expected = {
            "fart_scores",
            "fart_history",
            "command_usage",
            "lucky_charms",
            "lucky_charm_usage",
            "fart_leader_only_once",
            "evil_star_usage",
            "fart_donation_usage",
            "fart_gift_usage",
            "protection_status",
            "shop_blocks",
            "gas_shields",
            "fart_traps",
            "frost_shart_freeze",
            "uber_rare_curio_season",
            "yourt_rampage",
        }
        assert FartRepository._KNOWN_TRACKING_TABLES == expected
        assert FartRepository._PRESERVE_ON_RESET == {
            "fart_game_commands",
            "fart_shop_items",
            "uber_rare_curio_claimed",
            "frostshart_legacy_repair",
        }

    def test_evil_start_resets_then_reseeds_scores_in_plus_minus_250(self, tmp_path, monkeypatch):
        from repositories import fart as fart_mod
        from repositories.fart import FartRepository

        db_path = tmp_path / "fart_scores.db"
        self._seed_full_fart_db(db_path)

        scores = iter([-250, 0, 250])
        monkeypatch.setattr(fart_mod, "randint", lambda a, b: next(scores))

        repo = FartRepository(db_path=db_path)
        result = repo.evil_start()

        assert repo.EVIL_START_SCORE_MIN == -250
        assert repo.EVIL_START_SCORE_MAX == 250
        assert result["players_affected"] == 1
        assert result["players"][0]["score"] == -250

        conn = sqlite3.connect(str(db_path))
        score = conn.execute("SELECT score FROM fart_scores WHERE user_id = 1").fetchone()[0]
        assert score == -250
        # Same wipe as Reset Fart Game for season uber-rare flags
        assert conn.execute("SELECT COUNT(*) FROM uber_rare_curio_season").fetchone()[0] == 0
        # Global first-ever flag still preserved
        assert conn.execute("SELECT COUNT(*) FROM uber_rare_curio_claimed").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM fart_shop_items").fetchone()[0] == 1
        conn.close()

    def test_evil_start_uses_full_chaotic_range(self, tmp_path, monkeypatch):
        from repositories import fart as fart_mod
        from repositories.fart import FartRepository

        captured = {}

        def fake_randint(a, b):
            captured["a"] = a
            captured["b"] = b
            return 123

        monkeypatch.setattr(fart_mod, "randint", fake_randint)

        db_path = tmp_path / "fart_scores.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE fart_scores (
                user_id INTEGER PRIMARY KEY,
                user_display_name TEXT,
                date_last_updated TEXT,
                score INTEGER
            )
        """)
        conn.execute("INSERT INTO fart_scores VALUES (9, 'Chaos', NULL, 10)")
        conn.commit()
        conn.close()

        repo = FartRepository(db_path=db_path)
        result = repo.evil_start()
        assert captured == {"a": -250, "b": 250}
        assert result["players"][0]["score"] == 123

