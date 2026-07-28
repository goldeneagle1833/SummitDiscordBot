"""Service for validating deck point budgets."""

import json
import logging

from utils.deck_checker import scrape_curosa_async
from repositories.card_points_repo import get_all_card_points, get_max_budget

logger = logging.getLogger("discord_bot")


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

    # Fetch deck data from Curiosa
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
