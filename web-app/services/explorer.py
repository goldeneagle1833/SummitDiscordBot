"""Explorer Standings service — event import and leaderboard computation."""

import json
import logging
import re
import statistics
from collections import Counter

import requests

logger = logging.getLogger(__name__)

SORCERY_TRPC_BASE = "https://sorcerytcg.com/api/trpc"
SORCERY_EVENT_URL_RE = re.compile(
    r"https?://(?:play\.)?sorcerytcg\.com/events/([A-Za-z0-9_-]+)", re.IGNORECASE
)

DEFAULT_POINTS_CONFIG = {
    "participation": 10,
    "bonus_pathfinder": {"0": 5, "1": 4, "2": 3},
    "persecutor": {"1": 10, "2": 5, "3": 4, "4": 4, "5": 3, "6": 3, "7": 2, "8": 2},
    "trials_threshold": 10,
}


class ExplorerFetchError(Exception):
    """Raised when sorcerytcg.com API call fails."""


def _normalize_name(name: str) -> str:
    """Lowercase, strip whitespace and common separators for fuzzy matching."""
    return re.sub(r"[\s_\-\.]+", "", name.strip().lower())


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
                "URL must be in the format https://sorcerytcg.com/events/{id}"
            )
        event_id = match.group(1)

        event = self._fetch_event_trpc(event_id)

        players_data = event.get("players", [])

        # Derive play format from phases
        phases = event.get("phases", [])
        play_format = None
        for phase in phases:
            if phase.get("type") == "Play":
                play_format = phase.get("format")
                break

        # Fetch the page HTML to get the authoritative standings order from Play Network
        html_standings = self._fetch_page_standings(url)

        results = self._build_results(players_data, html_standings)

        # Extract venue name from store or owner
        venue_name = None
        store = event.get("store")
        if store:
            venue_name = store.get("name")
        if not venue_name:
            owner = event.get("owner")
            if owner:
                venue_name = owner.get("name")

        event_date = (event.get("startsAt") or "")
        if event_date:
            event_date = event_date[:10]  # YYYY-MM-DD

        return {
            "event_id": event_id,
            "event_name": event.get("title", ""),
            "event_date": event_date or None,
            "total_players": len([p for p in players_data if p.get("status") != "Dropped" or p.get("seats")]),
            "venue_name": venue_name,
            "play_format": play_format,
            "top_cut_size": event.get("topcut") or 0,
            "results": results,
        }

    def _fetch_page_standings(self, url: str) -> dict[str, int]:
        """Fetch the event page HTML and parse the Play Network standings order.

        Returns a dict mapping display_name -> position (1-indexed).
        Returns empty dict if parsing fails (caller falls back to algorithmic ranking).
        """
        try:
            resp = requests.get(
                url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}
            )
            if resp.status_code != 200:
                logger.warning("Failed to fetch page standings: HTTP %s", resp.status_code)
                return {}
            entries = re.findall(
                r'<span class="w-4 text-center font-title text-lg">(\d+)</span>.*?'
                r'<span class="truncate font-title">(.*?)</span>',
                resp.text,
                re.DOTALL,
            )
            # For duplicate names keep first occurrence (highest/best standing)
            standings = {}
            for pos_str, name in entries:
                name = name.strip()
                if name and name not in standings:
                    standings[name] = int(pos_str)
            if not standings:
                logger.warning("Parsed 0 standings from page HTML — CSS may have changed")
            else:
                logger.info("Parsed %d standings from Play Network page", len(standings))
            return standings
        except Exception as exc:
            logger.warning("Could not parse page standings: %s", exc)
            return {}

    def _fetch_event_trpc(self, event_id: str) -> dict:
        """Fetch event data from sorcerytcg.com tRPC endpoint."""
        params = {
            "batch": "1",
            "input": json.dumps({"0": {"json": {"id": event_id}}}),
        }
        try:
            resp = requests.get(
                f"{SORCERY_TRPC_BASE}/event.get",
                params=params,
                timeout=15,
            )
        except requests.exceptions.RequestException as exc:
            raise ExplorerFetchError(f"Network error fetching event: {exc}") from exc

        if resp.status_code != 200:
            raise ExplorerFetchError(
                f"sorcerytcg.com returned {resp.status_code} for event {event_id}"
            )

        try:
            body = resp.json()
            event = body[0]["result"]["data"]["json"]["event"]
            return event
        except (KeyError, IndexError, TypeError) as exc:
            raise ExplorerFetchError(
                f"Unexpected response format from sorcerytcg.com: {exc}"
            ) from exc

    def _build_results(self, players_data: list, html_standings: dict[str, int]) -> list[dict]:
        """Build results list from the tRPC event players data.

        Standing order comes from html_standings (Play Network page, source of truth).
        Falls back to Swiss score descending if html_standings is empty or a player
        is not found in the HTML (e.g. CSS class names changed).

        Wins = total match wins (Swiss + top-cut), matching Play Network's displayed record.
        """
        player_rows = []

        for player in players_data:
            user = player.get("user", {})
            user_id = user.get("id", "")
            display_name = user.get("displayname") or user.get("username") or ""

            # Avatar image from feature
            image_url = None
            feature = user.get("feature")
            if feature:
                meta = feature.get("meta", {})
                image_url = meta.get("image")

            seats = player.get("seats", [])

            # Skip dropped players with no games played
            if player.get("status") == "Dropped" and not seats:
                continue

            wins = sum(1 for s in seats if s.get("result", {}).get("result") == "Win")
            swiss_score = sum(
                s.get("result", {}).get("score", 0) for s in seats
                if s.get("round", {}).get("phase", {}).get("structure") == "Swiss"
            )

            player_rows.append({
                "cardeio_user_id": user_id,
                "display_name": display_name,
                "wins": wins,
                "swiss_score": swiss_score,
                "image_url": image_url,
                "team_name": "",
            })

        # Sort by Play Network page standings (source of truth).
        # Fall back to Swiss score descending for any player not found in the HTML.
        fallback_rank = len(html_standings) + 1 if html_standings else 1
        player_rows.sort(
            key=lambda r: (
                html_standings.get(r["display_name"], fallback_rank),
                -r["swiss_score"],
            )
        )

        total_players = len(player_rows)

        for i, row in enumerate(player_rows):
            row["final_standing"] = i + 1
            row["total_players"] = total_players
            del row["swiss_score"]

        return player_rows

    def find_potential_duplicates(self) -> list[dict]:
        """Find players that may be duplicates based on normalized name matching.

        Returns groups of players whose names match after normalization,
        excluding pairs that are already aliased.
        """
        from repositories.explorer import ExplorerRepository

        repo = ExplorerRepository()
        all_players = repo.get_all_unique_players()
        alias_map = repo.get_alias_map()

        # Already-linked IDs (both directions)
        linked = set(alias_map.keys()) | set(alias_map.values())

        # Group by normalized name
        name_groups: dict[str, list[dict]] = {}
        for p in all_players:
            norm = _normalize_name(p["display_name"])
            if not norm:
                continue
            name_groups.setdefault(norm, []).append(p)

        duplicates = []
        for norm_name, group in name_groups.items():
            if len(group) < 2:
                continue
            # Filter out groups where all members are already aliased together
            unlinked = [p for p in group if p["cardeio_user_id"] not in alias_map]
            if len(unlinked) < 2 and len(group) < 3:
                continue
            duplicates.append({
                "normalized_name": norm_name,
                "players": group,
            })

        return duplicates

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

        # Build alias map: alias_user_id -> canonical_user_id
        alias_map = repo.get_alias_map()

        # Group results by player (resolving aliases to canonical IDs)
        players: dict[str, dict] = {}
        for row in all_results:
            uid = row["cardeio_user_id"]
            uid = alias_map.get(uid, uid)  # resolve to canonical
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
        events_distribution = [
            {"events_attended": k, "num_players": v}
            for k, v in sorted(Counter(events_counts).items())
        ]

        return {
            "season_id": season_id,
            "season_name": season.get("name", ""),
            "points_config": config,
            "players": ranked,
            "unique_players_1_event": unique_1_event,
            "unique_players_3_events": unique_3_events,
            "median_events_attended": median_events,
            "events_distribution": events_distribution,
        }
