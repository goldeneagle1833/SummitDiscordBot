"""Explorer Standings service — event import and leaderboard computation."""

import json
import logging
import re
import statistics

import requests

logger = logging.getLogger(__name__)

CARDEIO_BASE = "https://api.carde.io/api/play"
SORCERY_GAME_ID = "74fac80c-c965-476d-9f2e-f6f1b2f35123"
CARDEIO_HEADERS = {"game-id": SORCERY_GAME_ID}
SORCERY_EVENT_URL_RE = re.compile(
    r"https?://play\.sorcerytcg\.com/events/([0-9a-f-]{36})", re.IGNORECASE
)

DEFAULT_POINTS_CONFIG = {
    "participation": 10,
    "bonus_pathfinder": {"0": 5, "1": 4, "2": 3},
    "persecutor": {"1": 10, "2": 5, "3": 4, "4": 4, "5": 3, "6": 3, "7": 2, "8": 2},
    "trials_threshold": 10,
}


class ExplorerFetchError(Exception):
    """Raised when carde.io API call fails."""


class ExplorerService:
    def fetch_event_data(self, url: str) -> dict:
        """Fetch and structure event data from a sorcerytcg.com event URL.

        Returns a dict with keys:
          event_name, event_date, total_players, venue_name, play_format,
          top_cut_size, cardeio_event_id, cardeio_swiss_phase_id,
          cardeio_final_tournament_id, results
        """
        match = SORCERY_EVENT_URL_RE.match(url.strip())
        if not match:
            raise ValueError(
                "URL must be in the format https://play.sorcerytcg.com/events/{uuid}"
            )
        event_uuid = match.group(1)

        # Try as activity ID first (returns phases directly), fall back to events
        data = self._fetch_activity_or_event(event_uuid)
        phases = data.get("phases", {})

        # Identify Swiss phase (stage "1") and final phase (highest stage number)
        swiss_phase = None
        final_phase = None
        highest_stage = 0

        for stage_key, phase_list in phases.items():
            stage_num = int(stage_key)
            for phase in phase_list:
                if stage_num == 1:
                    swiss_phase = phase
                if stage_num > highest_stage:
                    highest_stage = stage_num
                    final_phase = phase

        if swiss_phase is None:
            raise ExplorerFetchError("No Swiss phase (stage 1) found in event data")

        swiss_phase_id = swiss_phase["id"]
        swiss_tournament_id = swiss_phase.get("tournament", {}).get("id")

        final_tournament_id = None
        if final_phase and final_phase["id"] != swiss_phase["id"]:
            final_tournament_id = final_phase.get("tournament", {}).get("id")

        # Fetch Swiss roster for full player list + win counts
        swiss_roster = self._fetch_roster(swiss_phase_id)

        # Fetch final standings if a top-cut exists
        top_cut_standings = {}
        if final_tournament_id:
            top_cut_standings = self._fetch_final_standings(final_tournament_id)

        # When no top cut, use Swiss tournament standings for proper placement order
        swiss_standings = {}
        if not final_tournament_id and swiss_tournament_id:
            swiss_standings = self._fetch_final_standings(swiss_tournament_id)

        results = self._merge_standings(swiss_roster, top_cut_standings, swiss_standings)

        event_info = data.get("event", {})
        owner = event_info.get("owner", {})
        venue_name = owner.get("name")

        # Derive play_format from configuration
        play_format = None
        config = data.get("configuration", {})
        tournaments_config = config.get("tournaments", [])
        if tournaments_config:
            fmt = tournaments_config[0].get("gameplayFormatId")
            play_format = fmt  # raw ID; display name not available from this endpoint

        # Prefer event-level date
        event_date = (event_info.get("startsAt") or data.get("startsAt") or "")
        if event_date:
            event_date = event_date[:10]  # YYYY-MM-DD

        return {
            "cardeio_event_id": event_uuid,
            "cardeio_swiss_phase_id": swiss_phase_id,
            "cardeio_final_tournament_id": final_tournament_id,
            "event_name": event_info.get("name") or data.get("name", ""),
            "event_date": event_date or None,
            "total_players": len(swiss_roster),
            "venue_name": venue_name,
            "play_format": play_format,
            "top_cut_size": len(top_cut_standings),
            "results": results,
        }

    def _fetch_activity_or_event(self, uuid: str) -> dict:
        """Try fetching as activity first, then as event.

        The sorcerytcg.com URL can contain either an activity ID or event ID.
        The /activities/ endpoint returns phases directly.
        """
        # Try as activity
        try:
            resp = requests.get(
                f"{CARDEIO_BASE}/activities/{uuid}",
                headers=CARDEIO_HEADERS,
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                if data.get("phases"):
                    return data
        except requests.exceptions.RequestException:
            pass

        # Try as event (may contain multiple activities)
        try:
            resp = requests.get(
                f"{CARDEIO_BASE}/events/{uuid}",
                headers=CARDEIO_HEADERS,
                timeout=10,
            )
        except requests.exceptions.RequestException as exc:
            raise ExplorerFetchError(f"Network error fetching event: {exc}") from exc

        if resp.status_code != 200:
            raise ExplorerFetchError(
                f"carde.io returned {resp.status_code} for {uuid}"
            )

        data = resp.json().get("data", {})
        if data.get("phases"):
            return data

        # If the event endpoint returns activities list, fetch the first one
        activities = data.get("activities", [])
        if activities:
            activity_id = activities[0].get("id") if isinstance(activities[0], dict) else activities[0]
            try:
                resp2 = requests.get(
                    f"{CARDEIO_BASE}/activities/{activity_id}",
                    headers=CARDEIO_HEADERS,
                    timeout=10,
                )
                if resp2.status_code == 200:
                    return resp2.json().get("data", {})
            except requests.exceptions.RequestException as exc:
                raise ExplorerFetchError(f"Network error fetching activity: {exc}") from exc

        # Return whatever we got — caller will handle missing phases
        return data

    def _fetch_roster(self, activity_phase_id: str) -> list[dict]:
        """Fetch all players from a Swiss phase roster, handling pagination."""
        all_players = []
        page = 1

        while True:
            try:
                resp = requests.get(
                    f"{CARDEIO_BASE}/activityPhases/{activity_phase_id}/roster",
                    params={"sortBy": "seed", "page": page},
                    headers=CARDEIO_HEADERS,
                    timeout=10,
                )
            except requests.exceptions.RequestException as exc:
                raise ExplorerFetchError(f"Network error fetching roster: {exc}") from exc

            if resp.status_code != 200:
                raise ExplorerFetchError(
                    f"carde.io returned {resp.status_code} for roster {activity_phase_id}"
                )

            body = resp.json()
            all_players.extend(body.get("data", []))

            pagination = body.get("pagination", {})
            if pagination.get("nextPage"):
                page = pagination["nextPage"]
            else:
                break

        return all_players

    def _fetch_final_standings(self, tournament_id: str) -> dict:
        """Fetch final top-cut standings keyed by carde.io user ID."""
        try:
            resp = requests.get(
                f"{CARDEIO_BASE}/tournaments/{tournament_id}/standings",
                headers=CARDEIO_HEADERS,
                timeout=10,
            )
        except requests.exceptions.RequestException as exc:
            raise ExplorerFetchError(
                f"Network error fetching standings: {exc}"
            ) from exc

        if resp.status_code != 200:
            raise ExplorerFetchError(
                f"carde.io returned {resp.status_code} for standings {tournament_id}"
            )

        standings = {}
        for entry in resp.json().get("data", []):
            user_id = entry.get("user", {}).get("id")
            if user_id:
                standings[user_id] = entry.get("standing")
        return standings

    def _merge_standings(
        self, swiss_roster: list[dict], top_cut_standings: dict,
        swiss_standings: dict | None = None,
    ) -> list[dict]:
        """Merge Swiss roster with optional top-cut standings.

        Top-cut players use their final standing from top_cut_standings.
        When no top cut exists but swiss_standings are provided, those are
        used for placement (overall standings based on performance).
        Each result has: cardeio_user_id, display_name, final_standing, wins,
                         total_players, image_url, team_name
        """
        top_cut_size = len(top_cut_standings)
        total_players = len(swiss_roster)

        results = []
        swiss_rank_offset = top_cut_size  # next standing for non-top-cut players
        non_top_cut = []

        # Collect top-cut and non-top-cut players from Swiss roster
        for player in swiss_roster:
            user = player.get("user", {})
            game_user = player.get("gameUser", {})
            user_id = user.get("id", "")
            display_name = user.get("displayName") or game_user.get("displayName") or ""
            image_url = game_user.get("imageUrl")
            team_name = game_user.get("teamName") or ""
            tie_breakers = player.get("tieBreakers") or {}
            wins = (tie_breakers.get("points") or 0) // 3

            row = {
                "cardeio_user_id": user_id,
                "display_name": display_name,
                "wins": wins,
                "total_players": total_players,
                "image_url": image_url,
                "team_name": team_name,
            }

            if user_id in top_cut_standings:
                row["final_standing"] = top_cut_standings[user_id]
                results.append(row)
            else:
                non_top_cut.append(row)

        # Sort top-cut results by their final standing
        results.sort(key=lambda r: r["final_standing"])

        # Assign standings to non-top-cut players
        if not top_cut_standings and swiss_standings:
            # No top cut — use overall Swiss standings for placement
            for row in non_top_cut:
                row["final_standing"] = swiss_standings.get(row["cardeio_user_id"], total_players)
            non_top_cut.sort(key=lambda r: r["final_standing"])
        else:
            # Top cut exists — assign sequential standings after top cut
            for i, row in enumerate(non_top_cut):
                row["final_standing"] = swiss_rank_offset + i + 1

        results.extend(non_top_cut)
        return results

    def compute_leaderboard(self, season_id: int) -> dict:
        """Compute three-track season leaderboard from stored results.

        Returns full leaderboard response per contracts/explorer-api.md.
        """
        from repositories.explorer import ExplorerRepository

        repo = ExplorerRepository()
        season = repo.get_season(season_id)
        if not season:
            return None

        # Parse points config
        raw_config = season.get("points_config")
        if raw_config:
            try:
                config = json.loads(raw_config) if isinstance(raw_config, str) else raw_config
            except (json.JSONDecodeError, TypeError):
                config = DEFAULT_POINTS_CONFIG
        else:
            config = DEFAULT_POINTS_CONFIG

        participation = config.get("participation", 10)
        bonus_pathfinder = config.get("bonus_pathfinder", {})
        persecutor_config = config.get("persecutor", {})
        trials_threshold = config.get("trials_threshold", 10)

        all_results = repo.get_results_for_season(season_id)

        # Group results by player
        players: dict[str, dict] = {}
        for row in all_results:
            uid = row["cardeio_user_id"]
            if uid not in players:
                players[uid] = {
                    "cardeio_user_id": uid,
                    "display_name": row["display_name"],
                    "image_url": row.get("image_url"),
                    "team_name": row.get("team_name") or "",
                    "pathfinder_total": 0,
                    "persecutor_total": 0,
                    "grand_explorer": 0,
                    "events_played": 0,
                    "event_results": [],
                }

            wins = row.get("wins", 0) or 0
            final_standing = row.get("final_standing")

            pathfinder = participation + bonus_pathfinder.get(str(wins), 0)
            persecutor = persecutor_config.get(str(final_standing), 0) if final_standing else 0
            grand = pathfinder + persecutor

            players[uid]["pathfinder_total"] += pathfinder
            players[uid]["persecutor_total"] += persecutor
            players[uid]["grand_explorer"] += grand
            players[uid]["events_played"] += 1
            players[uid]["event_results"].append({
                "event_id": row.get("event_db_id") or row.get("event_id"),
                "event_name": row.get("event_name"),
                "event_date": row.get("event_date"),
                "final_standing": final_standing,
                "wins": wins,
                "pathfinder": pathfinder,
                "persecutor": persecutor,
                "grand_explorer": grand,
            })

        # Sort: grand_explorer desc, persecutor_total desc, pathfinder_total desc
        sorted_players = sorted(
            players.values(),
            key=lambda p: (
                -p["grand_explorer"],
                -p["persecutor_total"],
                -p["pathfinder_total"],
            ),
        )

        ranked = []
        for i, p in enumerate(sorted_players):
            p["rank"] = i + 1
            p["qualified"] = p["persecutor_total"] >= trials_threshold
            ranked.append(p)

        unique_1_event = sum(1 for p in ranked if p["events_played"] >= 1)
        unique_3_events = sum(1 for p in ranked if p["events_played"] >= 3)

        events_counts = [p["events_played"] for p in ranked]
        median_events = statistics.median(events_counts) if events_counts else 0

        return {
            "season_id": season_id,
            "season_name": season.get("name", ""),
            "points_config": config,
            "players": ranked,
            "unique_players_1_event": unique_1_event,
            "unique_players_3_events": unique_3_events,
            "median_events_attended": median_events,
        }
