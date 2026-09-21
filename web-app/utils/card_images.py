"""Card name to local image filename lookup.

Decks arrive from several places and only some of them carry usable image
references - Curiosa hands back absolute CDN URLs, which cannot be served from
``/card-images/``. Everything that renders a deck resolves names through here
instead, so every deck on the site draws from the same image set.

Image files are named ``<set>-<card name>-<printing>.<ext>``, e.g.
``bet-cave_in-b-s.webp``, where the printing is ``b-s`` for the base standard
card, ``b-f`` for its foil, ``op-rf`` for an organized-play rainbow foil, and
so on. The folder also holds stray download copies such as
``got-eclipse-b-s .png`` and ``got-black_mass-b-s (1).webp``, which are the
only copies of those cards. Every card maps to its standard printing when one
exists, so a deck never shows promo or foil art in place of the regular card.
"""

import logging
import os
import re

from utils.formatting import normalize_card_name
from webapp_config import CARD_IMAGES_DIR

logger = logging.getLogger(__name__)

_EXT_RANK = {".webp": 0, ".png": 1, ".jpg": 2, ".jpeg": 2}
_DOWNLOAD_COPY_RE = re.compile(r"\s*\(\d+\)\s*$")

_card_image_map: dict | None = None
_card_image_map_mtime: float | None = None


def _key(value: str) -> str:
    """A lookup key that survives however a name writes its separators.

    Filenames join words with underscores, while card names use spaces,
    hyphens and apostrophes - "East-West Dragon" is stored as
    ``east_west_dragon``. Treating every separator the same on both sides is
    what makes the two meet.
    """
    spaced = str(value or "").replace("_", " ").replace("-", " ")
    return normalize_card_name(spaced)


def card_image_key(card_name: str) -> str:
    """The key ``get_card_image_map`` files a card under."""
    return _key(card_name)


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
        return _key(base), printing
    return _key("-".join(parts[1:])), printing


def _printing_rank(printing: list) -> int:
    """Lower is better: base standard, then other standard printings, then foils."""
    joined = "-".join(printing)
    if joined == "b-s":
        return 0
    if joined.startswith("bt-s"):
        return 1
    if printing and printing[-1] == "s":
        return 2
    if joined == "b-f":
        return 3
    return 4


def _build_map(directory) -> dict:
    best: dict = {}

    def offer(key, rank, fname):
        # Ties go to the later filename, so a later set's printing wins.
        current = best.get(key)
        if current is None or rank <= current[0]:
            best[key] = (rank, fname)

    for fname in sorted(os.listdir(directory)):
        stem, ext = os.path.splitext(fname)
        ext = ext.lower()
        if ext not in _EXT_RANK:
            continue
        base = _DOWNLOAD_COPY_RE.sub("", stem).strip().lower()
        base = re.sub(r"\s*-\s*", "-", base)
        is_download_copy = base != stem.lower()

        name_key, printing = _split_filename(base)
        if not name_key:
            continue
        rank = (_printing_rank(printing), is_download_copy, _EXT_RANK[ext])
        offer(name_key, rank, fname)

        # Numbered token art ("foot_soldier_1") also covers the plain name.
        numbered = re.match(r"^(.+)_\d+$", name_key)
        if numbered:
            offer(numbered.group(1), (rank[0] + 10,) + rank[1:], fname)

    return {key: fname for key, (_, fname) in best.items()}


def get_card_image_map() -> dict:
    """{normalized card name: filename} for CARD_IMAGES_DIR.

    Rebuilt whenever the directory changes, so images added on the server
    show up without restarting the app.
    """
    global _card_image_map, _card_image_map_mtime
    try:
        mtime = os.stat(CARD_IMAGES_DIR).st_mtime
    except OSError:
        return {}
    if _card_image_map is None or _card_image_map_mtime != mtime:
        _card_image_map = _build_map(CARD_IMAGES_DIR)
        _card_image_map_mtime = mtime
    return _card_image_map


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
    """Drop the cached map. For tests."""
    global _card_image_map, _card_image_map_mtime
    _card_image_map = None
    _card_image_map_mtime = None
