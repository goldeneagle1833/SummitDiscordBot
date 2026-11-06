"""Leaderboard service for ELO rankings and distribution."""

import webapp_config
from repositories.elo import EloRepository
from services import provisional
from services.glicko2_season import is_glicko2
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


def top_cut_min_games(event: dict | None) -> int:
    """Ranked games an entry needs to count for top cut (0 = no minimum).

    Glicko-2 seasons (Season 9 on) need TOP_CUT_MIN_GAMES so a 3-0 start
    can't sit in the cut on luck; Elo seasons have no minimum.
    """
    from services.glicko2_season import TOP_CUT_MIN_GAMES, is_glicko2

    return TOP_CUT_MIN_GAMES if is_glicko2(event) else 0


def _entry_games(entry) -> int:
    if entry.get("games") is not None:
        return entry["games"] or 0
    wins = entry.get("wins") if entry.get("wins") is not None else entry.get("season_wins")
    losses = entry.get("losses") if entry.get("losses") is not None else entry.get("season_losses")
    return (wins or 0) + (losses or 0)


def top_cut_eligible(entries, event: dict | None) -> list:
    """Entries with enough games to count for top cut, ladder order kept."""
    need = top_cut_min_games(event)
    return [entry for entry in entries if _entry_games(entry) >= need]


def _flag_top_cut_eligible(rows, event) -> None:
    """Mark each leaderboard row with whether it can count for top cut yet."""
    need = top_cut_min_games(event)
    for row in rows:
        row["top_cut_eligible"] = _entry_games(row) >= need


def mark_provisional_ladder(rows, event, games_by_entry: dict, value_key="event_elo") -> list:
    """Glicko-2 seasons: hide provisional ratings and rank settled entries first.

    ``games_by_entry`` maps each row's ``entry_id`` to its games. Rows get
    ``provisional``, ``provisional_games`` and ``rank`` (None while
    provisional). Elo seasons come back unchanged.
    """
    if not is_glicko2(event):
        return rows
    for row in rows:
        provisional.mark(row, games_by_entry.get(row["entry_id"], 0), value_keys=(value_key,))
    return provisional.rank_settled_first(rows, value_key)


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
        """Get unified leaderboard from overall_standings with dual ELO support.

        Once lifetime runs on Glicko-2, provisional players show no ELO and
        no rank (see services/provisional.py) and come after settled ones.
        """
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

        return self._mark_lifetime(leaderboard_data, ("elo", "online_elo"))

    def _mark_lifetime(self, rows, value_keys) -> list[dict]:
        """Glicko-2 lifetime: hide provisional ratings and rank settled players first."""
        if not provisional.lifetime_is_glicko2(self._elo_repo._db_path):
            return rows
        games = provisional.standings_games(self._elo_repo._db_path)
        for row in rows:
            provisional.mark(row, games.get(str(row["id"]), (0, 0))[1], value_keys=value_keys)
        return provisional.rank_settled_first(rows, value_keys[0])

    def _avatar_event_rows(self, active_event, wins_key="wins", losses_key="losses",
                           games: dict | None = None) -> list[dict]:
        """Avatar-mode ladder: one row per (player, avatar) entry, best first.

        ``games``, when given, is filled with {entry_id: games played}.
        """
        event_start = active_event.get("start_date")
        records = self._match_repo.get_season_avatar_records(event_start) if event_start else {}
        voice_games = self._match_repo.get_season_voice_games(event_start) if event_start else {}
        rows = []
        for entry in self._elo_repo.get_avatar_standings(active_event["event_id"]):
            user_id = str(entry["user_id"])
            record = records.get((user_id, entry["avatar"]), {"wins": 0, "losses": 0})
            if games is not None:
                games[f"{user_id}:{entry['avatar']}"] = entry["games_played"]
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

    def _season_games(self, active_event, avatar_only=False) -> int:
        """Ranked games played so far in the running event."""
        event_start = (active_event or {}).get("start_date")
        if not event_start:
            return 0
        return self._match_repo.count_season_games(event_start, avatar_only=avatar_only)

    def get_event_leaderboard(self) -> dict:
        """Get event leaderboard with active event info and season records.

        Player mode: one row per player. Avatar mode: one row per player and
        avatar (each carries `avatar` and a unique `entry_id`).
        """
        active_event = self._elo_repo.get_active_event()
        if is_avatar_mode(active_event):
            games = {}
            rows = self._avatar_event_rows(active_event, games=games)
            _flag_top_cut_eligible(rows, active_event)
            rows = mark_provisional_ladder(rows, active_event, games)
            return {
                "event": active_event,
                "leaderboard": rows,
                "total_games": self._season_games(active_event, avatar_only=True),
                "voice_requirement": voice_requirement(),
                "top_cut_min_games": top_cut_min_games(active_event),
                "provisional_games_needed": provisional.NEEDED if is_glicko2(active_event) else 0,
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

        _flag_top_cut_eligible(leaderboard_data, active_event)
        leaderboard_data = mark_provisional_ladder(
            leaderboard_data, active_event, self._season_games_by_player(active_event)
        )
        return {
            "event": active_event,
            "leaderboard": leaderboard_data,
            "total_games": self._season_games(active_event),
            "voice_requirement": voice_requirement(),
            "top_cut_min_games": top_cut_min_games(active_event),
            "provisional_games_needed": provisional.NEEDED if is_glicko2(active_event) else 0,
        }

    def _season_games_by_player(self, event) -> dict:
        """{user_id: season games} for a Glicko-2 season (empty otherwise)."""
        if not is_glicko2(event):
            return {}
        return {
            uid: games[0]
            for uid, games in provisional.standings_games(self._elo_repo._db_path).items()
        }

    def get_avatar_leaderboards(
        self,
        avatar: str | None = None,
        limit: int | None = None,
        rank_by: str = "elo",
        min_games: int = 10,
    ) -> dict:
        """The season ladder split per avatar (Avatar-mode events).

        One list per avatar, best entry first, each entry numbered within its
        avatar and carrying its place on the full ladder too. Player-mode
        events have no per-avatar ladder, so ``avatars`` is empty then.
        ``avatar`` narrows to one avatar (case-insensitive); ``limit`` caps
        each list.

        ``rank_by`` orders each avatar's list: ``"elo"`` (default) is the season
        Elo ladder order; ``"avatar_score"`` is the same Avatar Score the Top
        Players page uses. Either way, entries with at least ``min_games`` games
        rank ahead of the rest (``0`` turns the minimum off).
        """
        from routes.api.avatars import calculate_avatar_score

        data = self.get_event_leaderboard()
        event = data["event"]
        glicko = is_glicko2(event)
        groups: dict[str, list[dict]] = {}
        if is_avatar_mode(event):
            for overall_rank, row in enumerate(data["leaderboard"], 1):
                extra = {}
                if glicko:
                    # Provisional entries: no rating, no rank (see services/provisional.py)
                    overall_rank = row["rank"]
                    extra = {"provisional": row["provisional"],
                             "provisional_games": row["provisional_games"]}
                groups.setdefault(row["avatar"], []).append(
                    {
                        **extra,
                        "overall_rank": overall_rank,
                        "user_id": row["id"],
                        "display_name": row["name"],
                        "elo": row["event_elo"],
                        "avatar_score": calculate_avatar_score(row["wins"], row["losses"]),
                        "games": row["wins"] + row["losses"],
                        "wins": row["wins"],
                        "losses": row["losses"],
                        "voice_games": row["voice_games"],
                    }
                )
        for entries in groups.values():
            if rank_by == "avatar_score":
                # Stable sort: equal scores keep their Elo ladder order
                entries.sort(
                    key=lambda e: (
                        e["games"] >= min_games,
                        e["avatar_score"],
                        e["wins"] / e["games"] if e["games"] else 0,
                        e["wins"],
                    ),
                    reverse=True,
                )
            else:
                # Stable sort: Elo ladder order within each side of the minimum
                entries.sort(key=lambda e: e["games"] >= min_games, reverse=True)
            if glicko:
                # Stable: provisional entries go last and take no rank
                entries.sort(key=lambda e: e["provisional"])
            rank = 0
            for entry in entries:
                if entry.get("provisional"):
                    entry["rank"] = None
                    continue
                rank += 1
                entry["rank"] = rank
        wanted = avatar.strip().casefold() if avatar else None
        avatars = [
            {
                "avatar": name,
                "players": len(entries),
                "entries": entries[:limit] if limit else entries,
            }
            for name, entries in sorted(groups.items())
            if wanted is None or name.casefold() == wanted
        ]
        return {
            "event": event,
            "elo_mode": (event or {}).get("elo_mode", "player"),
            "rank_by": rank_by,
            "min_games": min_games,
            "avatars": avatars,
            "voice_requirement": voice_requirement(),
        }

    def get_combined_leaderboard(self) -> dict:
        """Get unified lifetime and event leaderboards."""
        active_event = self._elo_repo.get_active_event()
        standings = self._elo_repo.get_all_standings_with_event()

        # Lifetime section: unified (all sources)
        lifetime_data = self.get_leaderboard()

        if is_avatar_mode(active_event):
            games = {}
            rows = self._avatar_event_rows(
                active_event, wins_key="season_wins", losses_key="season_losses", games=games
            )
            _flag_top_cut_eligible(rows, active_event)
            rows = mark_provisional_ladder(rows, active_event, games)
            return {
                "lifetime": lifetime_data,
                "event": {
                    "info": active_event,
                    "leaderboard": rows,
                    "voice_requirement": voice_requirement(),
                    "top_cut_min_games": top_cut_min_games(active_event),
                    "provisional_games_needed": provisional.NEEDED if is_glicko2(active_event) else 0,
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
        _flag_top_cut_eligible(event_data, active_event)
        event_data = mark_provisional_ladder(
            event_data, active_event, self._season_games_by_player(active_event)
        )

        return {
            "lifetime": lifetime_data,
            "event": {
                "info": active_event,
                "leaderboard": event_data,
                "voice_requirement": voice_requirement(),
                "top_cut_min_games": top_cut_min_games(active_event),
                "provisional_games_needed": provisional.NEEDED if is_glicko2(active_event) else 0,
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
        return self._mark_lifetime(leaderboard_data, ("elo",))

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
        if provisional.lifetime_is_glicko2(self._elo_repo._db_path):
            # Provisional Glicko-2 lifetime ratings are not shown anywhere
            games = provisional.standings_games(self._elo_repo._db_path)
            elos = [
                elo for uid, elo in self._elo_repo.get_all_elos_by_user()
                if not provisional.is_provisional(games.get(str(uid), (0, 0))[1])
            ]
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
