"""Shipping price from the store listings in a cart.

Each listing can say how many cards one of it holds (``ship_cards``) and/or
set its own shipping price (``shipping_cents``). Cards add up across the
cart: up to ENVELOPE_MAX_CARDS go in a plain white envelope, more go USPS
Ground Advantage. A listing's own shipping price wins over the card price
when it's higher (the cart pays the single highest price, one package).

A cart with any listing that has neither set keeps the storefront's old
shipping (Stripe shipping rate or flat rate), so nothing changes until a
listing is set up.
"""

import os

ENVELOPE_MAX_CARDS = int(os.environ.get("STORE_ENVELOPE_MAX_CARDS", "6"))
ENVELOPE_CENTS = int(os.environ.get("STORE_ENVELOPE_SHIPPING_CENTS", "199"))
GROUND_CENTS = int(os.environ.get("STORE_GROUND_SHIPPING_CENTS", "599"))


def shipping_rules() -> dict:
    """The card tiers, for the storefront to show a shipping estimate."""
    return {
        "envelope_max_cards": ENVELOPE_MAX_CARDS,
        "envelope_cents": ENVELOPE_CENTS,
        "ground_cents": GROUND_CENTS,
    }


def cards_shipping_cents(cards: int) -> int:
    """Price for a package of this many cards (0 cards ships nothing)."""
    if cards <= 0:
        return 0
    return ENVELOPE_CENTS if cards <= ENVELOPE_MAX_CARDS else GROUND_CENTS


def listing_shipping_cents(lines: list[tuple[dict, int]]) -> int | None:
    """Shipping for a cart of (product, quantity), or None for the old way.

    None when the cart is empty or any listing has neither a card count nor
    its own shipping price.
    """
    if not lines:
        return None
    cards = 0
    own_prices = [0]
    for product, qty in lines:
        per_card = product.get("ship_cards")
        own = product.get("shipping_cents")
        if per_card is None and own is None:
            return None
        if per_card is not None:
            cards += int(per_card) * max(0, int(qty))
        if own is not None:
            own_prices.append(int(own))
    return max(cards_shipping_cents(cards), *own_prices)

