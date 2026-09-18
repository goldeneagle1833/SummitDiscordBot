"""Card name to local image filename lookup.

Decks arrive from several places and only some of them carry usable image
references - Curiosa hands back absolute CDN URLs, which cannot be served from
``/card-images/``. Everything that renders a deck resolves names through here
instead, so every deck on the site draws from the same image set.
"""

import logging
import os
import re

from utils.formatting import normalize_card_name
from webapp_config import CARD_IMAGES_DIR

logger = logging.getLogger(__name__)

# Printing suffixes on the filenames, longest first so "-bt-s-r" is not
# mistaken for "-bt-s".
_PRINTING_SUFFIXES = (
    "-bt-s-r",
    "-scg-f",
    "-bt-s",
    "-bt-f",
    "-op-s",
    "-tc-f",
    "-b-s",
    "-b-f",
    "-d-s",
    "-d-f",
)

_card_image_map: dict | None = None


def get_card_image_map() -> dict:
    """{normalized card name: filename}, built once from CARD_IMAGES_DIR."""
    global _card_image_map
    if _card_image_map is not None:
        return _card_image_map

    mapping: dict = {}
    if CARD_IMAGES_DIR.exists():
        all_files = sorted(os.listdir(CARD_IMAGES_DIR))
        png_files = [f for f in all_files if f.lower().endswith((".png", ".jpg", ".jpeg"))]
        webp_files = [f for f in all_files if f.lower().endswith(".webp")]

        for fname in png_files + webp_files:
            base = re.sub(r"\.(png|jpg|jpeg|webp)$", "", fname, flags=re.IGNORECASE).lower()
            for suffix in _PRINTING_SUFFIXES:
                if base.endswith(suffix):
                    base = base[: -len(suffix)]
                    break
            # Filenames are "<set number>-<card name>"; drop the number.
            card_name_normalized = base.split("-", 1)[1] if "-" in base else base

            # Prefer the standard printing when a card has several.
            is_standard = "-b-s" in fname.lower() or "-bt-s" in fname.lower()
            if card_name_normalized not in mapping or is_standard:
                mapping[card_name_normalized] = fname

    _card_image_map = mapping
    return mapping


def resolve_card_image(card_name: str) -> str | None:
    """The image filename for a card, or None when we do not have one."""
    if not card_name:
        return None
    return get_card_image_map().get(normalize_card_name(card_name))


def attach_images(cards, name_key: str = "name") -> list:
    """Set each card's ``image`` to a filename we can actually serve."""
    for card in cards or []:
        if isinstance(card, dict):
            card["image"] = resolve_card_image(card.get(name_key))
    return cards or []


def reset_cache():
    """Drop the cached map. For tests, and after new images are added."""
    global _card_image_map
    _card_image_map = None
