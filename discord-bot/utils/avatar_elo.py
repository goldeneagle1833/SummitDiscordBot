"""Helpers for canonical avatar-specific event ELO identities."""

import json
import sqlite3


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
    return row[0] if row else None


def resolve_avatar_name(
    deck_json: str | dict | None,
    override: str | None = None,
    db_path: str = "elo.db",
) -> str | None:
    """Resolve an optional catalog override or the main avatar in deck JSON."""
    candidate = override if override else extract_main_avatar(deck_json)
    return canonicalize_avatar_name(candidate, db_path)
