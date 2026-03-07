"""Service for admin operations on players and matches."""

import logging

from repositories.elo import EloRepository
from repositories.matches import MatchRepository

logger = logging.getLogger(__name__)


class AdminService:
    """Business logic for admin operations."""

    def __init__(
        self,
        elo_repo: EloRepository | None = None,
        match_repo: MatchRepository | None = None,
    ):
        self._elo_repo = elo_repo or EloRepository()
        self._match_repo = match_repo or MatchRepository()

    def remove_player(self, user_id: int) -> dict:
        """Remove a player from overall_standings.

        Match records are preserved for historical accuracy.
        """
        current_elo = self._elo_repo.get_user_elo(user_id)
        if current_elo is None:
            return {"success": False, "error": "Player not found in standings"}

        deleted = self._elo_repo.delete_player(user_id)
        if deleted:
            logger.info(f"Admin removed player {user_id} from standings")
            return {"success": True, "message": f"Player removed from standings"}
        return {"success": False, "error": "Failed to remove player"}

    def remove_match(self, match_id: int) -> dict:
        """Delete a match and reverse ELO changes for both players."""
        match = self._match_repo.get_match_full_details(match_id)
        if not match:
            return {"success": False, "error": f"Match #{match_id} not found"}

        winner_id = int(match["winner_id"])
        loser_id = int(match["loser_id"])
        winner_elo_change = match["winner_elo_change"]
        loser_elo_change = match["loser_elo_change"]

        # Reverse ELO for winner
        winner_current = self._elo_repo.get_user_elo(winner_id)
        if winner_current is not None:
            new_winner_elo = winner_current - winner_elo_change
            self._elo_repo.upsert_user_elo(
                winner_id, match["winner_name"] or f"User#{winner_id}", new_winner_elo
            )

        # Reverse ELO for loser
        loser_current = self._elo_repo.get_user_elo(loser_id)
        if loser_current is not None:
            new_loser_elo = loser_current - loser_elo_change
            self._elo_repo.upsert_user_elo(
                loser_id, match["loser_name"] or f"User#{loser_id}", new_loser_elo
            )

        deleted = self._match_repo.delete_match(match_id)
        if deleted:
            logger.info(
                f"Admin removed match #{match_id}: "
                f"winner={winner_id} (ELO {winner_elo_change:+d} reversed), "
                f"loser={loser_id} (ELO {loser_elo_change:+d} reversed)"
            )
            return {
                "success": True,
                "message": f"Match #{match_id} deleted and ELO reversed",
                "winner_id": str(winner_id),
                "loser_id": str(loser_id),
                "winner_elo_reversed": winner_elo_change,
                "loser_elo_reversed": loser_elo_change,
            }
        return {"success": False, "error": "Failed to delete match record"}

    def reset_player_elo(self, user_id: int, new_elo: int = 1500) -> dict:
        """Set a player's ELO to a specified value."""
        current_elo = self._elo_repo.get_user_elo(user_id)
        if current_elo is None:
            return {"success": False, "error": "Player not found in standings"}

        reset = self._elo_repo.reset_player_elo(user_id, new_elo)
        if reset:
            logger.info(f"Admin set ELO for {user_id}: {current_elo} -> {new_elo}")
            return {
                "success": True,
                "message": f"ELO updated: {current_elo} -> {new_elo}",
            }
        return {"success": False, "error": "Failed to update ELO"}

    def rename_player(self, user_id: int, new_name: str) -> dict:
        """Rename a player's display name in standings and match history."""
        current_elo = self._elo_repo.get_user_elo(user_id)
        if current_elo is None:
            return {"success": False, "error": "Player not found in standings"}

        renamed = self._elo_repo.rename_player(user_id, new_name)
        if renamed:
            matches_updated = self._match_repo.rename_player_in_matches(user_id, new_name)
            logger.info(
                f"Admin renamed player {user_id} to '{new_name}' "
                f"(standings + {matches_updated} match records)"
            )
            return {"success": True, "message": f"Player renamed to '{new_name}'"}
        return {"success": False, "error": "Failed to rename player"}
