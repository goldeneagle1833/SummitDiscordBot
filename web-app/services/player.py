"""Player service for player stats and profiles."""

from repositories.elo import EloRepository
from repositories.matches import MatchRepository


class PlayerService:
    """Business logic for player operations."""

    def __init__(
        self,
        elo_repo: EloRepository | None = None,
        match_repo: MatchRepository | None = None,
    ):
        self._elo_repo = elo_repo or EloRepository()
        self._match_repo = match_repo or MatchRepository()

    def get_player_stats(self, player_id: str) -> dict | None:
        """Get comprehensive stats for a player."""
        # Keep player_id as string to avoid overflow with large Google IDs
        # SQLite's type affinity handles string-to-integer comparison automatically
        elo = self._elo_repo.get_user_elo(player_id)
        wins = self._match_repo.get_wins_count(player_id)
        losses = self._match_repo.get_losses_count(player_id)

        total_matches = wins + losses
        win_rate = (wins / total_matches * 100) if total_matches > 0 else 0

        return {
            "player_id": player_id,
            "elo": elo or 1500,
            "wins": wins,
            "losses": losses,
            "total_matches": total_matches,
            "win_rate": round(win_rate, 1),
        }

    def get_player_matches(self, player_id: str, limit: int = 100) -> list[dict]:
        """Get match history for a player."""
        return self._match_repo.get_player_matches(player_id, limit)

    def get_limited_stats(self, player_id: str) -> dict:
        """Get limited arena stats for a player."""
        limited_elo = self._match_repo.get_limited_elo(player_id)
        arena_runs = self._match_repo.get_limited_arena_runs(player_id)
        limited_matches = self._match_repo.get_limited_matches_for_player(player_id)

        total_wins = sum(1 for m in limited_matches if str(m["winner_id"]) == str(player_id))
        total_losses = sum(1 for m in limited_matches if str(m["loser_id"]) == str(player_id))
        total = total_wins + total_losses

        return {
            "limited_elo": limited_elo,
            "arena_runs": arena_runs,
            "recent_matches": limited_matches,
            "total_wins": total_wins,
            "total_losses": total_losses,
            "total_matches": total,
            "win_rate": round(total_wins / total * 100, 1) if total > 0 else 0,
        }
