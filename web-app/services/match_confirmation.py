"""Service layer for match confirmation business logic."""

from typing import Optional

from repositories.match_confirmation import MatchConfirmationRepository


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
