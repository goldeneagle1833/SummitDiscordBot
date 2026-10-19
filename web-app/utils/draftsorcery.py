"""Reading decks from DraftSorcery, where Limited players build their drafts."""

import json
import logging
from urllib.parse import parse_qs, urlparse

import requests

logger = logging.getLogger(__name__)


def is_draftsorcery_url(url: str) -> bool:
    return "draftsorcery.com" in (url or "").lower()


def deck_code(url: str) -> str | None:
    """The deck code in a ``https://draftsorcery.com/?deck=<code>`` link."""
    return parse_qs(urlparse(url or "").query).get("deck", [None])[0]


def fetch_draftsorcery_deck(url: str) -> dict | None:
    """Fetch a DraftSorcery deck in the same shape as a Curiosa deck.

    Returns {avatar, spellbook, atlas, sideboard}, each a list of
    {name, quantity}, or None when the deck can't be read.
    """
    code = deck_code(url)
    if not code:
        return None

    try:
        response = requests.get(f"https://draftsorcery.com/api/decks/{code}", timeout=30)
        if response.status_code != 200:
            logger.warning(f"DraftSorcery API returned status {response.status_code}")
            return None
        data = response.json()
    except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
        logger.warning(f"DraftSorcery API request failed: {e}")
        return None

    # board entries have full card metadata; fall back to deck.cards
    deck_cards = data.get("board") or data.get("deck", {}).get("cards", [])
    if not deck_cards:
        return None

    # Count card occurrences and group by type
    card_counts = {}
    for entry in deck_cards:
        card_info = entry.get("card", {})
        name = card_info.get("name", "")
        card_type = (card_info.get("type") or "").lower()
        if not name:
            continue
        if name not in card_counts:
            card_counts[name] = {"name": name, "quantity": 0, "type": card_type}
        card_counts[name]["quantity"] += 1

    # Map to Curiosa-style sections
    avatar = []
    spellbook = []
    atlas = []
    for info in card_counts.values():
        entry = {"name": info["name"], "quantity": info["quantity"]}
        if info["type"] == "avatar":
            avatar.append(entry)
        elif info["type"] == "site":
            atlas.append(entry)
        else:
            spellbook.append(entry)

    return {"avatar": avatar, "spellbook": spellbook, "atlas": atlas, "sideboard": []}
