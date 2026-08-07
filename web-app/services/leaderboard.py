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
        """Get unified leaderboard from overall_standings with dual ELO support."""
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
                    "paper_elo": standing.get("paper_elo", 1500),
                    "online_elo": standing.get("online_elo", 1500),
                    "primary_mode": standing.get("primary_mode", "Online"),
                    "wins": wins,
                    "losses": losses,
                }
            )

        return leaderboard_data

    def get_event_leaderboard(self) -> dict:
        """Get event leaderboard with active event info."""
        active_event = self._elo_repo.get_active_event()
        if active_event and active_event.get("avatar_specific"):
            standings = self._elo_repo.get_avatar_event_standings(
                active_event["event_id"], "online"
            )
            return {
                "event": active_event,
                "leaderboard": [
                    {
                        "id": str(row["user_id"]),
                        "name": row["user_display_name"],
                        "avatar": row["avatar_name"],
                        "event_elo": row["event_elo"],
                    }
                    for row in standings
                ],
            }
        standings = self._elo_repo.get_event_standings()

        # Get event participants from match_records
        event_participants = set()
        if active_event:
            event_start = active_event.get("start_date")
            if event_start:
                event_participants = set(self._match_repo.get_season_players(event_start))

        leaderboard_data = []
        for standing in standings:
            user_id = standing["user_id"]
            # Only include players who have played matches in the event
            if user_id in event_participants:
                leaderboard_data.append(
                    {
                        "id": str(user_id),
                        "name": standing["display_name"],
                        "event_elo": standing["event_elo"],
                    }
                )

        return {"event": active_event, "leaderboard": leaderboard_data}

    def get_combined_leaderboard(self) -> dict:
        """Get unified lifetime and event leaderboards."""
        active_event = self._elo_repo.get_active_event()
        standings = self._elo_repo.get_all_standings_with_event()

        # Lifetime section: unified (all sources)
        lifetime_data = self.get_leaderboard()

        if active_event and active_event.get("avatar_specific"):
            standings = self._elo_repo.get_avatar_event_standings(
                active_event["event_id"], "online"
            )
            return {
                "lifetime": lifetime_data,
                "event": {
                    "info": active_event,
                    "leaderboard": [
                        {
                            "id": str(row["user_id"]),
                            "name": row["user_display_name"],
                            "avatar": row["avatar_name"],
                            "event_elo": row["event_elo"],
                        }
                        for row in standings
                    ],
                },
            }

        event_data = []
        event_player_ids = set()

        # Get event start date for season stats and participant list
        event_start = None
        event_participants = set()
        if active_event:
            event_start = active_event.get("start_date")
            if event_start:
                event_participants = set(self._match_repo.get_season_players(event_start))

        for standing in standings:
            user_id = standing["user_id"]

            # Include in event if they have played matches in the event period
            if user_id in event_participants:
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

        # Sort event data by event_elo descending
        event_data.sort(key=lambda x: x["event_elo"], reverse=True)

        return {
            "lifetime": lifetime_data,
            "event": {"info": active_event, "leaderboard": event_data},
        }

    def get_source_leaderboard(self, source: str) -> list[dict]:
        """Get leaderboard for a specific source with win/loss records.

        Uses match_records for win/loss and overall_standings for ELO.
        """
        player_stats = self._match_repo.get_source_player_stats(source)
        leaderboard_data = []
        for stat in player_stats:
            # Keep as string to avoid overflow with large Google IDs
            elo = self._elo_repo.get_user_elo(stat["user_id"]) or 1500
            leaderboard_data.append({
                "id": stat["user_id"],
                "name": stat["display_name"],
                "elo": elo,
                "wins": stat["wins"],
                "losses": stat["losses"],
            })
        leaderboard_data.sort(key=lambda x: x["elo"], reverse=True)
        return leaderboard_data

    def get_paper_leaderboard(self) -> list[dict]:
        """Get paper ELO leaderboard from paper_standings with web match win/loss records."""
        standings = self._elo_repo.get_paper_standings()
        leaderboard_data = []
        for standing in standings:
            user_id = standing["user_id"]
            wins = self._match_repo.get_web_wins_count(user_id)
            losses = self._match_repo.get_web_losses_count(user_id)
            leaderboard_data.append(
                {
                    "id": str(user_id),
                    "name": standing["display_name"],
                    "paper_elo": standing["paper_elo"],
                    "paper_event_elo": standing["paper_event_elo"],
                    "wins": wins,
                    "losses": losses,
                }
            )
        return leaderboard_data

    def get_paper_event_leaderboard(self) -> dict:
        """Get paper event leaderboard with active event info."""
        active_event = self._elo_repo.get_active_event()
        if active_event and active_event.get("avatar_specific"):
            standings = self._elo_repo.get_avatar_event_standings(
                active_event["event_id"], "paper"
            )
            return {
                "event": active_event,
                "leaderboard": [
                    {
                        "id": str(row["user_id"]),
                        "name": row["user_display_name"],
                        "avatar": row["avatar_name"],
                        "event_elo": row["event_elo"],
                    }
                    for row in standings
                ],
            }
        standings = self._elo_repo.get_paper_standings()

        # Get paper event participants from web match records
        paper_participants = set()
        if active_event:
            event_start = active_event.get("start_date")
            if event_start:
                paper_participants = set(self._match_repo.get_web_season_players(event_start))

        leaderboard_data = []
        for standing in standings:
            user_id = standing["user_id"]
            # Only include players who have played paper matches in the event
            if str(user_id) in paper_participants or user_id in paper_participants:
                leaderboard_data.append(
                    {
                        "id": str(user_id),
                        "name": standing["display_name"],
                        "event_elo": standing["paper_event_elo"],
                    }
                )

        # Sort by event ELO descending
        leaderboard_data.sort(key=lambda x: x["event_elo"], reverse=True)

        return {"event": active_event, "leaderboard": leaderboard_data}

    def get_limited_leaderboard(self, view: str = "lifetime") -> list[dict]:
        """Get limited format ELO leaderboard with win/loss records.

        Args:
            view: "lifetime" uses lifetime_elo and includes archived matches.
                  "season" uses current season elo and live matches only.
        """
        from repositories.limited_repo import (
            get_all_limited_standings,
            get_limited_wins_count,
            get_limited_losses_count,
        )

        use_lifetime = view == "lifetime"
        standings = get_all_limited_standings(use_lifetime=use_lifetime)
        leaderboard_data = []
        for standing in standings:
            user_id = standing["user_id"]
            wins = get_limited_wins_count(user_id, include_archived=use_lifetime)
            losses = get_limited_losses_count(user_id, include_archived=use_lifetime)
            if wins + losses == 0:
                continue
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
