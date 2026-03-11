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

    def remove_player(self, user_id: str) -> dict:
        """Remove a player from both overall_standings and paper_standings.

        Match records are preserved for historical accuracy.
        """
        # Try bot standings first
        bot_elo = self._elo_repo.get_user_elo(user_id)
        paper_elo = self._elo_repo.get_user_paper_elo(str(user_id))

        if bot_elo is None and paper_elo is None:
            return {"success": False, "error": "Player not found in any standings"}

        removed_from = []
        if bot_elo is not None:
            if self._elo_repo.delete_player(user_id):
                removed_from.append(f"online (ELO {bot_elo})")
        if paper_elo is not None:
            if self._elo_repo.delete_paper_player(str(user_id)):
                removed_from.append(f"paper (ELO {paper_elo})")

        if removed_from:
            logger.info(f"Admin removed player {user_id} from: {', '.join(removed_from)}")
            return {"success": True, "message": f"Player removed from {', '.join(removed_from)}"}
        return {"success": False, "error": "Failed to remove player"}

    def remove_match(self, match_id: str) -> dict:
        """Delete a match and reverse ELO changes. Handles both bot and web matches."""
        is_web = str(match_id).startswith("web_")

        if is_web:
            return self._remove_web_match(match_id)
        else:
            return self._remove_bot_match(match_id)

    def _remove_bot_match(self, match_id: str) -> dict:
        """Remove a bot match (from match_records) and reverse ELO in overall_standings."""
        try:
            numeric_id = int(match_id)
        except (ValueError, TypeError):
            return {"success": False, "error": f"Invalid bot match ID: {match_id}"}

        match = self._match_repo.get_match_full_details(numeric_id)
        if not match:
            return {"success": False, "error": f"Match #{match_id} not found in bot records"}

        winner_id = match["winner_id"]
        loser_id = match["loser_id"]
        winner_elo_change = match["winner_elo_change"]
        loser_elo_change = match["loser_elo_change"]

        # Reverse ELO for winner
        try:
            winner_current = self._elo_repo.get_user_elo(winner_id)
            if winner_current is not None:
                new_winner_elo = winner_current - winner_elo_change
                self._elo_repo.upsert_user_elo(
                    winner_id, match["winner_name"] or f"User#{winner_id}", new_winner_elo
                )
        except Exception as e:
            logger.warning(f"Could not reverse winner ELO: {e}")

        # Reverse ELO for loser
        try:
            loser_current = self._elo_repo.get_user_elo(loser_id)
            if loser_current is not None:
                new_loser_elo = loser_current - loser_elo_change
                self._elo_repo.upsert_user_elo(
                    loser_id, match["loser_name"] or f"User#{loser_id}", new_loser_elo
                )
        except Exception as e:
            logger.warning(f"Could not reverse loser ELO: {e}")

        deleted = self._match_repo.delete_match(numeric_id)
        if deleted:
            logger.info(
                f"Admin removed bot match #{match_id}: "
                f"winner={winner_id} (ELO {winner_elo_change:+d} reversed), "
                f"loser={loser_id} (ELO {loser_elo_change:+d} reversed)"
            )
            return {
                "success": True,
                "message": f"Bot match #{match_id} deleted and ELO reversed",
                "winner_id": str(winner_id),
                "loser_id": str(loser_id),
                "winner_elo_reversed": winner_elo_change,
                "loser_elo_reversed": loser_elo_change,
            }
        return {"success": False, "error": "Failed to delete match record"}

    def _remove_web_match(self, match_id: str) -> dict:
        """Remove a web match (from match_reports_web) and reverse paper ELO."""
        match = self._match_repo.get_web_match_full_details(match_id)
        if not match:
            return {"success": False, "error": f"Match {match_id} not found in web records"}

        winner_id = str(match["winner_id"])
        loser_id = str(match["loser_id"])
        winner_elo_change = match["winner_elo_change"]
        loser_elo_change = match["loser_elo_change"]

        # Reverse paper ELO for winner
        winner_current = self._elo_repo.get_user_paper_elo(winner_id)
        if winner_current is not None:
            new_winner_elo = winner_current - winner_elo_change
            self._elo_repo.upsert_paper_elo(
                winner_id, match["winner_name"] or f"User#{winner_id}", new_winner_elo
            )

        # Reverse paper ELO for loser
        loser_current = self._elo_repo.get_user_paper_elo(loser_id)
        if loser_current is not None:
            new_loser_elo = loser_current - loser_elo_change
            self._elo_repo.upsert_paper_elo(
                loser_id, match["loser_name"] or f"User#{loser_id}", new_loser_elo
            )

        deleted = self._match_repo.delete_web_match(match_id)
        if deleted:
            logger.info(
                f"Admin removed web match {match_id}: "
                f"winner={winner_id} (paper ELO {winner_elo_change:+d} reversed), "
                f"loser={loser_id} (paper ELO {loser_elo_change:+d} reversed)"
            )
            return {
                "success": True,
                "message": f"Web match {match_id} deleted and paper ELO reversed",
                "winner_id": winner_id,
                "loser_id": loser_id,
                "winner_elo_reversed": winner_elo_change,
                "loser_elo_reversed": loser_elo_change,
            }
        return {"success": False, "error": "Failed to delete web match record"}

    def reset_player_elo(self, user_id: str, new_elo: int = 1500, source: str = "both") -> dict:
        """Set a player's ELO to a specified value.

        Args:
            user_id: Player ID (str to support google_ prefix)
            new_elo: New ELO value
            source: Which standings to reset - 'bot', 'paper', or 'both'
        """
        results = []

        if source in ("bot", "both"):
            current_bot = self._elo_repo.get_user_elo(user_id)
            if current_bot is not None:
                if self._elo_repo.reset_player_elo(user_id, new_elo):
                    results.append(f"online: {current_bot} -> {new_elo}")

        if source in ("paper", "both"):
            current_paper = self._elo_repo.get_user_paper_elo(str(user_id))
            if current_paper is not None:
                if self._elo_repo.reset_paper_elo(str(user_id), new_elo):
                    results.append(f"paper: {current_paper} -> {new_elo}")

        if not results:
            return {"success": False, "error": "Player not found in standings"}

        msg = "ELO updated - " + ", ".join(results)
        logger.info(f"Admin set ELO for {user_id}: {msg}")
        return {"success": True, "message": msg}

    def rename_player(self, user_id: str, new_name: str) -> dict:
        """Rename a player's display name in all standings and match history."""
        renamed_any = False

        # Rename in bot standings
        bot_elo = self._elo_repo.get_user_elo(user_id)
        if bot_elo is not None:
            if self._elo_repo.rename_player(user_id, new_name):
                renamed_any = True
            bot_matches = self._match_repo.rename_player_in_matches(user_id, new_name)
        else:
            bot_matches = 0

        # Rename in paper standings
        paper_elo = self._elo_repo.get_user_paper_elo(str(user_id))
        if paper_elo is not None:
            if self._elo_repo.rename_paper_player(str(user_id), new_name):
                renamed_any = True

        # Rename in web match records
        web_matches = self._match_repo.rename_player_in_web_matches(str(user_id), new_name)

        if renamed_any:
            logger.info(
                f"Admin renamed player {user_id} to '{new_name}' "
                f"(bot matches: {bot_matches}, web matches: {web_matches})"
            )
            return {"success": True, "message": f"Player renamed to '{new_name}'"}

        if bot_matches + web_matches > 0:
            return {"success": True, "message": f"Player renamed in {bot_matches + web_matches} match records"}

        return {"success": False, "error": "Player not found in any standings"}
