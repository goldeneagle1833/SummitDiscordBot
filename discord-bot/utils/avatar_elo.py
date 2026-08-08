"""Helpers for canonical avatar-specific event ELO identities."""

import json
import difflib
import re
import sqlite3


AVATAR_ALIASES = {
    "imposter": "Impostor",
}


def _normalized_avatar_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.casefold())


def list_avatar_names(db_path: str = "elo.db") -> list[str]:
    """Return canonical Avatar card names from the local catalog."""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """SELECT name FROM card_catalog
               WHERE card_type = 'Avatar' COLLATE NOCASE
               ORDER BY name COLLATE NOCASE"""
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    return [row[0] for row in rows]


def extract_main_avatar(deck_json: str | dict | None) -> str | None:
    """Extract the deck's main Avatar, excluding auxiliary avatar cards."""
    if not deck_json:
        return None
    try:
        deck = json.loads(deck_json) if isinstance(deck_json, str) else deck_json
    except (TypeError, json.JSONDecodeError):
        return None
    avatars = deck.get("avatar") or []
    for avatar in avatars:
        if avatar and avatar.get("type") == "Avatar" and avatar.get("name"):
            return avatar["name"].strip()
    if avatars and avatars[0] and avatars[0].get("name"):
        return avatars[0]["name"].strip()
    return None


def canonicalize_avatar_name(name: str | None, db_path: str = "elo.db") -> str | None:
    """Return the card-catalog spelling for an Avatar, or None if unknown."""
    if not name or not str(name).strip():
        return None
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """SELECT name FROM card_catalog
               WHERE name = ? COLLATE NOCASE AND card_type = 'Avatar' COLLATE NOCASE
               LIMIT 1""",
            (str(name).strip(),),
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    finally:
        conn.close()
    if row:
        return row[0]

    names = list_avatar_names(db_path)
    normalized = _normalized_avatar_name(str(name).strip())
    alias_target = AVATAR_ALIASES.get(normalized)
    if alias_target:
        alias_match = next(
            (candidate for candidate in names if candidate.casefold() == alias_target.casefold()),
            None,
        )
        if alias_match:
            return alias_match
    normalized_matches = [
        candidate
        for candidate in names
        if _normalized_avatar_name(candidate) == normalized
    ]
    return normalized_matches[0] if len(normalized_matches) == 1 else None


def suggest_avatar_names(
    name: str | None, db_path: str = "elo.db", limit: int = 3
) -> list[str]:
    """Suggest canonical names for an invalid free-text Avatar entry."""
    if not name:
        return []
    names = list_avatar_names(db_path)
    query = str(name).strip()
    substring_matches = [
        candidate for candidate in names if query.casefold() in candidate.casefold()
    ]
    if substring_matches:
        return substring_matches[:limit]
    normalized_map = {_normalized_avatar_name(candidate): candidate for candidate in names}
    close = difflib.get_close_matches(
        _normalized_avatar_name(query), normalized_map.keys(), n=limit, cutoff=0.45
    )
    return [normalized_map[value] for value in close]


def avatar_input_error(label: str, value: str | None, db_path: str = "elo.db") -> str:
    suggestions = suggest_avatar_names(value, db_path)
    message = f"Enter a valid Avatar card name for {label}"
    if suggestions:
        message += ". Did you mean: " + ", ".join(suggestions) + "?"
    else:
        message += ". Use the exact card name shown in the Avatar catalog."
    return message


def resolve_avatar_name(
    deck_json: str | dict | None,
    override: str | None = None,
    db_path: str = "elo.db",
) -> str | None:
    """Resolve an optional catalog override or the main avatar in deck JSON."""
    candidate = override if override else extract_main_avatar(deck_json)
    return canonicalize_avatar_name(candidate, db_path)
