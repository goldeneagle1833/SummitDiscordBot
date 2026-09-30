"""Leaderboard service for ELO rankings and distribution."""

import webapp_config
from repositories.elo import EloRepository
from repositories.matches import MatchRepository
from repositories.user_profiles import UserProfileRepository


def unique_players(entries) -> list:
    """Each player's best entry only, keeping ladder order.

    Top cut belongs to the player: in an Avatar-mode event a second
    qualifying avatar never takes a second slot, so the next unique player
    moves up. In Player mode every entry is already a different player.
    """
    seen = set()
    best = []
    for entry in entries:
        user_id = str(entry.get("user_id", entry.get("id")))
        if user_id in seen:
            continue
        seen.add(user_id)
        best.append(entry)
    return best


def is_avatar_mode(event: dict | None) -> bool:
    return bool(event) and event.get("elo_mode") == "avatar"


def voice_requirement() -> dict:
    """Top-cut voice requirement settings for the season leaderboards."""
    return {
        "min_games": webapp_config.TOP_CUT_MIN_VOICE_GAMES,
        "enforced": webapp_config.TOP_CUT_VOICE_REQUIREMENT_ENFORCED,
    }


class LeaderboardService:
    """Business logic for leaderboard operations."""

    def __init__(
        self,
        elo_repo: EloRepository | None = None,
        match_repo: MatchRepository | None = None,
        profile_repo: UserProfileRepository | None = None,
    ):
        self._elo_repo = elo_repo or EloRepository()
        self._match_repo = match_repo or MatchRepository()
        self._profile_repo = profile_repo or UserProfileRepository()
        self._chosen = None

    def _name(self, user_id, standing_name):
        """The name to show for a player.

        A name set on the site cannot simply be written into the standings and
        left there: the bot rewrites a player's name from Discord every time it
        rates a game, so the choice would be undone by their next match. The
        site applies it when it reads instead.
        """
        if self._chosen is None:
            try:
                self._chosen = self._profile_repo.get_all_custom_display_names()
            except Exception:
                self._chosen = {}
        return self._chosen.get(str(user_id)) or standing_name

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
                    "name": self._name(user_id, standing["display_name"]),
                    "elo": standing["elo"],
                    "paper_elo": standing.get("paper_elo", 1500),
                    "online_elo": standing.get("online_elo", 1500),
                    "primary_mode": standing.get("primary_mode", "Online"),
                    "wins": wins,
                    "losses": losses,
                }
            )

        return leaderboard_data

    def _avatar_event_rows(self, active_event, wins_key="wins", losses_key="losses") -> list[dict]:
        """Avatar-mode ladder: one row per (player, avatar) entry, best first."""
        event_start = active_event.get("start_date")
        records = self._match_repo.get_season_avatar_records(event_start) if event_start else {}
        voice_games = self._match_repo.get_season_voice_games(event_start) if event_start else {}
        rows = []
        for entry in self._elo_repo.get_avatar_standings(active_event["event_id"]):
            user_id = str(entry["user_id"])
            record = records.get((user_id, entry["avatar"]), {"wins": 0, "losses": 0})
            rows.append(
                {
                    "id": user_id,
                    "entry_id": f"{user_id}:{entry['avatar']}",
                    "name": self._name(user_id, entry["display_name"]),
                    "avatar": entry["avatar"],
                    "event_elo": entry["event_elo"],
                    wins_key: record["wins"],
                    losses_key: record["losses"],
                    # Voice games count toward top cut per player, not per avatar
                    "voice_games": voice_games.get(user_id, 0),
                }
            )
        return rows

    def get_event_leaderboard(self) -> dict:
        """Get event leaderboard with active event info and season records.

        Player mode: one row per player. Avatar mode: one row per player and
        avatar (each carries `avatar` and a unique `entry_id`).
        """
        active_event = self._elo_repo.get_active_event()
        if is_avatar_mode(active_event):
            return {
                "event": active_event,
                "leaderboard": self._avatar_event_rows(active_event),
                "voice_requirement": voice_requirement(),
            }
        standings = self._elo_repo.get_event_standings()

        season_records = {}
        voice_games = {}
        if active_event:
            event_start = active_event.get("start_date")
            if event_start:
                season_records = self._match_repo.get_season_records(event_start)
                voice_games = self._match_repo.get_season_voice_games(event_start)

        leaderboard_data = []
        for standing in standings:
            user_id = standing["user_id"]
            record = season_records.get(str(user_id))
            # Only include players who have played matches in the event
            if record:
                leaderboard_data.append(
                    {
                        "id": str(user_id),
                        "entry_id": str(user_id),
                        "name": self._name(user_id, standing["display_name"]),
                        "avatar": None,
                        "event_elo": standing["event_elo"],
                        "wins": record["wins"],
                        "losses": record["losses"],
                        "voice_games": voice_games.get(str(user_id), 0),
                    }
                )

        return {
            "event": active_event,
            "leaderboard": leaderboard_data,
            "voice_requirement": voice_requirement(),
        }

    def get_combined_leaderboard(self) -> dict:
        """Get unified lifetime and event leaderboards."""
        active_event = self._elo_repo.get_active_event()
        standings = self._elo_repo.get_all_standings_with_event()

        # Lifetime section: unified (all sources)
        lifetime_data = self.get_leaderboard()

        if is_avatar_mode(active_event):
            return {
                "lifetime": lifetime_data,
                "event": {
                    "info": active_event,
                    "leaderboard": self._avatar_event_rows(
                        active_event, wins_key="season_wins", losses_key="season_losses"
                    ),
                    "voice_requirement": voice_requirement(),
                },
            }

        event_data = []
        event_player_ids = set()

        # Get event start date for season stats and participant list
        event_start = None
        season_records = {}
        voice_games = {}
        if active_event:
            event_start = active_event.get("start_date")
            if event_start:
                season_records = self._match_repo.get_season_records(event_start)
                voice_games = self._match_repo.get_season_voice_games(event_start)

        for standing in standings:
            user_id = standing["user_id"]
            record = season_records.get(str(user_id))

            # Include in event if they have played matches in the event period
            if record:
                event_data.append(
                    {
                        "id": str(user_id),
                        "entry_id": str(user_id),
                        "name": self._name(user_id, standing["display_name"]),
                        "avatar": None,
                        "event_elo": standing["event_elo"],
                        "season_wins": record["wins"],
                        "season_losses": record["losses"],
                        "voice_games": voice_games.get(str(user_id), 0),
                    }
                )
                event_player_ids.add(user_id)

        # Sort event data by event_elo descending
        event_data.sort(key=lambda x: x["event_elo"], reverse=True)

        return {
            "lifetime": lifetime_data,
            "event": {
                "info": active_event,
                "leaderboard": event_data,
                "voice_requirement": voice_requirement(),
            },
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
                "name": self._name(stat["user_id"], stat["display_name"]),
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
                    "name": self._name(user_id, standing["display_name"]),
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
                        "name": self._name(user_id, standing["display_name"]),
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
                    "name": self._name(user_id, standing["display_name"]),
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
