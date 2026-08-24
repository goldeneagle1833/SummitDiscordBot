"""Service for validating deck point budgets."""

import asyncio
import json
import logging
from urllib.parse import urlparse, parse_qs

import requests

from utils.deck_checker import scrape_curosa_async
from repositories.card_points_repo import get_all_card_points, get_max_budget

logger = logging.getLogger("discord_bot")


async def _fetch_draftsorcery_deck(url: str) -> dict | None:
    """Fetch and normalize a deck from DraftSorcery API.

    Returns deck data in Curiosa-style format (avatar, spellbook, atlas, sideboard)
    or None on failure.
    """
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    deck_code = params.get("deck", [None])[0]
    if not deck_code:
        return None

    def _fetch():
        try:
            response = requests.get(
                f"https://draftsorcery.com/api/decks/{deck_code}",
                timeout=30,
            )
            if response.status_code != 200:
                return None
            return response.json()
        except Exception:
            return None

    data = await asyncio.to_thread(_fetch)
    if not data:
        return None

    # board entries have full card metadata; fall back to deck.cards
    deck_cards = data.get("board") or data.get("deck", {}).get("cards", [])
    if not deck_cards:
        return None

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

    avatar, spellbook, atlas = [], [], []
    for info in card_counts.values():
        entry = {"name": info["name"], "quantity": info["quantity"]}
        if info["type"] == "avatar":
            avatar.append(entry)
        elif info["type"] == "site":
            atlas.append(entry)
        else:
            spellbook.append(entry)

    return {"avatar": avatar, "spellbook": spellbook, "atlas": atlas, "sideboard": []}


async def _fetch_sorcery_online_deck(url: str) -> dict | None:
    """Fetch the public deck export without exposing the link in logs."""

    def _fetch():
        try:
            response = requests.get(
                "https://playsorceryonline.com/api/decks/export",
                params={"input": url},
                timeout=30,
            )
            return response.json() if response.status_code == 200 else None
        except Exception:
            return None

    return await asyncio.to_thread(_fetch)


def calculate_deck_points(deck_data: dict, card_points: dict[str, int]) -> tuple[int, list[dict]]:
    """Calculate total points for a deck based on card point assignments.

    Args:
        deck_data: Parsed deck JSON from Curiosa API.
        card_points: Dict mapping card_name (lowercase) -> point_value.

    Returns:
        Tuple of (total_points, list of {name, quantity, points_each, points_total} for costed cards).
    """
    total = 0
    costed_cards = []

    for section in ("avatar", "spellbook", "atlas", "sideboard"):
        cards = deck_data.get(section)
        if not cards:
            continue
        for card in cards:
            name = card.get("name", "")
            quantity = card.get("quantity", 1)
            pts = card_points.get(name.lower(), 0)
            if pts > 0:
                card_total = pts * quantity
                total += card_total
                costed_cards.append({
                    "name": name,
                    "quantity": quantity,
                    "points_each": pts,
                    "points_total": card_total,
                })

    return total, costed_cards


async def validate_deck_points(deck_url: str) -> tuple[bool, str, int, int]:
    """Validate a deck URL against the points budget.

    Returns:
        Tuple of (is_valid, message, total_points, max_budget).
    """
    max_budget = get_max_budget()
    card_points = get_all_card_points()

    if not card_points:
        # No cards have points assigned yet — all decks pass
        return True, "No point restrictions configured.", 0, max_budget

    # Fetch deck data from DraftSorcery or Curiosa
    if "playsorceryonline.com" in deck_url.lower():
        deck_data = await _fetch_sorcery_online_deck(deck_url)
        if not deck_data:
            return False, "Could not fetch deck data from Sorcery Online. Check the URL and try again.", 0, max_budget
    elif "draftsorcery.com" in deck_url.lower():
        deck_data = await _fetch_draftsorcery_deck(deck_url)
        if not deck_data:
            return False, "Could not fetch deck data from DraftSorcery. Check the URL and try again.", 0, max_budget
    else:
        deck_json_str = await scrape_curosa_async(deck_url)
        if not deck_json_str or deck_json_str == "{}":
            return False, "Could not fetch deck data from Curiosa. Check the URL and try again.", 0, max_budget
        try:
            deck_data = json.loads(deck_json_str)
        except json.JSONDecodeError:
            return False, "Invalid deck data received from Curiosa.", 0, max_budget

    total_points, costed_cards = calculate_deck_points(deck_data, card_points)

    if total_points > max_budget:
        # Build a breakdown of the offending cards
        breakdown = ", ".join(
            f"{c['name']} ({c['points_each']}x{c['quantity']}={c['points_total']})"
            for c in sorted(costed_cards, key=lambda c: -c["points_total"])[:5]
        )
        return (
            False,
            f"Deck has **{total_points}** points (max **{max_budget}**). "
            f"Top cards: {breakdown}",
            total_points,
            max_budget,
        )

    return True, f"Deck is valid: {total_points}/{max_budget} points.", total_points, max_budget
