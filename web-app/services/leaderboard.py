"""Leaderboard service for ELO rankings and distribution."""

from repositories.elo import EloRepository
from repositories.matches import MatchRepository


class LeaderboardService:
    """Business logic for leaderboard operations."""

    def __init__(
        self,
        elo_repo: EloRepository | None = None,
        match_repo: MatchRepository | None = None,
    ):
        self._elo_repo = elo_repo or EloRepository()
        self._match_repo = match_repo or MatchRepository()

    def get_leaderboard(self) -> list[dict]:
        """Get full leaderboard with win/loss records."""
        standings = self._elo_repo.get_all_standings()

        leaderboard_data = []
        for standing in standings:
            user_id = standing["user_id"]
            wins = self._match_repo.get_wins_count(user_id)
            losses = self._match_repo.get_losses_count(user_id)

            leaderboard_data.append({
                "id": str(user_id),
                "name": standing["display_name"],
                "elo": standing["elo"],
                "wins": wins,
                "losses": losses,
            })

        return leaderboard_data

    def get_elo_distribution(self) -> dict:
        """Get ELO distribution across bands."""
        elos = self._elo_repo.get_all_elos()
        total_players = len(elos)

        if total_players == 0:
            return {"increments": [], "offset": [], "total_players": 0}

        # 100pt increments (1200-1299, 1300-1399, etc.)
        increments = []
        for lower in range(1100, 2100, 100):
            upper = lower + 99
            count = sum(1 for elo in elos if lower <= elo <= upper)
            percentage = (count / total_players * 100) if count > 0 else 0
            increments.append({
                "range": f"{lower}-{upper}",
                "count": count,
                "percentage": round(percentage, 2),
            })

        # 2000+ bucket
        count_2000_plus = sum(1 for elo in elos if elo >= 2000)
        percentage_2000_plus = (
            (count_2000_plus / total_players * 100) if count_2000_plus > 0 else 0
        )
        increments.append({
            "range": "2000+",
            "count": count_2000_plus,
            "percentage": round(percentage_2000_plus, 2),
        })

        # 100pt offset (1050-1149, 1150-1249, etc.)
        offset = []
        for lower in range(1050, 2000, 100):
            upper = lower + 99
            count = sum(1 for elo in elos if lower <= elo <= upper)
            percentage = (count / total_players * 100) if count > 0 else 0
            offset.append({
                "range": f"{lower}-{upper}",
                "count": count,
                "percentage": round(percentage, 2),
            })

        # 1950+ bucket
        count_1950_plus = sum(1 for elo in elos if elo >= 1950)
        percentage_1950_plus = (
            (count_1950_plus / total_players * 100) if count_1950_plus > 0 else 0
        )
        offset.append({
            "range": "1950+",
            "count": count_1950_plus,
            "percentage": round(percentage_1950_plus, 2),
        })

        return {
            "increments": list(reversed(increments)),
            "offset": list(reversed(offset)),
            "total_players": total_players,
        }
