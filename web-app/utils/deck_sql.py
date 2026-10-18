"""SQL helpers for reading match deck columns without loading whole decks.

Each match row stores two full Curiosa deck lists (~19 KB of JSON each). Most
stats only need each deck's avatar, and pulling every deck into Python costs
~1 GB per request on the full archive. That memory is rarely handed back to
the OS, so worker RSS ratchets up with every such request.
"""

import sqlite3

_has_json = None


def sqlite_has_json() -> bool:
    """Whether this SQLite build has the JSON functions (checked once)."""
    global _has_json
    if _has_json is None:
        try:
            sqlite3.connect(":memory:").execute(
                "SELECT json_object('a', json_extract('{\"a\": 1}', '$.a'))"
            ).fetchone()
            _has_json = True
        except sqlite3.OperationalError:
            _has_json = False
    return _has_json


def avatar_only(col: str) -> str:
    """SELECT expression for a deck column, cut down to {"avatar": [...]}.

    Empty values ('', '{}', NULL) and invalid JSON come back unchanged, so code
    that json.loads the column and reads deck["avatar"] behaves exactly as it
    does on the full deck. Falls back to the full column without JSON support.
    """
    if not sqlite_has_json():
        return col
    return (
        f"CASE WHEN {col} IS NULL OR {col} IN ('', '{{}}') OR NOT json_valid({col}) THEN {col}"
        f" ELSE json_object('avatar', json_extract({col}, '$.avatar')) END"
    )


def avatar_name(col: str) -> str:
    """SQL expression for a deck column's first avatar name (NULL if none)."""
    return f"CASE WHEN json_valid({col}) THEN json_extract({col}, '$.avatar[0].name') END"


AVATAR_DECKS = f"{avatar_only('json_deck_data_winner')}, {avatar_only('json_deck_data_loser')}"
