"""Hard rules every MCP answer passes through.

1. No ranked deck lists or deck links. Deck links appear only in the Top 8
   tools, which build them from public tournament data themselves. Every
   other answer goes through ``strip_deck_data``, which removes any field or
   text that could point at a ranked deck. Tests assert this.
2. Answers stay small: lists are cut and long text trimmed, so a single tool
   call can't return megabytes to the AI app (``compact``).
"""

from __future__ import annotations

import re
from typing import Any

# Field names that carry deck links, deck lists or deck snapshots anywhere in
# the site's JSON. Matched case-insensitively against the whole key.
_DECK_KEY = re.compile(
    r"(deck_?url|deck_?link|curiosa|deck_?snapshot|snapshot|deck_?json|json_deck|deck_?data|"
    r"deck_?list|decklist|deck_?id|deckrecid|has_deck|spellbook|atlas|sideboard|collection|"
    r"members|recommendations|replay|recent_decks)",
    re.IGNORECASE,
)
# Text that is (or contains) a link to a deck on a deck site
_DECK_TEXT = re.compile(r"(curiosa\.io|sorcerytcg\.com/decks|realmsapp|/decks?/[A-Za-z0-9]{8,})", re.IGNORECASE)

MAX_LIST = 25
MAX_TEXT = 600


def strip_deck_data(value: Any) -> Any:
    """A copy of ``value`` with every deck link, deck list and snapshot removed."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if _DECK_KEY.search(str(key)):
                continue
            out[key] = strip_deck_data(item)
        return out
    if isinstance(value, list):
        return [strip_deck_data(v) for v in value]
    if isinstance(value, str) and _DECK_TEXT.search(value):
        return "[link removed]"
    return value


def contains_deck_data(value: Any) -> bool:
    """True if ``value`` still holds anything ``strip_deck_data`` would remove."""
    if isinstance(value, dict):
        return any(_DECK_KEY.search(str(k)) or contains_deck_data(v) for k, v in value.items())
    if isinstance(value, list):
        return any(contains_deck_data(v) for v in value)
    return isinstance(value, str) and bool(_DECK_TEXT.search(value))


def compact(value: Any, max_list: int = MAX_LIST, max_text: int = MAX_TEXT, _depth: int = 0) -> Any:
    """Cut long lists and strings, drop image links and deep nesting."""
    if _depth > 6:
        return None
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if "image" in lowered or lowered in ("icon", "avatar_url", "is_admin", "is_owner"):
                continue
            out[key] = compact(item, max_list, max_text, _depth + 1)
        return out
    if isinstance(value, list):
        items = [compact(v, max_list, max_text, _depth + 1) for v in value[:max_list]]
        if len(value) > max_list:
            items.append(f"... {len(value) - max_list} more not shown")
        return items
    if isinstance(value, str) and len(value) > max_text:
        return value[:max_text].rstrip() + "..."
    if isinstance(value, float):
        return round(value, 1)
    return value


def safe(value: Any, **kwargs) -> Any:
    """``strip_deck_data`` then ``compact``: what non-Top 8 tools return."""
    return compact(strip_deck_data(value), **kwargs)
