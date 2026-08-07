"""Helpers for canonical avatar-specific event ELO identities."""

import json
import sqlite3

from webapp_config import ELO_DB_PATH


def extract_main_avatar(deck_json: str | dict | None) -> str | None:
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


def canonicalize_avatar_name(name: str | None) -> str | None:
    if not name or not str(name).strip():
        return None
    conn = sqlite3.connect(str(ELO_DB_PATH))
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


def resolve_avatar_name(deck_json, override=None) -> str | None:
    candidate = override if override else extract_main_avatar(deck_json)
    return canonicalize_avatar_name(candidate)
