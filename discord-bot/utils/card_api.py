"""Convert Sorcery TCG API cards into the legacy card shape the catalog stores.

In September 2026 api.sorcerytcg.com/api/cards replaced its response format:
``guardian`` became ``engine`` (flat thresholds, list-valued elements and
subtypes, ``defense``/``rules`` spellings) and ``sets[].variants[]`` became a
flat ``printings[]`` list. Everything downstream (the card_catalog columns, the
web app's raw_json readers) expects the old All_Cards_Array shape, so the sync
converts new-format cards back to it. Legacy-format cards pass through as-is.
"""

# Order the old API used when joining multi-element cards ("Earth, Fire, Water, Air").
_ELEMENT_ORDER = ["Earth", "Fire", "Water", "Air"]


def _join_elements(elements) -> str:
    """Join an element list the way the old API did; "None" when there are none."""
    real = [e for e in (elements or []) if e and e != "None"]
    if not real:
        return "None"
    ordered = [e for e in _ELEMENT_ORDER if e in real]
    ordered += [e for e in real if e not in _ELEMENT_ORDER]
    return ", ".join(ordered)


def to_legacy_card(card: dict) -> dict:
    """Return ``card`` in the legacy guardian/sets shape.

    Cards already in the legacy shape (no ``engine`` key) are returned unchanged.
    """
    engine = card.get("engine")
    if not isinstance(engine, dict):
        return card

    guardian = {
        "type": engine.get("type") or "",
        # Avatars have no rarity, only a slot; tokens have neither and the old
        # API listed them as Ordinary.
        "rarity": engine.get("rarity") or engine.get("slot") or "Ordinary",
        "cost": engine.get("cost"),
        "attack": engine.get("attack"),
        "defence": engine.get("defense"),
        "life": engine.get("life"),
        "rulesText": engine.get("rules") or "",
        "thresholds": {
            "air": engine.get("air") or 0,
            "earth": engine.get("earth") or 0,
            "fire": engine.get("fire") or 0,
            "water": engine.get("water") or 0,
        },
    }

    # Group printings into sets, oldest set first like the old API.
    sets: dict[str, dict] = {}
    printings = sorted(card.get("printings") or [], key=lambda p: p.get("printedAt") or "")
    for printing in printings:
        set_name = (printing.get("set") or {}).get("name") or ""
        meta = printing.get("meta") or {}
        entry = sets.setdefault(set_name, {
            "name": set_name,
            "releasedAt": printing.get("printedAt"),
            "metadata": guardian,
            "variants": [],
        })
        entry["variants"].append({
            "slug": printing.get("slug") or "",
            "finish": meta.get("finish") or "",
            "product": meta.get("product") or "",
            "artist": (meta.get("artist") or {}).get("name") or "",
            "flavorText": meta.get("flavor") or "",
            "typeText": meta.get("typeline") or "",
        })

    return {
        "name": card.get("name", ""),
        "elements": _join_elements(engine.get("elements")),
        "subTypes": ", ".join(engine.get("subtypes") or []),
        "guardian": guardian,
        "sets": list(sets.values()),
    }
