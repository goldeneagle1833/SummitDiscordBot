"""Service layer for match confirmation business logic."""

import logging
import re
from typing import Optional

from repositories.match_confirmation import MatchConfirmationRepository

# Configure logger for match reporting operations
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MatchConfirmationService:
    """Business logic for match confirmations."""

    def __init__(self, repository: Optional[MatchConfirmationRepository] = None):
        self.repo = repository or MatchConfirmationRepository()

    def create_match_report(
        self,
        submitter_id: int,
        opponent_identification: dict,
        match_result: dict,
        decks: dict,
    ) -> dict:
        """
        Create a new match report and confirmation request.

        Args:
            submitter_id: Discord user ID of submitter
            opponent_identification: {"method": "discord_username"|"discord_id"|"lfg_lookup", "value": ...}
            match_result: {"winner": "self"|"opponent", "final_life": {"self": int, "opponent": int}}
            decks: {"self_deck_url": str|None, "opponent_deck_url": str|None}

        Returns:
            dict: {"success": bool, "confirmation_id": int, "expires_at": int, "opponent": dict}

        Raises:
            ValueError: If validation fails
            RuntimeError: If opponent not found or database error
        """
        # Stub implementation - to be completed in T045-T047
        raise NotImplementedError("create_match_report not yet implemented")

    def process_confirmation(
        self, confirmation_id: int, action: str, user_id: int
    ) -> dict:
        """
        Process a match confirmation (confirm or dispute).

        Args:
            confirmation_id: ID of confirmation to process
            action: 'confirm' or 'dispute'
            user_id: Discord user ID of user taking action

        Returns:
            dict: {"success": bool, "message": str, "elo_changes": dict | None}

        Raises:
            ValueError: If confirmation not found or already processed
            RuntimeError: If ELO update fails
        """
        # Stub implementation - to be completed in T072-T075
        raise NotImplementedError("process_confirmation not yet implemented")

    def auto_confirm_expired(self) -> int:
        """
        Auto-confirm all expired pending confirmations.

        Returns:
            int: Count of confirmations auto-confirmed
        """
        # Stub implementation - to be completed in T076
        raise NotImplementedError("auto_confirm_expired not yet implemented")

    def _finalize_confirmed_match(self, confirmation: dict) -> dict:
        """
        Internal helper to trigger ELO update and create match record.

        Args:
            confirmation: Confirmation record dict

        Returns:
            dict: ELO changes {"winner": {...}, "loser": {...}}
        """
        # Stub implementation - to be completed in T073-T075
        raise NotImplementedError("_finalize_confirmed_match not yet implemented")

    def validate_match_report_input(
        self,
        submitter_id: str,
        opponent_id: str,
        result: str,
        went_first: str,
        submitter_deck_url: Optional[str] = None,
        opponent_deck_url: Optional[str] = None,
    ) -> dict:
        """
        Validate all inputs for a match report submission.

        Args:
            submitter_id: Discord user ID of submitter
            opponent_id: Discord user ID of opponent
            result: Match result ('won' or 'lost')
            went_first: Turn order ('submitter' or 'opponent')
            submitter_deck_url: Optional Curiosa.io deck URL for submitter
            opponent_deck_url: Optional Curiosa.io deck URL for opponent

        Returns:
            dict: {"valid": bool, "errors": dict} where errors maps field names to error messages

        Validation Rules:
            - opponent_id must not equal submitter_id (no self-reporting)
            - result must be 'won' or 'lost'
            - went_first must be 'submitter' or 'opponent'
            - deck URLs (if provided) must match Curiosa.io pattern
        """
        errors = {}

        # Validate opponent selection (no self-reporting)
        if not opponent_id:
            errors["opponent_id"] = "Opponent is required"
        elif str(submitter_id) == str(opponent_id):
            errors["opponent_id"] = "Cannot report a match against yourself"

        # Validate result
        if result not in ("won", "lost"):
            errors["result"] = "Result must be 'won' or 'lost'"

        # Validate turn order
        if went_first not in ("submitter", "opponent"):
            errors["went_first"] = "Turn order must be 'submitter' or 'opponent'"

        # Validate deck URLs (if provided)
        deck_url_pattern = r"^https?://(www\.)?curiosa\.io/decks/[a-zA-Z0-9_-]+$"

        if submitter_deck_url:
            if not re.match(deck_url_pattern, submitter_deck_url):
                errors[
                    "submitter_deck_url"
                ] = "Invalid Curiosa.io deck URL format. Expected: https://curiosa.io/decks/[deck-id]"

        if opponent_deck_url:
            if not re.match(deck_url_pattern, opponent_deck_url):
                errors[
                    "opponent_deck_url"
                ] = "Invalid Curiosa.io deck URL format. Expected: https://curiosa.io/decks/[deck-id]"

        return {"valid": len(errors) == 0, "errors": errors}

    def calculate_winner_loser(
        self, submitter_id: str, opponent_id: str, result: str
    ) -> dict:
        """
        Calculate winner and loser IDs based on match result from submitter's perspective.

        Args:
            submitter_id: Discord user ID of submitter
            opponent_id: Discord user ID of opponent
            result: Match result from submitter's perspective ('won' or 'lost')

        Returns:
            dict: {"winner_id": str, "loser_id": str}

        Example:
            >>> calculate_winner_loser("123", "456", "won")
            {"winner_id": "123", "loser_id": "456"}

            >>> calculate_winner_loser("123", "456", "lost")
            {"winner_id": "456", "loser_id": "123"}
        """
        if result == "won":
            winner_id = str(submitter_id)
            loser_id = str(opponent_id)
        else:  # result == "lost"
            winner_id = str(opponent_id)
            loser_id = str(submitter_id)

        logger.info(
            f"Match result calculated: submitter={submitter_id}, opponent={opponent_id}, "
            f"result={result} → winner={winner_id}, loser={loser_id}"
        )

        return {"winner_id": winner_id, "loser_id": loser_id}
