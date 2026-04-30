"""Repository for loading deck data from tournament files and match records.

Used by the Sorcery Deck Rec feature to build the deck corpus for
similarity-based archetype recommendations.
"""

import json
import logging
import re
import sqlite3
from collections import Counter
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


def _count_quantities(spellbook: list) -> dict[str, int]:
    """Return a {normalized_card_name: copy_count} dict from a spellbook list."""
    counts: Counter = Counter()
    for card in spellbook:
        if not isinstance(card, dict):
            continue
        name = card.get("name", "")
        if name:
            counts[name.strip().lower()] += 1
    return dict(counts)


def _count_quantities_display(spellbook: list) -> dict[str, int]:
    """Return a {card_name: copy_count} dict preserving original casing."""
    counts: Counter = Counter()
    for card in spellbook:
        if not isinstance(card, dict):
            continue
        name = card.get("name", "")
        if name:
            counts[name.strip()] += 1
    return dict(counts)


def _get_card_details(spellbook: list, atlas: list | None = None) -> list[dict]:
    """Return aggregated card list preserving name, qty, type, and threshold.

    Combines spellbook and atlas so the full deck is represented.
    """
    seen: dict[str, dict] = {}
    for card in list(spellbook) + list(atlas or []):
        if not isinstance(card, dict):
            continue
        name = card.get("name", "").strip()
        if not name:
            continue
        # Curiosa API returns one entry per unique card with a quantity field.
        # Tournament JSON has one entry per copy — treat missing quantity as 1.
        card_qty = int(card.get("quantity") or card.get("qty") or 1)
        if name not in seen:
            seen[name] = {
                "name": name,
                "qty": 0,
                "type": card.get("type", ""),
                "threshold": card.get("threshold") or card.get("cost") or card.get("mana") or 0,
            }
        seen[name]["qty"] += card_qty
    return list(seen.values())


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
    is_admin_rec: bool = False
    # card_name (lowercase) → number of copies in the deck
    card_quantities: dict = field(default_factory=dict)
    # card_name (original casing) → number of copies in the deck
    card_quantities_display: dict = field(default_factory=dict)
    # full card details: [{name, qty, type, threshold}] for spellbook + atlas
    card_details: list = field(default_factory=list)
    primer: str = ""          # short description shown on admin tile
    stars: int | None = None  # 1–3 star rating


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

    def load_seed_decks(self) -> list[DeckRecord]:
        """Load only tournament and admin seed decks (no community match records).

        Faster than load_all_decks() — suitable for similarity lookups where
        community decks aren't needed as reference points.
        """
        seen_ids: dict[str, DeckRecord] = {}
        for deck in self._load_tournament_decks():
            if deck.deck_id and deck.deck_id not in seen_ids:
                seen_ids[deck.deck_id] = deck
        for deck in self._load_admin_decks():
            if not deck.deck_id:
                continue
            if deck.deck_id in seen_ids:
                existing = seen_ids[deck.deck_id]
                existing.is_admin_rec = True
                existing.primer = deck.primer or existing.primer
                existing.stars = deck.stars if deck.stars is not None else existing.stars
            else:
                seen_ids[deck.deck_id] = deck
        return list(seen_ids.values())

    def load_all_decks(self) -> list[DeckRecord]:
        """Load decks from tournament files, admin recommendations, and match records DB.

        Priority order: tournament seeds > admin recs > community match decks.
        Returns deduplicated list of DeckRecord objects.
        """
        seen_ids: dict[str, DeckRecord] = {}

        # 1. Tournament files — highest quality, become seeds
        for deck in self._load_tournament_decks():
            if deck.deck_id and deck.deck_id not in seen_ids:
                seen_ids[deck.deck_id] = deck

        # 2. Admin recommended decks — also seeds
        #    If the deck already exists (e.g. from tournament files), merge
        #    admin metadata so it appears in the Staff Recommendations section.
        for deck in self._load_admin_decks():
            if not deck.deck_id:
                continue
            if deck.deck_id in seen_ids:
                existing = seen_ids[deck.deck_id]
                existing.is_admin_rec = True
                existing.primer = deck.primer or existing.primer
                existing.stars = deck.stars if deck.stars is not None else existing.stars
            else:
                seen_ids[deck.deck_id] = deck

        # 3. Match records — community decks, lower priority
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

            spellbook = raw.get("spellbook", [])
            atlas = raw.get("atlas", [])
            card_names = frozenset(
                c["name"].strip().lower()
                for c in spellbook
                if isinstance(c, dict) and c.get("name")
            )
            if not card_names:
                return None

            card_quantities = _count_quantities(spellbook)
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
                card_quantities=card_quantities,
                card_quantities_display=_count_quantities_display(spellbook),
                card_details=_get_card_details(spellbook, atlas),
            )
        except Exception as e:
            logger.debug("Skipping malformed tournament deck: %s", e)
            return None

    # ------------------------------------------------------------------ #
    # Match records DB loading                                             #
    # ------------------------------------------------------------------ #

    # Column names in match_records/archive — display name uses "losser" (bot typo),
    # but deck data columns use "loser" (single s).
    _MATCH_SIDE_COLS = {
        "winner": ("json_deck_data_winner", "curiosa_url_winner", "winner_display_name"),
        "losser": ("json_deck_data_loser",  "curiosa_url_loser",  "losser_display_name"),
    }

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
            json_col, url_col, name_col = self._MATCH_SIDE_COLS[side]

            deck_json_str = row[json_col] if json_col in row.keys() else None
            if not deck_json_str or deck_json_str in ("", "{}"):
                return None

            curiosa_url = (row[url_col] if url_col in row.keys() else None) or ""
            deck_id = self._extract_deck_id(curiosa_url)
            if not deck_id:
                return None

            deck_data = json.loads(deck_json_str)
            spellbook = deck_data.get("spellbook", [])
            card_names = frozenset(
                c["name"].strip().lower()
                for c in spellbook
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
                elements=_extract_elements(spellbook),
                event_year=None,
                card_quantities=_count_quantities(spellbook),
            )
        except Exception as e:
            logger.debug("Skipping malformed match deck (%s): %s", side, e)
            return None

    # ------------------------------------------------------------------ #
    # Admin recommended decks                                              #
    # ------------------------------------------------------------------ #

    def _ensure_admin_table(self, conn: sqlite3.Connection) -> None:
        """Create admin_recommended_decks table and migrate missing columns."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_recommended_decks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deck_id TEXT UNIQUE NOT NULL,
                curiosa_url TEXT NOT NULL,
                deck_name TEXT,
                avatar_name TEXT,
                json_deck_data TEXT,
                added_by TEXT,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                primer TEXT,
                stars INTEGER
            )
        """)
        # Migrate existing installs that predate these columns
        for col, definition in (("primer", "TEXT"), ("stars", "INTEGER")):
            try:
                conn.execute(f"ALTER TABLE admin_recommended_decks ADD COLUMN {col} {definition}")
            except sqlite3.OperationalError:
                pass  # column already exists
        conn.commit()

    def _load_admin_decks(self) -> list[DeckRecord]:
        """Load admin-recommended decks from the DB, marked as seeds."""
        decks = []
        if not self._db_path.exists():
            return decks
        try:
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
            self._ensure_admin_table(conn)
            cur = conn.cursor()
            cur.execute("""
                SELECT deck_id, curiosa_url, deck_name, avatar_name, json_deck_data, primer, stars
                FROM admin_recommended_decks
            """)
            rows = cur.fetchall()
            conn.close()

            for row in rows:
                deck = self._parse_admin_deck(row)
                if deck:
                    decks.append(deck)
        except Exception as e:
            logger.error("Failed to load admin decks: %s", e)

        logger.info("Loaded %d admin recommended decks", len(decks))
        return decks

    def _parse_admin_deck(self, row: sqlite3.Row) -> DeckRecord | None:
        """Parse an admin recommended deck row into a DeckRecord."""
        try:
            deck_id = row["deck_id"]
            if not deck_id:
                return None

            deck_json_str = row["json_deck_data"] or "{}"
            deck_data = json.loads(deck_json_str) if deck_json_str not in ("", "{}") else {}

            spellbook = deck_data.get("spellbook", [])
            atlas = deck_data.get("atlas", [])
            card_names = frozenset(
                c["name"].strip().lower()
                for c in spellbook
                if isinstance(c, dict) and c.get("name")
            )

            if not card_names:
                logger.warning("Admin deck %s has no card data — will show but without recommendations", deck_id)

            avatar_name = row["avatar_name"] or "Unknown"
            if not avatar_name or avatar_name == "Unknown":
                avatar_name = (deck_data.get("avatar") or [{}])[0].get("name", "Unknown")

            curiosa_url = row["curiosa_url"] or f"{self.CURIOSA_BASE}{deck_id}"

            return DeckRecord(
                deck_id=deck_id,
                deck_name=row["deck_name"] or deck_data.get("name", "Admin Pick"),
                avatar_name=avatar_name,
                player_name=deck_data.get("username", "Admin Pick"),
                event_name="Admin Pick",
                is_seed=True,
                card_names=card_names,
                card_count=len(card_names),
                curiosa_url=curiosa_url,
                elements=_extract_elements(spellbook),
                event_year=None,
                is_admin_rec=True,
                card_quantities=_count_quantities(spellbook),
                card_quantities_display=_count_quantities_display(spellbook),
                card_details=_get_card_details(spellbook, atlas),
                primer=row["primer"] or "",
                stars=row["stars"],
            )
        except Exception as e:
            logger.debug("Skipping malformed admin deck: %s", e)
            return None

    def save_admin_deck(self, deck_id: str, curiosa_url: str, deck_name: str,
                        avatar_name: str, json_deck_data: str, added_by: str,
                        primer: str = "", stars: int | None = None) -> None:
        """Insert or replace an admin recommended deck."""
        conn = sqlite3.connect(str(self._db_path))
        self._ensure_admin_table(conn)
        conn.execute("""
            INSERT OR REPLACE INTO admin_recommended_decks
                (deck_id, curiosa_url, deck_name, avatar_name, json_deck_data, added_by, primer, stars)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (deck_id, curiosa_url, deck_name, avatar_name, json_deck_data, added_by, primer or None, stars))
        conn.commit()
        conn.close()

    def update_admin_deck_meta(self, deck_id: str, primer: str, stars: int | None) -> bool:
        """Update just the primer and stars for an existing admin deck."""
        conn = sqlite3.connect(str(self._db_path))
        self._ensure_admin_table(conn)
        cur = conn.execute("""
            UPDATE admin_recommended_decks SET primer = ?, stars = ? WHERE deck_id = ?
        """, (primer or None, stars, deck_id))
        updated = cur.rowcount > 0
        conn.commit()
        conn.close()
        return updated

    def delete_admin_deck(self, deck_id: str) -> bool:
        """Delete an admin recommended deck. Returns True if a row was deleted."""
        conn = sqlite3.connect(str(self._db_path))
        self._ensure_admin_table(conn)
        cur = conn.execute("DELETE FROM admin_recommended_decks WHERE deck_id = ?", (deck_id,))
        deleted = cur.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def get_admin_deck_ids(self) -> list[str]:
        """Return all admin recommended deck IDs."""
        if not self._db_path.exists():
            return []
        try:
            conn = sqlite3.connect(str(self._db_path))
            self._ensure_admin_table(conn)
            cur = conn.execute("SELECT deck_id FROM admin_recommended_decks")
            ids = [row[0] for row in cur.fetchall()]
            conn.close()
            return ids
        except Exception as e:
            logger.error("Failed to get admin deck ids: %s", e)
            return []

    def compute_cluster_win_rate(self, seed, threshold: float = 0.3) -> dict:
        """Scan every match row and count wins/losses for decks similar to seed.

        For each row in match_records and match_records_archive, the winner and
        loser deck JSON is parsed and its Jaccard similarity against the seed is
        computed. Rows at or above threshold contribute a win or loss.
        """
        if not self._db_path.exists():
            return {"wins": 0, "losses": 0, "win_rate": None}

        seed_cards = seed.card_names
        wins = 0
        losses = 0

        try:
            conn = sqlite3.connect(str(self._db_path))
            cur = conn.cursor()

            for table in ("match_records_archive", "match_records"):
                try:
                    cur.execute(f"""
                        SELECT json_deck_data_winner, json_deck_data_loser
                        FROM {table}
                        WHERE (json_deck_data_winner IS NOT NULL AND json_deck_data_winner NOT IN ('', '{{}}'))
                           OR (json_deck_data_loser  IS NOT NULL AND json_deck_data_loser  NOT IN ('', '{{}}'))
                    """)
                    for json_w, json_l in cur.fetchall():
                        if json_w and json_w not in ("", "{}"):
                            w_cards = self._parse_spellbook_names(json_w)
                            if w_cards and self._jaccard(w_cards, seed_cards) >= threshold:
                                wins += 1
                        if json_l and json_l not in ("", "{}"):
                            l_cards = self._parse_spellbook_names(json_l)
                            if l_cards and self._jaccard(l_cards, seed_cards) >= threshold:
                                losses += 1
                except sqlite3.OperationalError:
                    pass

            conn.close()
        except Exception as e:
            logger.error("Failed to compute cluster win rate: %s", e)
            return {"wins": 0, "losses": 0, "win_rate": None}

        total = wins + losses
        win_rate = round(wins / total, 4) if total > 0 else None
        return {"wins": wins, "losses": losses, "win_rate": win_rate}

    @staticmethod
    def _parse_spellbook_names(json_str: str) -> frozenset:
        """Parse deck JSON and return frozenset of lowercase card names."""
        try:
            data = json.loads(json_str)
            spellbook = data.get("spellbook", [])
            return frozenset(
                c["name"].strip().lower()
                for c in spellbook
                if isinstance(c, dict) and c.get("name")
            )
        except Exception:
            return frozenset()

    @staticmethod
    def _jaccard(a: frozenset, b: frozenset) -> float:
        union = len(a | b)
        return len(a & b) / union if union else 0.0

    def _extract_deck_id(self, url: str) -> str:
        """Extract Curiosa deck ID from a URL like https://curiosa.io/decks/abc123."""
        if not url:
            return ""
        # Handle URLs with query strings: split on ? first
        path = url.split("?")[0].rstrip("/")
        return path.split("/")[-1] if "/" in path else ""
