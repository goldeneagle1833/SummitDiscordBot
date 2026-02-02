"""Match service for match history and reporting."""

import json
from repositories.matches import MatchRepository


class MatchService:
    """Business logic for match operations."""

    def __init__(self, match_repo: MatchRepository | None = None):
        self._match_repo = match_repo or MatchRepository()

    def get_match_history(self, date: str | None = None) -> list[dict]:
        """Get match history, optionally filtered by date."""
        if date:
            return self._match_repo.get_matches_by_date(date)
        return self._match_repo.get_recent_matches(hours=24)

    def get_available_dates(self) -> list[str]:
        """Get dates that have match data."""
        return self._match_repo.get_available_dates()

    def get_deck_snapshot(self, match_id: int, player_id: str) -> dict | None:
        """Get deck snapshot for a specific player in a match."""
        match = self._match_repo.get_match_by_id(match_id)

        if not match:
            return None

        winner_id = match["winner_id"]
        loser_id = match["loser_id"]
        winner_name = match["winner_name"]
        loser_name = match["loser_name"]
        timestamp = match["timestamp"]
        old_json_deck = match.get("old_json_deck")
        winner_json = match.get("winner_json")
        loser_json = match.get("loser_json")

        player_id_str = str(player_id)

        if player_id_str == winner_id:
            # Only use winner-specific deck data; don't fall back to old_json_deck
            # because it might belong to the loser (whoever reported the match)
            deck_json = winner_json if winner_json and winner_json != "{}" else None
            player_name = winner_name
            result = "Win"
            opponent_name = loser_name
        elif player_id_str == loser_id:
            # Only use loser-specific deck data; don't fall back to old_json_deck
            # because it might belong to the winner (whoever reported the match)
            deck_json = loser_json if loser_json and loser_json != "{}" else None
            player_name = loser_name
            result = "Loss"
            opponent_name = winner_name
        else:
            return {"error": "Player not found in this match"}

        if not deck_json or deck_json == "{}":
            return {"error": "No deck data available for this match"}

        try:
            deck_data = json.loads(deck_json)
        except json.JSONDecodeError:
            return {"error": "Invalid deck data"}

        return {
            "match_id": match_id,
            "player_name": player_name,
            "opponent_name": opponent_name,
            "result": result,
            "date": timestamp,
            "deck": deck_data,
        }
