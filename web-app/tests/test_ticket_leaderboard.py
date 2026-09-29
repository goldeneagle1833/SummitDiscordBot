"""The Discord leaderboard channel as a partner endpoint: ticket holders ranked."""

import sqlite3
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

import services.ticket_holders as ticket_holders
import webapp_config
from repositories.brackets import BracketRepository
from services.ticket_leaderboard import TicketLeaderboardService
from tests.conftest import seed_elo_data, seed_matches


class FakeLeaderboard:
    SEASON = {"event_id": 7, "event_name": "Season 7"}

    def __init__(self, event_players=None, lifetime_players=None, event=SEASON):
        self.event_players = event_players if event_players is not None else []
        self.lifetime_players = lifetime_players or []
        self.event = event

    def get_event_leaderboard(self):
        return {"event": self.event, "leaderboard": self.event_players}

    def get_leaderboard(self):
        return self.lifetime_players


def event_entry(i, elo, wins=3, losses=1):
    return {
        "id": f"u{i}", "name": f"P{i}", "event_elo": elo,
        "wins": wins, "losses": losses, "voice_games": 2,
    }


@pytest.fixture()
def repo(tmp_path):
    repository = BracketRepository(db_path=tmp_path / "tickets.db")
    repository.ensure_tables()
    return repository


@pytest.fixture(autouse=True)
def unconfigured_sync(monkeypatch):
    """Never reach Discord from a test."""
    monkeypatch.setattr(webapp_config, "DISCORD_BOT_TOKEN", "")
    monkeypatch.setattr(webapp_config, "TICKET_HOLDER_ROLE_IDS", set())


# -- Service ------------------------------------------------------


class TestTicketLeaderboardService:
    def test_ticket_holders_are_ranked_best_first(self, repo):
        players = [event_entry(i, 2000 - i * 10) for i in range(1, 13)]
        repo.replace_ticket_holders([{"user_id": "u2"}, {"user_id": "u5"}, {"user_id": "u9"}])
        service = TicketLeaderboardService(FakeLeaderboard(players), repo)

        result = service.get_leaderboard()

        assert [p["user_id"] for p in result["ticket_holders"]] == ["u2", "u5", "u9"]
        assert [p["rank"] for p in result["ticket_holders"]] == [1, 2, 3]
        assert [p["overall_rank"] for p in result["ticket_holders"]] == [2, 5, 9]
        assert all(p["is_ticket_holder"] for p in result["ticket_holders"])
        assert result["rating"] == "event"
        assert result["event"]["event_name"] == "Season 7"

    def test_each_entry_carries_the_channel_fields(self, repo):
        repo.replace_ticket_holders([{"user_id": "u1"}])
        service = TicketLeaderboardService(
            FakeLeaderboard([event_entry(1, 1650, wins=7, losses=2)]), repo
        )

        entry = service.get_leaderboard()["ticket_holders"][0]

        assert entry["display_name"] == "P1"
        assert entry["elo"] == 1650
        assert entry["games"] == 9
        assert entry["wins"] == 7
        assert entry["losses"] == 2
        assert entry["voice_games"] == 2

    def test_free_play_is_everyone_without_a_ticket(self, repo):
        players = [event_entry(i, 2000 - i) for i in range(1, 13)]
        repo.replace_ticket_holders([{"user_id": "u1"}])
        service = TicketLeaderboardService(FakeLeaderboard(players), repo)

        result = service.get_leaderboard()

        free = result["free_play"]
        assert len(free) == 8  # the channel shows the top 8
        assert free[0]["user_id"] == "u2"
        assert free[0]["rank"] == 1
        assert not any(p["is_ticket_holder"] for p in free)

    def test_overall_is_the_top_eight_regardless_of_tickets(self, repo):
        players = [event_entry(i, 2000 - i) for i in range(1, 13)]
        repo.replace_ticket_holders([{"user_id": "u3"}])
        service = TicketLeaderboardService(FakeLeaderboard(players), repo)

        overall = service.get_leaderboard()["overall"]

        assert [p["user_id"] for p in overall] == [f"u{i}" for i in range(1, 9)]
        assert overall[2]["is_ticket_holder"] is True

    def test_games_played_counts_every_rated_game_once(self, repo):
        players = [event_entry(1, 1600, wins=4, losses=1), event_entry(2, 1500, wins=1, losses=4)]
        service = TicketLeaderboardService(FakeLeaderboard(players), repo)

        assert service.get_leaderboard()["games_played"] == 5

    def test_limit_caps_the_ticket_holder_list(self, repo):
        players = [event_entry(i, 2000 - i) for i in range(1, 31)]
        repo.replace_ticket_holders([{"user_id": f"u{i}"} for i in range(1, 31)])
        service = TicketLeaderboardService(FakeLeaderboard(players), repo)

        assert len(service.get_leaderboard()["ticket_holders"]) == 30
        assert len(service.get_leaderboard(limit=24)["ticket_holders"]) == 24

    def test_without_a_roster_nobody_is_a_ticket_holder(self, repo):
        service = TicketLeaderboardService(FakeLeaderboard([event_entry(1, 1600)]), repo)

        result = service.get_leaderboard()

        assert result["ticket_holders"] == []
        assert len(result["free_play"]) == 1
        assert result["roster"] == {"size": 0, "synced_at": None, "configured": False}

    def test_falls_back_to_lifetime_elo_when_no_event_is_running(self, repo):
        lifetime = [
            {"id": "u1", "name": "P1", "elo": 1700, "wins": 10, "losses": 5},
            {"id": "u2", "name": "P2", "elo": 1600, "wins": 4, "losses": 6},
        ]
        repo.replace_ticket_holders([{"user_id": "u2"}])
        service = TicketLeaderboardService(
            FakeLeaderboard(event_players=[], lifetime_players=lifetime, event=None), repo
        )

        result = service.get_leaderboard()

        assert result["rating"] == "lifetime"
        assert result["event"] is None
        assert result["ticket_holders"][0]["elo"] == 1600
        assert result["ticket_holders"][0]["games"] == 10

    def test_reports_when_the_roster_was_synced(self, repo):
        repo.replace_ticket_holders([{"user_id": "u1"}])
        service = TicketLeaderboardService(FakeLeaderboard([event_entry(1, 1600)]), repo)

        roster = service.get_leaderboard()["roster"]

        assert roster["size"] == 1
        assert roster["synced_at"] is not None


# -- Roster freshness ----------------------------------------------


@pytest.fixture()
def configured_sync(monkeypatch):
    monkeypatch.setattr(webapp_config, "DISCORD_BOT_TOKEN", "bot-token")
    monkeypatch.setattr(webapp_config, "TICKET_HOLDER_ROLE_IDS", {"role1"})


def age_roster(repo, age: timedelta):
    """Pretend the cached roster was synced `age` ago."""
    conn = sqlite3.connect(repo._db_path)
    conn.execute(
        "UPDATE ticket_holders SET synced_at = ?",
        ((datetime.now() - age).isoformat(),),
    )
    conn.commit()
    conn.close()


class TestRosterFreshness:
    def test_a_never_synced_roster_is_fetched_inline(self, repo, configured_sync):
        def fake_sync(r):
            r.replace_ticket_holders([{"user_id": "u1"}])
            return {"count": 1}

        with patch.object(ticket_holders, "sync_roster", side_effect=fake_sync) as sync:
            synced_at = ticket_holders.ensure_roster_fresh(repo)

        sync.assert_called_once_with(repo)
        assert synced_at is not None
        assert ticket_holders.ticket_holder_ids(repo) == {"u1"}

    def test_a_fresh_roster_is_left_alone(self, repo, configured_sync):
        repo.replace_ticket_holders([{"user_id": "u1"}])

        with patch.object(ticket_holders, "sync_roster") as sync, \
                patch.object(ticket_holders.threading, "Thread") as thread:
            ticket_holders.ensure_roster_fresh(repo)

        sync.assert_not_called()
        thread.assert_not_called()

    def test_a_stale_roster_is_served_while_refreshing_in_the_background(
        self, repo, configured_sync
    ):
        repo.replace_ticket_holders([{"user_id": "u1"}])
        age_roster(repo, ticket_holders.ROSTER_MAX_AGE + timedelta(minutes=1))

        with patch.object(ticket_holders, "sync_roster") as sync, \
                patch.object(ticket_holders.threading, "Thread") as thread:
            synced_at = ticket_holders.ensure_roster_fresh(repo)

        sync.assert_not_called()  # not on the request thread
        thread.assert_called_once()
        assert thread.call_args.kwargs["target"] is ticket_holders._sync_in_background
        thread.return_value.start.assert_called_once()
        assert synced_at is not None

    def test_a_failed_inline_sync_falls_back_to_nothing(self, repo, configured_sync):
        with patch.object(
            ticket_holders, "sync_roster",
            side_effect=ticket_holders.TicketHolderError("Discord returned 403"),
        ):
            assert ticket_holders.ensure_roster_fresh(repo) is None

    def test_nothing_happens_when_sync_is_not_configured(self, repo):
        with patch.object(ticket_holders, "sync_roster") as sync:
            assert ticket_holders.ensure_roster_fresh(repo) is None
        sync.assert_not_called()

    def test_background_refresh_swallows_discord_errors(self, repo):
        with patch.object(
            ticket_holders, "sync_roster",
            side_effect=ticket_holders.TicketHolderError("offline"),
        ):
            ticket_holders._sync_in_background(repo)  # must not raise


# -- Route --------------------------------------------------------


def seed_season(elo_db, match_db):
    conn = sqlite3.connect(str(elo_db))
    conn.execute(
        "INSERT INTO events (event_name, start_date, is_active) VALUES (?, ?, 1)",
        ("Season 7", "2025-01-01"),
    )
    conn.commit()
    conn.close()
    seed_elo_data(elo_db, [
        {"user_id": "u1", "name": "Alice", "online_event_elo": 1700},
        {"user_id": "u2", "name": "Bob", "online_event_elo": 1600},
        {"user_id": "u3", "name": "Cara", "online_event_elo": 1550},
        {"user_id": "u4", "name": "Idle", "online_event_elo": 1500},
    ])
    seed_matches(match_db, [
        {"winner_id": "u1", "loser_id": "u2"},
        {"winner_id": "u1", "loser_id": "u3"},
        {"winner_id": "u3", "loser_id": "u2"},
    ])


class TestTicketHolderRoute:
    URL = "/api/leaderboard/ticket-holders"

    def test_requires_a_partner_or_integration_key(self, client):
        assert client.get(self.URL).status_code == 401
        assert client.get(self.URL, headers={"X-API-Key": "nope"}).status_code == 401

    def test_accepts_the_pso_partner_key(self, client, elo_db, match_db, monkeypatch):
        monkeypatch.setattr(webapp_config, "DRAFT_SORCERY_API_KEY", "partner-test-key")
        seed_season(elo_db, match_db)
        BracketRepository().replace_ticket_holders([{"user_id": "u2"}, {"user_id": "u3"}])

        response = client.get(self.URL, headers={"X-API-Key": "partner-test-key"})

        assert response.status_code == 200
        body = response.get_json()
        assert body["success"] is True
        assert body["event"]["event_name"] == "Season 7"
        assert body["games_played"] == 3
        assert [p["display_name"] for p in body["ticket_holders"]] == ["Bob", "Cara"]
        assert body["ticket_holders"][0]["rank"] == 1
        assert body["ticket_holders"][0]["overall_rank"] == 2
        assert body["ticket_holders"][0]["games"] == 2
        # Idle never played this season, so the channel does not list them.
        assert [p["display_name"] for p in body["free_play"]] == ["Alice"]
        assert body["roster"]["size"] == 2

    def test_accepts_a_general_integration_key(self, client, elo_db, match_db):
        seed_season(elo_db, match_db)
        response = client.get(self.URL, headers={"X-API-Key": "test-api-key-123"})
        assert response.status_code == 200

    def test_limit_caps_the_list(self, client, elo_db, match_db):
        seed_season(elo_db, match_db)
        BracketRepository().replace_ticket_holders([{"user_id": "u2"}, {"user_id": "u3"}])

        response = client.get(
            self.URL + "?limit=1", headers={"X-API-Key": "test-api-key-123"}
        )

        assert len(response.get_json()["ticket_holders"]) == 1

    def test_rejects_a_silly_limit(self, client):
        response = client.get(self.URL + "?limit=0", headers={"X-API-Key": "test-api-key-123"})
        assert response.status_code == 400
