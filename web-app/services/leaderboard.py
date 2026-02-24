"""Leaderboard service for ELO rankings and distribution."""

from repositories.elo import EloRepository
from repositories.matches import MatchRepository
from repositories.external_matches import ExternalMatchRepository


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
        """Get full lifetime leaderboard with win/loss records."""
        standings = self._elo_repo.get_all_standings()

        leaderboard_data = []
        for standing in standings:
            user_id = standing["user_id"]
            wins = self._match_repo.get_wins_count(user_id)
            losses = self._match_repo.get_losses_count(user_id)

            leaderboard_data.append(
                {
                    "id": str(user_id),
                    "name": standing["display_name"],
                    "elo": standing["elo"],
                    "wins": wins,
                    "losses": losses,
                }
            )

        return leaderboard_data

    def get_event_leaderboard(self) -> dict:
        """Get event leaderboard with active event info."""
        active_event = self._elo_repo.get_active_event()
        standings = self._elo_repo.get_event_standings()

        leaderboard_data = []
        for standing in standings:
            user_id = standing["user_id"]
            leaderboard_data.append(
                {
                    "id": str(user_id),
                    "name": standing["display_name"],
                    "event_elo": standing["event_elo"],
                }
            )

        return {"event": active_event, "leaderboard": leaderboard_data}

    def get_combined_leaderboard(self) -> dict:
        """Get both lifetime and event leaderboards."""
        active_event = self._elo_repo.get_active_event()
        standings = self._elo_repo.get_all_standings_with_event()

        lifetime_data = []
        event_data = []
        event_player_ids = set()

        # Get event start date for season stats
        event_start = None
        if active_event:
            event_start = active_event.get("start_date")

        for standing in standings:
            user_id = standing["user_id"]
            wins = self._match_repo.get_wins_count(user_id)
            losses = self._match_repo.get_losses_count(user_id)

            lifetime_data.append(
                {
                    "id": str(user_id),
                    "name": standing["display_name"],
                    "elo": standing["elo"],
                    "wins": wins,
                    "losses": losses,
                }
            )

            # Include in event if they have non-default ELO
            if standing["event_elo"] != 1500:
                season_wins = 0
                season_losses = 0
                if event_start:
                    season_wins = self._match_repo.get_season_wins_count(
                        user_id, event_start
                    )
                    season_losses = self._match_repo.get_season_losses_count(
                        user_id, event_start
                    )

                event_data.append(
                    {
                        "id": str(user_id),
                        "name": standing["display_name"],
                        "event_elo": standing["event_elo"],
                        "season_wins": season_wins,
                        "season_losses": season_losses,
                    }
                )
                event_player_ids.add(user_id)

        # Also include players who have played this season but still have 1500 ELO
        if event_start:
            season_players = self._match_repo.get_season_players(event_start)
            for user_id in season_players:
                if user_id not in event_player_ids:
                    # Find their display name from standings or use their ID
                    display_name = None
                    for standing in standings:
                        if standing["user_id"] == user_id:
                            display_name = standing["display_name"]
                            break

                    if display_name:
                        season_wins = self._match_repo.get_season_wins_count(
                            user_id, event_start
                        )
                        season_losses = self._match_repo.get_season_losses_count(
                            user_id, event_start
                        )

                        event_data.append(
                            {
                                "id": str(user_id),
                                "name": display_name,
                                "event_elo": 1500,
                                "season_wins": season_wins,
                                "season_losses": season_losses,
                            }
                        )

        # Sort event data by event_elo descending
        event_data.sort(key=lambda x: x["event_elo"], reverse=True)

        return {
            "lifetime": lifetime_data,
            "event": {"info": active_event, "leaderboard": event_data},
        }

    def get_source_leaderboard(self, source: str) -> list[dict]:
        """Get leaderboard for a specific external source with win/loss records."""
        ext_repo = ExternalMatchRepository()
        standings = ext_repo.get_source_elo_standings(source)

        leaderboard_data = []
        for standing in standings:
            user_id = standing["user_id"]
            counts = ext_repo.get_match_count_by_source(user_id, source)
            leaderboard_data.append({
                "id": user_id,
                "name": standing["display_name"],
                "elo": standing["elo"],
                "wins": counts["wins"],
                "losses": counts["losses"],
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
            increments.append(
                {
                    "range": f"{lower}-{upper}",
                    "count": count,
                    "percentage": round(percentage, 2),
                }
            )

        # 2000+ bucket
        count_2000_plus = sum(1 for elo in elos if elo >= 2000)
        percentage_2000_plus = (
            (count_2000_plus / total_players * 100) if count_2000_plus > 0 else 0
        )
        increments.append(
            {
                "range": "2000+",
                "count": count_2000_plus,
                "percentage": round(percentage_2000_plus, 2),
            }
        )

        # 100pt offset (1050-1149, 1150-1249, etc.)
        offset = []
        for lower in range(1050, 2000, 100):
            upper = lower + 99
            count = sum(1 for elo in elos if lower <= elo <= upper)
            percentage = (count / total_players * 100) if count > 0 else 0
            offset.append(
                {
                    "range": f"{lower}-{upper}",
                    "count": count,
                    "percentage": round(percentage, 2),
                }
            )

        # 1950+ bucket
        count_1950_plus = sum(1 for elo in elos if elo >= 1950)
        percentage_1950_plus = (
            (count_1950_plus / total_players * 100) if count_1950_plus > 0 else 0
        )
        offset.append(
            {
                "range": "1950+",
                "count": count_1950_plus,
                "percentage": round(percentage_1950_plus, 2),
            }
        )

        return {
            "increments": list(reversed(increments)),
            "offset": list(reversed(offset)),
            "total_players": total_players,
        }
