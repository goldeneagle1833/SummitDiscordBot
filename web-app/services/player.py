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
