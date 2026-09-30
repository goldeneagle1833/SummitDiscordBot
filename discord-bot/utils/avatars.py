"""Avatar names: the official list, name checking, and reading a deck's avatar.

Avatar-mode events rate every (player, avatar) pair separately, so an avatar
name must always be spelled the same way ("Imposter", never "Impostor") or one
avatar would split into two ladder entries.
"""

import json
import logging
import re
import sqlite3

from utils.text import levenshtein_distance

logger = logging.getLogger("discord_bot")

# Avatars seen in tournament and ladder decks. The card catalog synced from
# the official Sorcery API is the primary source; this list covers a fresh
# install whose catalog has not synced yet (or synced only part of the set).
KNOWN_AVATARS = (
    "Animist", "Archimago", "Avatar of Air", "Avatar of Earth", "Avatar of Fire",
    "Avatar of Water", "Battlemage", "Bladedancer", "Corruptor", "Deathspeaker",
    "Dragonlord", "Druid", "Duplicator", "Elementalist", "Enchantress",
    "Flamecaller", "Geomancer", "Harbinger", "Imposter", "Interrogator",
    "Ironclad", "Magician", "Necromancer", "Pathfinder", "Persecutor",
    "Realm-Eater", "Savior", "Seer", "Sorcerer", "Sparkmage", "Spellslinger",
    "Templar", "Waveshaper", "Witch",
)

# Suggestions further than this from every avatar are not offered.
_MAX_SUGGESTION_DISTANCE = 3


def _key(name: str) -> str:
    """Comparison key: case, spaces and punctuation don't matter."""
    return re.sub(r"[^a-z0-9]", "", (name or "").casefold())


def _catalog_avatars(db_path: str = "elo.db") -> list[str]:
    try:
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT name FROM card_catalog WHERE card_type = 'Avatar' COLLATE NOCASE"
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return []
    return [row[0] for row in rows if row[0]]


def get_avatar_names(db_path: str = "elo.db") -> list[str]:
    """Every known avatar name, catalog spelling first, sorted."""
    names = {}
    for name in (*_catalog_avatars(db_path), *KNOWN_AVATARS):
        names.setdefault(_key(name), name)
    return sorted(names.values())


def canonical_avatar(name: str, db_path: str = "elo.db") -> str | None:
    """The official spelling of ``name``, or None when it isn't an avatar."""
    key = _key(name)
    if not key:
        return None
    for avatar in get_avatar_names(db_path):
        if _key(avatar) == key:
            return avatar
    return None


def suggest_avatar(name: str, db_path: str = "elo.db") -> str | None:
    """The closest avatar name to a misspelling, if one is close enough."""
    key = _key(name)
    if not key:
        return None
    best, best_distance = None, _MAX_SUGGESTION_DISTANCE + 1
    for avatar in get_avatar_names(db_path):
        distance = levenshtein_distance(key, _key(avatar))
        if distance < best_distance:
            best, best_distance = avatar, distance
    return best


def validate_avatar_name(name: str, db_path: str = "elo.db") -> tuple[str | None, str | None]:
    """Check a typed avatar name: (official_name, None) or (None, error).

    A near miss is rejected with a suggestion rather than silently corrected,
    so a typo can never update the wrong avatar entry.
    """
    typed = (name or "").strip()
    avatar = canonical_avatar(typed, db_path)
    if avatar:
        return avatar, None
    if not typed:
        return None, "An avatar name is required."
    suggestion = suggest_avatar(typed, db_path)
    if suggestion:
        return None, f"No avatar named '{typed}' — did you mean **{suggestion}**?"
    return None, f"No avatar named '{typed}'."


def avatar_from_deck(deck) -> str | None:
    """The avatar in a deck (dict or JSON string in the legacy Curiosa shape).

    Curiosa/sorcerytcg.com and Play Sorcery Online decks both arrive in this
    shape (see utils.deck_checker). A name missing from the known list is
    still returned as-is, so a newly released avatar works before the card
    catalog catches up.
    """
    if isinstance(deck, str):
        try:
            deck = json.loads(deck) if deck else {}
        except (TypeError, ValueError):
            return None
    if not isinstance(deck, dict):
        return None
    for entry in deck.get("avatar") or []:
        name = entry.get("name") if isinstance(entry, dict) else entry
        if isinstance(name, str) and name.strip():
            return canonical_avatar(name) or name.strip()
    return None


async def read_deck_avatar(deck_url: str) -> str | None:
    """Fetch a deck link and return its avatar (None when unreadable)."""
    if not deck_url:
        return None
    from utils.deck_checker import scrape_curosa_async

    try:
        deck_json = await scrape_curosa_async(deck_url)
    except Exception as exc:  # scrape_curosa_async already swallows most errors
        logger.warning("read_deck_avatar: fetch failed for %s: %s", deck_url, exc)
        return None
    return avatar_from_deck(deck_json)
