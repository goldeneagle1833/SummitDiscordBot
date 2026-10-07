"""
Migration: Move bracket (top cut) games out of the running season.

Bracket games used to be logged to match_records, where the running season
counts them. They now go to match_records_archive under the season the
bracket followed; this moves the ones logged before that change. Safe to run
on every startup.

Run with: python migrations/archive_bracket_matches.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)


def archive_bracket_matches() -> int:
    from services.brackets import BracketService

    return BracketService().archive_existing_records()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"Moved {archive_bracket_matches()} bracket matches into the archive")
