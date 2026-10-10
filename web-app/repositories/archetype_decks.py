"""Loads every deck the Deck Archetypes page groups, from three sources.

  tournaments — the Top 8 page's event folders (top-8-decks-by-event/)
  seed events — tournament lists from the original archetype snapshot whose
                events are not on the Top 8 page (data/deck_archetype_seed_events.json).
                Their card lists are fetched from sorcerytcg.com once and cached.
  ranked      — every deck reported in a ranked match (match_records and
                match_records_archive), with its ranked win/loss record

A deck that shows up in more than one source is merged into one record, so a
tournament list that was also played on ranked carries both its placements and
its ranked record.
"""

import hashlib
import json
import logging
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from services.curiosa import get_curiosa_deck_id, get_pso_deck_id, normalize_deck_url
from utils.formatting import extract_year_from_name
from webapp_config import BASE_DIR, MATCH_RECORDS_DB_PATH, TOP_8_DIR

logger = logging.getLogger(__name__)

SEED_EVENTS_PATH = BASE_DIR / "data" / "deck_archetype_seed_events.json"
SEED_CACHE_PATH = BASE_DIR / "data" / "archetype_seed_decks.cache.json"

CURIOSA_DECK_URL = "https://sorcerytcg.com/decks/"
ZONES = ("spellbook", "atlas", "collection")
_ELEMENTS = ("Air", "Earth", "Fire", "Water")
# Placements 1-8 in a top8 file are Top 8 finishes; anything after is the rest of the cut.
TOP8_SIZE = 8


@dataclass
class TournamentEntry:
    event: str
    date: str | None
    player: str
    placement: int | None
    top8: bool
    top_cut: bool
    # Decks published for the event (not attendance; some events only publish a Top 8).
    event_size: int = 0
    # Events with no exact date still have a year in their name.
    year: int | None = None

    def date_span(self) -> tuple[str, str] | None:
        """(first, last) ISO day the event could have been on, or None if unknown."""
        if self.date:
            return self.date[:10], self.date[:10]
        if self.year:
            return f"{self.year}-01-01", f"{self.year}-12-31"
        return None

    def to_dict(self) -> dict:
        return {
            "event": self.event,
            "date": self.date,
            "player": self.player,
            "placement": self.placement,
            "top8": self.top8,
            "topCut": self.top_cut,
            "eventSize": self.event_size,
        }


@dataclass
class RankedGame:
    day: str | None  # ISO date the match was reported
    won: bool
    player: str | None


@dataclass
class ArchetypeDeck:
    key: str
    name: str
    url: str | None
    avatar: str
    elements: str
    # zone -> {card name: copies}
    cards: dict
    entries: list = field(default_factory=list)
    games: list = field(default_factory=list)
    # True for decks listed on the Top 8 page (not seed or ranked-only decks).
    on_top8_page: bool = False

    @property
    def is_tournament(self) -> bool:
        return bool(self.entries)


def _card_counts(cards: list) -> dict:
    """{name: copies}. Curiosa lists one entry per card with a quantity; older
    tournament files list one entry per copy, so quantities are summed."""
    counts: Counter = Counter()
    for card in cards or []:
        if not isinstance(card, dict):
            continue
        name = (card.get("name") or "").strip()
        if not name:
            continue
        try:
            counts[name] += max(1, int(card.get("quantity") or 1))
        except (TypeError, ValueError):
            counts[name] += 1
    return dict(counts)


def element_label(spellbook: list) -> str:
    """The deck's top two elements by copies, alphabetical ("Air / Fire")."""
    totals = {e: 0 for e in _ELEMENTS}
    for card in spellbook or []:
        if not isinstance(card, dict):
            continue
        try:
            qty = max(1, int(card.get("quantity") or 1))
        except (TypeError, ValueError):
            qty = 1
        for part in str(card.get("elements") or "").split(","):
            part = part.strip()
            if part in totals:
                totals[part] += qty
    top = [e for e in sorted(_ELEMENTS, key=lambda e: -totals[e]) if totals[e] > 0][:2]
    return " / ".join(sorted(top)) if top else "None"


def deck_from_json(raw: dict, key: str, url: str | None) -> ArchetypeDeck | None:
    """Build a deck from the legacy Curiosa deck format, or None if it has no spellbook."""
    if not isinstance(raw, dict):
        return None
    spellbook = raw.get("spellbook") or []
    cards = {
        "spellbook": _card_counts(spellbook),
        "atlas": _card_counts(raw.get("atlas")),
        "collection": _card_counts(raw.get("sideboard") or raw.get("collection")),
    }
    if not cards["spellbook"]:
        return None
    avatar_list = raw.get("avatar") or [{}]
    avatar = (avatar_list[0].get("name") if isinstance(avatar_list[0], dict) else None) or "Unknown"
    return ArchetypeDeck(
        key=key,
        name=(raw.get("name") or "").strip(),
        url=url,
        avatar=avatar,
        elements=element_label(spellbook),
        cards=cards,
    )


def _deck_key_from_url(url: str | None) -> tuple[str | None, str | None]:
    """(merge key, canonical link) for a deck link, or (None, None)."""
    if not url:
        return None, None
    curiosa_id = get_curiosa_deck_id(url)
    if curiosa_id:
        return curiosa_id, f"{CURIOSA_DECK_URL}{curiosa_id}"
    pso_id = get_pso_deck_id(url)
    if pso_id:
        return f"pso-{pso_id}", normalize_deck_url(url)
    return None, None


def _content_key(raw: dict) -> str:
    """A stable key for a deck with no link, from its avatar and card list."""
    parts = [str(((raw.get("avatar") or [{}])[0] or {}).get("name", ""))]
    for zone in ("spellbook", "atlas", "sideboard"):
        parts.append(json.dumps(sorted(_card_counts(raw.get(zone)).items())))
    return "list-" + hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


class ArchetypeDeckRepository:
    def __init__(
        self,
        top8_dir: Path | None = None,
        db_path: Path | None = None,
        seed_events_path: Path | None = None,
        seed_cache_path: Path | None = None,
    ):
        self._top8_dir = top8_dir or TOP_8_DIR
        self._db_path = db_path or MATCH_RECORDS_DB_PATH
        self._seed_events_path = seed_events_path or SEED_EVENTS_PATH
        self._seed_cache_path = seed_cache_path or SEED_CACHE_PATH

    # ------------------------------------------------------------------ #
    # Top 8 page tournaments                                               #
    # ------------------------------------------------------------------ #

    def _event_names(self) -> dict[str, tuple[str, str | None]]:
        """folder -> (display name, ISO date), as the Top 8 page shows them."""
        try:
            from repositories.events import EventRepository

            return {
                e["folder"]: (e.get("name") or e["folder"], e.get("event_date"))
                for e in EventRepository(self._top8_dir).get_all_events()
            }
        except Exception:
            logger.exception("Could not read Top 8 event metadata")
            return {}

    def load_tournament_decks(self) -> tuple[dict[str, ArchetypeDeck], int]:
        """Every deck in the Top 8 page's event folders, plus the event count."""
        decks: dict[str, ArchetypeDeck] = {}
        events = 0
        if not self._top8_dir.exists():
            logger.warning("TOP_8_DIR not found: %s", self._top8_dir)
            return decks, events

        names = self._event_names()
        for folder in sorted(self._top8_dir.iterdir()):
            if not folder.is_dir() or folder.name.startswith("_"):
                continue
            top8_file = full_file = None
            for f in folder.glob("*.json"):
                lower = f.name.lower()
                if "top8" in lower or "top 8" in lower:
                    top8_file = f
                elif lower.startswith(folder.name.lower()):
                    full_file = f
            if not top8_file and not full_file:
                continue

            event_name, event_date = names.get(folder.name, (folder.name, None))
            in_event: dict[str, tuple[ArchetypeDeck, TournamentEntry]] = {}
            for path, ranked_file in ((top8_file, True), (full_file, False)):
                if not path:
                    continue
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception as e:
                    logger.warning("Failed to read %s: %s", path, e)
                    continue
                if not isinstance(data, list):
                    continue
                for index, raw in enumerate(data):
                    if not isinstance(raw, dict):
                        continue
                    deck_id = str(raw.get("id") or "").strip()
                    if not deck_id or deck_id in in_event:
                        continue
                    deck = deck_from_json(raw, deck_id, f"{CURIOSA_DECK_URL}{deck_id}")
                    if deck is None:
                        continue
                    deck.on_top8_page = True
                    placement = index + 1 if ranked_file and index < TOP8_SIZE else None
                    entry = TournamentEntry(
                        event=event_name,
                        date=event_date,
                        player=(raw.get("username") or "Unknown"),
                        placement=placement,
                        top8=placement is not None,
                        top_cut=ranked_file,
                        year=extract_year_from_name(folder.name) or None,
                    )
                    in_event[deck_id] = (deck, entry)

            if in_event:
                events += 1
            for deck_id, (deck, entry) in in_event.items():
                entry.event_size = len(in_event)
                existing = decks.get(deck_id)
                if existing is None:
                    deck.entries.append(entry)
                    decks[deck_id] = deck
                else:
                    existing.entries.append(entry)
        return decks, events

    # ------------------------------------------------------------------ #
    # Seed events from the original snapshot                               #
    # ------------------------------------------------------------------ #

    def _load_seed_file(self) -> dict:
        try:
            with open(self._seed_events_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception:
            logger.exception("Could not read %s", self._seed_events_path)
            return {}

    def load_seed_list(self) -> list[dict]:
        return self._load_seed_file().get("decks") or []

    def load_seed_cache(self) -> dict:
        """{deck id: legacy deck dict, or {"unavailable": true}}."""
        try:
            with open(self._seed_cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception:
            logger.exception("Could not read %s", self._seed_cache_path)
            return {}

    def save_seed_cache_entry(self, deck_id: str, value: dict) -> None:
        """Merge one fetched deck into the cache file, atomically."""
        cache = self.load_seed_cache()
        cache[deck_id] = value
        self._seed_cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._seed_cache_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f)
        tmp.replace(self._seed_cache_path)

    def load_seed_decks(self) -> tuple[dict[str, ArchetypeDeck], set[str], list[str], int]:
        """(decks with card lists, event names, deck ids still to fetch, unavailable count)."""
        cache = self.load_seed_cache()
        seed_file = self._load_seed_file()
        # Decks each event published, including ones already on the Top 8 page.
        event_sizes = seed_file.get("eventSizes") or {}
        decks: dict[str, ArchetypeDeck] = {}
        events: set[str] = set()
        pending: list[str] = []
        unavailable = 0
        for seed in seed_file.get("decks") or []:
            deck_id = str(seed.get("id") or "").strip()
            if not deck_id:
                continue
            cached = cache.get(deck_id)
            if cached is None:
                pending.append(deck_id)
                continue
            deck = None if cached.get("unavailable") else deck_from_json(
                cached, deck_id, seed.get("url") or f"{CURIOSA_DECK_URL}{deck_id}"
            )
            if deck is None:
                unavailable += 1
                continue
            # The snapshot's name and avatar are what the deck was at the event.
            deck.name = seed.get("name") or deck.name
            deck.avatar = seed.get("avatar") or deck.avatar
            for e in seed.get("entries") or []:
                placement = e.get("placement") if isinstance(e.get("placement"), int) else None
                event = e.get("event") or "Unknown event"
                deck.entries.append(TournamentEntry(
                    event=event,
                    date=e.get("date"),
                    player=e.get("player") or "Unknown",
                    placement=placement,
                    top8=bool(e.get("top8")) or (placement is not None and placement <= TOP8_SIZE),
                    top_cut=bool(e.get("topCut")) or bool(e.get("top8")),
                    event_size=int(event_sizes.get(event) or 0),
                ))
                events.add(e.get("event") or "Unknown event")
            decks[deck_id] = deck
        return decks, events, pending, unavailable

    # ------------------------------------------------------------------ #
    # Ranked matches                                                       #
    # ------------------------------------------------------------------ #

    _SIDES = (
        ("json_deck_data_winner", "curiosa_url_winner", "winner_display_name", True),
        ("json_deck_data_loser", "curiosa_url_loser", "losser_display_name", False),
    )

    def _ranked_rows(self, cur: sqlite3.Cursor, table: str):
        """Newest first, so the first time a deck is seen is its latest list."""
        try:
            columns = {row[1] for row in cur.execute(f"PRAGMA table_info({table})")}
        except sqlite3.Error:
            return
        needed = {"json_deck_data_winner", "json_deck_data_loser", "curiosa_url_winner",
                  "curiosa_url_loser", "winner_display_name", "losser_display_name"}
        if not needed <= columns:
            return
        timestamp = "timestamp" if "timestamp" in columns else "NULL"
        # Older archives have no match_type column; everything there was ranked.
        ranked_only = " AND (match_type = 'ranked' OR match_type IS NULL)" if "match_type" in columns else ""
        cur.execute(f"""
            SELECT json_deck_data_winner, json_deck_data_loser,
                   curiosa_url_winner, curiosa_url_loser,
                   winner_display_name, losser_display_name, {timestamp}
            FROM {table}
            WHERE ((json_deck_data_winner IS NOT NULL AND json_deck_data_winner NOT IN ('', '{{}}'))
                OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser NOT IN ('', '{{}}')))
                {ranked_only}
            ORDER BY rowid DESC
        """)
        yield from cur

    def load_ranked_decks(self) -> tuple[dict[str, ArchetypeDeck], list]:
        """Every deck reported in a ranked match with its games, plus each game's day."""
        decks: dict[str, ArchetypeDeck] = {}
        games: list = []
        if not self._db_path.exists():
            logger.warning("match_records.db not found: %s", self._db_path)
            return decks, games
        try:
            conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
        except sqlite3.Error:
            logger.exception("Could not open match records")
            return decks, games
        try:
            cur = conn.cursor()
            for table in ("match_records", "match_records_archive"):
                for row in self._ranked_rows(cur, table):
                    values = dict(zip(
                        ("json_deck_data_winner", "json_deck_data_loser", "curiosa_url_winner",
                         "curiosa_url_loser", "winner_display_name", "losser_display_name", "timestamp"),
                        row,
                    ))
                    day = str(values["timestamp"])[:10] if values["timestamp"] else None
                    games.append(day)
                    for json_col, url_col, name_col, won in self._SIDES:
                        raw_json = values[json_col]
                        if not raw_json or raw_json in ("", "{}"):
                            continue
                        key, url = _deck_key_from_url(values[url_col])
                        deck = decks.get(key) if key else None
                        if deck is None:
                            # Only parse a deck's JSON the first time it is seen.
                            try:
                                raw = json.loads(raw_json)
                            except (TypeError, ValueError):
                                continue
                            if not key:
                                key = _content_key(raw)
                                deck = decks.get(key)
                            if deck is None:
                                deck = deck_from_json(raw, key, url)
                                if deck is None:
                                    continue
                                decks[key] = deck
                        deck.games.append(RankedGame(day=day, won=won, player=values[name_col] or None))
        except sqlite3.Error:
            logger.exception("Failed reading ranked match decks")
        finally:
            conn.close()
        return decks, games
