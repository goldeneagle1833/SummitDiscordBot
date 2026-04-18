"""Repository for loading deck data from tournament files and match records.

Used by the Sorcery Deck Rec feature to build the deck corpus for
similarity-based archetype recommendations.
"""

import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from webapp_config import MATCH_RECORDS_DB_PATH, TOP_8_DIR

logger = logging.getLogger(__name__)


_VALID_ELEMENTS = frozenset({"Earth", "Fire", "Water", "Air"})
_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def _extract_elements(spellbook: list) -> frozenset:
    """Return frozenset of valid element strings present in the spellbook."""
    elements = set()
    for card in spellbook:
        if not isinstance(card, dict):
            continue
        val = card.get("elements", "")
        if isinstance(val, str):
            for part in val.split(","):
                part = part.strip()
                if part in _VALID_ELEMENTS:
                    elements.add(part)
    return frozenset(elements)


def _extract_year(text: str) -> int | None:
    """Return the first 20xx year found in text, or None."""
    m = _YEAR_RE.search(text)
    return int(m.group(1)) if m else None


@dataclass
class DeckRecord:
    """Represents a single deck build from any data source."""

    deck_id: str
    deck_name: str
    avatar_name: str
    player_name: str
    event_name: str
    is_seed: bool
    card_names: frozenset
    card_count: int
    curiosa_url: str
    elements: frozenset = field(default_factory=frozenset)
    event_year: int | None = None


class DeckRecRepository:
    """Loads and merges deck data from tournament JSON files and match records DB."""

    CURIOSA_BASE = "https://curiosa.io/decks/"

    def __init__(
        self,
        top8_dir: Path | None = None,
        db_path: Path | None = None,
    ):
        self._top8_dir = top8_dir or TOP_8_DIR
        self._db_path = db_path or MATCH_RECORDS_DB_PATH

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def load_all_decks(self) -> list[DeckRecord]:
        """Load decks from both tournament files and match records DB.

        Tournament seeds take precedence when the same Curiosa deck ID appears
        in both sources. Returns deduplicated list of DeckRecord objects.
        """
        seen_ids: dict[str, DeckRecord] = {}

        # 1. Tournament files — highest quality, become seeds
        for deck in self._load_tournament_decks():
            if deck.deck_id and deck.deck_id not in seen_ids:
                seen_ids[deck.deck_id] = deck

        # 2. Match records — community decks, lower priority
        for deck in self._load_match_decks():
            if deck.deck_id and deck.deck_id not in seen_ids:
                seen_ids[deck.deck_id] = deck

        return list(seen_ids.values())

    # ------------------------------------------------------------------ #
    # Tournament file loading                                              #
    # ------------------------------------------------------------------ #

    def _load_tournament_decks(self) -> list[DeckRecord]:
        """Walk top-8-decks-by-event/ and parse all JSON deck files."""
        decks = []

        if not self._top8_dir.exists():
            logger.warning("TOP_8_DIR not found: %s", self._top8_dir)
            return decks

        for folder in self._top8_dir.iterdir():
            if not folder.is_dir() or folder.name.startswith("_"):
                continue

            json_path = self._best_json_file(folder)
            if json_path is None:
                continue

            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                logger.warning("Failed to read %s: %s", json_path, e)
                continue

            if not isinstance(data, list):
                continue

            for raw in data:
                deck = self._parse_tournament_deck(raw, folder.name)
                if deck:
                    decks.append(deck)

        logger.info("Loaded %d tournament decks from %s", len(decks), self._top8_dir)
        return decks

    def _best_json_file(self, folder: Path) -> Path | None:
        """Return the best JSON file in an event folder (full list > top8)."""
        top8_file = None
        full_file = None

        for f in folder.glob("*.json"):
            name_lower = f.name.lower()
            if "top8" in name_lower or "top 8" in name_lower:
                top8_file = f
            elif f.name.lower().startswith(folder.name.lower()):
                full_file = f

        return full_file or top8_file

    def _parse_tournament_deck(self, raw: dict, event_name: str) -> DeckRecord | None:
        """Parse a single deck dict from a tournament JSON file."""
        try:
            deck_id = str(raw.get("id", "")).strip()
            if not deck_id:
                return None

            card_names = frozenset(
                c["name"].strip().lower()
                for c in raw.get("spellbook", [])
                if isinstance(c, dict) and c.get("name")
            )
            if not card_names:
                return None

            spellbook = raw.get("spellbook", [])
            return DeckRecord(
                deck_id=deck_id,
                deck_name=raw.get("name", "Unnamed Deck") or "Unnamed Deck",
                avatar_name=(raw.get("avatar") or [{}])[0].get("name", "Unknown"),
                player_name=raw.get("username", "Unknown") or "Unknown",
                event_name=event_name,
                is_seed=True,
                card_names=card_names,
                card_count=len(card_names),
                curiosa_url=f"{self.CURIOSA_BASE}{deck_id}",
                elements=_extract_elements(spellbook),
                event_year=_extract_year(event_name),
            )
        except Exception as e:
            logger.debug("Skipping malformed tournament deck: %s", e)
            return None

    # ------------------------------------------------------------------ #
    # Match records DB loading                                             #
    # ------------------------------------------------------------------ #

    def _load_match_decks(self) -> list[DeckRecord]:
        """Query match_records and match_records_archive for community decks."""
        decks = []

        if not self._db_path.exists():
            logger.warning("match_records.db not found: %s", self._db_path)
            return decks

        try:
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            for table in ("match_records_archive", "match_records"):
                rows = self._fetch_match_rows(cur, table)
                for row in rows:
                    for side in ("winner", "losser"):
                        deck = self._parse_match_deck(row, side)
                        if deck:
                            decks.append(deck)

            conn.close()
        except Exception as e:
            logger.error("Failed to load match decks: %s", e)

        logger.info("Loaded %d community deck records from match DB", len(decks))
        return decks

    def _fetch_match_rows(self, cur: sqlite3.Cursor, table: str) -> list:
        """Fetch rows with deck data from the given table."""
        try:
            cur.execute(f"""
                SELECT
                    winner_display_name,
                    losser_display_name,
                    json_deck_data_winner,
                    json_deck_data_loser,
                    curiosa_url_winner,
                    curiosa_url_loser
                FROM {table}
                WHERE
                    (json_deck_data_winner IS NOT NULL AND json_deck_data_winner NOT IN ('', '{{}}'))
                    OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser NOT IN ('', '{{}}'))
            """)
            return cur.fetchall()
        except sqlite3.OperationalError:
            # Table or column may not exist
            return []

    def _parse_match_deck(self, row: sqlite3.Row, side: str) -> DeckRecord | None:
        """Parse winner or loser deck from a match record row."""
        try:
            json_col = f"json_deck_data_{side}"
            url_col = f"curiosa_url_{side}"
            name_col = f"{side}_display_name"

            deck_json_str = row[json_col] if json_col in row.keys() else None
            if not deck_json_str or deck_json_str in ("", "{}"):
                return None

            curiosa_url = (row[url_col] if url_col in row.keys() else None) or ""
            deck_id = self._extract_deck_id(curiosa_url)
            if not deck_id:
                return None

            deck_data = json.loads(deck_json_str)
            card_names = frozenset(
                c["name"].strip().lower()
                for c in deck_data.get("spellbook", [])
                if isinstance(c, dict) and c.get("name")
            )
            if not card_names:
                return None

            avatar_name = (deck_data.get("avatar") or [{}])[0].get("name", "Unknown")
            player_name = (row[name_col] if name_col in row.keys() else None) or "Unknown"

            return DeckRecord(
                deck_id=deck_id,
                deck_name="",
                avatar_name=avatar_name,
                player_name=player_name,
                event_name="",
                is_seed=False,
                card_names=card_names,
                card_count=len(card_names),
                curiosa_url=curiosa_url or f"{self.CURIOSA_BASE}{deck_id}",
                elements=_extract_elements(deck_data.get("spellbook", [])),
                event_year=None,
            )
        except Exception as e:
            logger.debug("Skipping malformed match deck (%s): %s", side, e)
            return None

    def _extract_deck_id(self, url: str) -> str:
        """Extract Curiosa deck ID from a URL like https://curiosa.io/decks/abc123."""
        if not url:
            return ""
        # Handle URLs with query strings: split on ? first
        path = url.split("?")[0].rstrip("/")
        return path.split("/")[-1] if "/" in path else ""
