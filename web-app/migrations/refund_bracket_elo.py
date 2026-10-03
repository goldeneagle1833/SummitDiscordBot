"""
Migration: Give back the ELO that bracket (top cut) games moved.

Bracket games no longer affect any ELO. Matches settled before that change
moved lifetime ELO; this refunds each one exactly once and relabels its match
history row as a top cut game. Safe to run on every startup.

Run with: python migrations/refund_bracket_elo.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)


def refund_bracket_elo() -> int:
    from services.brackets import BracketService

    return BracketService().refund_applied_elo()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"Refunded {refund_bracket_elo()} bracket matches")
