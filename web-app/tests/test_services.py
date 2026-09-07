"""Tests for service business logic layer."""

from unittest.mock import MagicMock
import pytest

from services.leaderboard import LeaderboardService
from services.match import MatchService
from services.player import PlayerService


# ── LeaderboardService ───────────────────────────────────────


class TestLeaderboardService:
    def _make_elo_repo(self, standings=None, events=None, active_event=None):
        repo = MagicMock()
        repo.get_all_standings.return_value = standings or []
        repo.get_all_standings_with_event.return_value = standings or []
        repo.get_event_standings.return_value = standings or []
        repo.get_all_events.return_value = events or []
        repo.get_active_event.return_value = active_event
        repo.get_all_elos.return_value = []
        repo.get_user_elo.return_value = 1500
        return repo

    def _make_match_repo(self, wins=0, losses=0, season_players=None, season_records=None):
        repo = MagicMock()
        repo.get_wins_count.return_value = wins
        repo.get_losses_count.return_value = losses
        repo.get_season_players.return_value = season_players or []
        repo.get_season_records.return_value = season_records or {}
        repo.get_season_wins_count.return_value = wins
        repo.get_season_losses_count.return_value = losses
        return repo

    def test_get_leaderboard_empty(self):
        service = LeaderboardService(
            elo_repo=self._make_elo_repo(),
            match_repo=self._make_match_repo(),
        )
        assert service.get_leaderboard() == []

    def test_get_leaderboard_with_players(self):
        standings = [
            {"user_id": "1", "display_name": "Alice", "elo": 1800,
             "paper_elo": 1500, "online_elo": 1800, "primary_mode": "Online"},
        ]
        elo_repo = self._make_elo_repo(standings=standings)
        match_repo = self._make_match_repo(wins=10, losses=5)

        service = LeaderboardService(elo_repo=elo_repo, match_repo=match_repo)
        result = service.get_leaderboard()

        assert len(result) == 1
        assert result[0]["name"] == "Alice"
        assert result[0]["elo"] == 1800
        assert result[0]["wins"] == 10
        assert result[0]["losses"] == 5

    def test_get_event_leaderboard_no_active_event(self):
        service = LeaderboardService(
            elo_repo=self._make_elo_repo(active_event=None),
            match_repo=self._make_match_repo(),
        )
        result = service.get_event_leaderboard()
        assert result["event"] is None
        assert result["leaderboard"] == []

    def test_get_event_leaderboard_includes_season_record(self):
        standings = [
            {"user_id": "1", "display_name": "Alice", "event_elo": 1640},
            {"user_id": "2", "display_name": "Bob", "event_elo": 1580},
        ]
        active_event = {"event_id": 7, "event_name": "Season 7", "start_date": "2025-01-01"}
        match_repo = self._make_match_repo(
            season_records={"1": {"wins": 5, "losses": 2}},
        )
        service = LeaderboardService(
            elo_repo=self._make_elo_repo(standings=standings, active_event=active_event),
            match_repo=match_repo,
        )

        result = service.get_event_leaderboard()

        assert result["leaderboard"] == [
            {"id": "1", "name": "Alice", "event_elo": 1640, "wins": 5, "losses": 2},
        ]
        match_repo.get_season_records.assert_called_once_with("2025-01-01")

    def test_get_combined_leaderboard_structure(self):
        elo_repo = self._make_elo_repo()
        match_repo = self._make_match_repo()
        service = LeaderboardService(elo_repo=elo_repo, match_repo=match_repo)
        result = service.get_combined_leaderboard()
        assert "lifetime" in result
        assert "event" in result
        assert "info" in result["event"]
        assert "leaderboard" in result["event"]

    def test_get_elo_distribution_empty(self):
        elo_repo = self._make_elo_repo()
        service = LeaderboardService(elo_repo=elo_repo, match_repo=self._make_match_repo())
        result = service.get_elo_distribution()
        assert result["total_players"] == 0
        assert result["increments"] == []

    def test_get_elo_distribution_with_data(self):
        elo_repo = self._make_elo_repo()
        elo_repo.get_all_elos.return_value = [1200, 1300, 1300, 1500, 1800]

        service = LeaderboardService(elo_repo=elo_repo, match_repo=self._make_match_repo())
        result = service.get_elo_distribution()
        assert result["total_players"] == 5
        # Should have increment bands
        assert len(result["increments"]) > 0
        # The 1300-1399 band should have 2 players
        band_1300 = next(b for b in result["increments"] if b["range"] == "1300-1399")
        assert band_1300["count"] == 2


# ── MatchService ─────────────────────────────────────────────


class TestMatchService:
    def test_get_available_dates(self):
        match_repo = MagicMock()
        match_repo.get_available_dates.return_value = ["2025-01-15", "2025-01-16"]
        service = MatchService(match_repo=match_repo)
        assert service.get_available_dates() == ["2025-01-15", "2025-01-16"]

    def test_get_match_history_with_date(self):
        match_repo = MagicMock()
        match_repo.get_matches_by_date.return_value = [{"id": 1}]
        service = MatchService(match_repo=match_repo)
        result = service.get_match_history(date="2025-01-15")
        match_repo.get_matches_by_date.assert_called_once_with("2025-01-15")
        assert result == [{"id": 1}]

    def test_get_match_history_no_date(self):
        match_repo = MagicMock()
        match_repo.get_recent_matches.return_value = [{"id": 2}]
        service = MatchService(match_repo=match_repo)
        result = service.get_match_history(date=None)
        match_repo.get_recent_matches.assert_called_once_with(hours=24)
        assert result == [{"id": 2}]

    def test_get_deck_snapshot_player_not_in_match(self):
        match_repo = MagicMock()
        match_repo.get_match_by_id.return_value = {
            "winner_id": "1", "loser_id": "2",
            "winner_name": "A", "loser_name": "B",
            "timestamp": "2025-01-15", "old_json_deck": None,
            "winner_json": None, "loser_json": None,
        }
        service = MatchService(match_repo=match_repo)
        result = service.get_deck_snapshot(1, "99")
        assert "error" in result
        assert "not found" in result["error"]

    def test_get_deck_snapshot_no_match(self):
        match_repo = MagicMock()
        match_repo.get_match_by_id.return_value = None
        service = MatchService(match_repo=match_repo)
        assert service.get_deck_snapshot(999, "1") is None


# ── PlayerService ────────────────────────────────────────────


class TestPlayerService:
    def test_get_player_stats(self):
        elo_repo = MagicMock()
        elo_repo.get_user_elo.return_value = 1700
        match_repo = MagicMock()
        match_repo.get_wins_count.return_value = 20
        match_repo.get_losses_count.return_value = 10

        service = PlayerService(elo_repo=elo_repo, match_repo=match_repo)
        stats = service.get_player_stats("123")

        assert stats["elo"] == 1700
        assert stats["wins"] == 20
        assert stats["losses"] == 10
        assert stats["total_matches"] == 30
        assert stats["win_rate"] == 66.7

    def test_get_player_stats_no_elo(self):
        elo_repo = MagicMock()
        elo_repo.get_user_elo.return_value = None
        match_repo = MagicMock()
        match_repo.get_wins_count.return_value = 0
        match_repo.get_losses_count.return_value = 0

        service = PlayerService(elo_repo=elo_repo, match_repo=match_repo)
        stats = service.get_player_stats("new_player")
        assert stats["elo"] == 1500  # default
        assert stats["win_rate"] == 0

    def test_get_player_stats_zero_division(self):
        elo_repo = MagicMock()
        elo_repo.get_user_elo.return_value = 1500
        match_repo = MagicMock()
        match_repo.get_wins_count.return_value = 0
        match_repo.get_losses_count.return_value = 0

        service = PlayerService(elo_repo=elo_repo, match_repo=match_repo)
        stats = service.get_player_stats("zero")
        assert stats["win_rate"] == 0
        assert stats["total_matches"] == 0
