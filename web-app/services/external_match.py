"""Service for external match reporting and per-source ELO calculation."""

import logging
from datetime import datetime

from repositories.external_matches import ExternalMatchRepository
from services.curiosa import CuriosaService

logger = logging.getLogger(__name__)


def calculate_elo(player_elo: int, opponent_elo: int, did_win: bool, k: int = 32) -> int:
    """
    Calculate new ELO rating using the standard Elo formula.

    Same formula as discord-bot/services/elo_service.py update_elo().
    """
    expected_score = 1 / (1 + 10 ** ((opponent_elo - player_elo) / 400))
    actual_score = 1 if did_win else 0
    new_elo = player_elo + k * (actual_score - expected_score)
    return round(new_elo)


class ExternalMatchService:
    """Business logic for external match reporting with per-source ELO."""

    def __init__(
        self,
        repo: ExternalMatchRepository | None = None,
        curiosa: CuriosaService | None = None,
    ):
        self._repo = repo or ExternalMatchRepository()
        self._curiosa = curiosa or CuriosaService()

    def report_match(
        self,
        winner_id: str,
        loser_id: str,
        winner_deck_url: str,
        loser_deck_url: str,
        source: str,
        winner_name: str | None = None,
        loser_name: str | None = None,
        winner_went_first: str | None = None,
        match_time: int | None = None,
        match_comment: str | None = None,
    ) -> dict:
        """
        Process an external match report:
        1. Fetch deck data from Curiosa
        2. Calculate per-source ELO changes
        3. Update source_elo for both players
        4. Insert the match record

        Returns dict with report details.
        """
        # Fetch deck data from Curiosa
        json_deck_data_winner = self._curiosa.fetch_deck_data(winner_deck_url)
        json_deck_data_loser = self._curiosa.fetch_deck_data(loser_deck_url)

        # Get current source ELOs
        winner_elo = self._repo.get_source_elo(winner_id, source)
        loser_elo = self._repo.get_source_elo(loser_id, source)

        # Calculate new ELOs (K=32, always updates — no event dependency)
        new_winner_elo = calculate_elo(winner_elo, loser_elo, True, k=32)
        new_loser_elo = calculate_elo(loser_elo, winner_elo, False, k=32)

        winner_elo_change = new_winner_elo - winner_elo
        loser_elo_change = new_loser_elo - loser_elo

        # Update source ELOs
        winner_display = winner_name or f"User#{winner_id}"
        loser_display = loser_name or f"User#{loser_id}"
        self._repo.update_source_elo(winner_id, source, winner_display, new_winner_elo)
        self._repo.update_source_elo(loser_id, source, loser_display, new_loser_elo)

        # Insert external match report
        timestamp = datetime.now().isoformat()
        report_id = self._repo.insert_report(
            winner_id=winner_id,
            loser_id=loser_id,
            winner_name=winner_name,
            loser_name=loser_name,
            winner_deck_url=winner_deck_url,
            loser_deck_url=loser_deck_url,
            json_deck_data_winner=json_deck_data_winner,
            json_deck_data_loser=json_deck_data_loser,
            winner_went_first=winner_went_first,
            match_time=match_time,
            match_comment=match_comment,
            source=source,
            timestamp=timestamp,
            winner_elo_change=winner_elo_change,
            loser_elo_change=loser_elo_change,
        )

        logger.info(
            f"External match recorded: report_id={report_id}, source={source}, "
            f"winner={winner_id} ({new_winner_elo}), loser={loser_id} ({new_loser_elo})"
        )

        return {
            "report_id": report_id,
            "winner_id": winner_id,
            "loser_id": loser_id,
            "winner_elo": new_winner_elo,
            "loser_elo": new_loser_elo,
            "winner_elo_change": winner_elo_change,
            "loser_elo_change": loser_elo_change,
            "source": source,
            "timestamp": timestamp,
        }
