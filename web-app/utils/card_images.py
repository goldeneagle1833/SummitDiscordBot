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

_card_image_map: dict | None = None


def _key(value: str) -> str:
    """A lookup key that survives however a name writes its separators.

    Filenames join words with underscores, while card names use spaces,
    hyphens and apostrophes - "East-West Dragon" is stored as
    ``east_west_dragon``. Treating every separator the same on both sides is
    what makes the two meet.
    """
    spaced = str(value or "").replace("_", " ").replace("-", " ")
    return normalize_card_name(spaced)


def _split_filename(base: str):
    """Split "<set>-<card name>-<printing>" into (name key, printing tokens).

    Printing markers are short trailing segments - ``-b-s``, ``-bt-s-r``,
    ``-dk-s``, ``-op-f`` - and new ones keep appearing, so they are recognised
    by shape rather than from a list. Stripping stops while two segments
    remain, so a card named in three letters keeps its name.
    """
    parts = base.split("-")
    printing = []
    while len(parts) > 2 and len(parts[-1]) <= 3:
        printing.insert(0, parts.pop())

    if len(parts) < 2:
        return "", printing
    return _key("-".join(parts[1:])), printing


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
            card_name_normalized, printing = _split_filename(base)
            if not card_name_normalized:
                continue

            # Prefer the standard printing over foils and variants.
            is_standard = printing and printing[-1] == "s"
            if card_name_normalized not in mapping or is_standard:
                mapping[card_name_normalized] = fname

    _card_image_map = mapping
    return mapping


def resolve_card_image(card_name: str) -> str | None:
    """The image filename for a card, or None when we do not have one."""
    if not card_name:
        return None
    return get_card_image_map().get(_key(card_name))


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
