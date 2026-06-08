"""Service for external match reporting (no ELO impact)."""

import logging
from datetime import datetime

from repositories.external_matches import ExternalMatchRepository
from services.curiosa import CuriosaService

logger = logging.getLogger(__name__)


class ExternalMatchService:
    """Business logic for external match reporting.

    External matches are stored in a dedicated table and included in
    the stats pool (win/loss counts, match history) but do NOT affect
    ELO ratings.
    """

    def __init__(
        self,
        external_repo: ExternalMatchRepository | None = None,
        curiosa: CuriosaService | None = None,
    ):
        self._external_repo = external_repo or ExternalMatchRepository()
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
        2. Insert into external_matches table

        No ELO calculations or updates are performed.

        Returns dict with report details.
        """
        # Fetch deck data from Curiosa
        json_deck_data_winner = self._curiosa.fetch_deck_data(winner_deck_url)
        json_deck_data_loser = self._curiosa.fetch_deck_data(loser_deck_url)

        # Insert external match record (no ELO)
        timestamp = datetime.now().isoformat()
        report_id = self._external_repo.insert(
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
        )

        logger.info(
            f"External match recorded: report_id={report_id}, source={source}, "
            f"winner={winner_id}, loser={loser_id}"
        )

        return {
            "report_id": report_id,
            "winner_id": winner_id,
            "loser_id": loser_id,
            "source": source,
            "timestamp": timestamp,
        }
