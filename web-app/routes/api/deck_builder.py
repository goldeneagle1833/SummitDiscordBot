"""API routes for the Deck Builder / Visualizer tool.

Endpoints:
  POST /api/deck-builder/fetch  — fetch a deck from Curiosa URL and return enriched card data
  POST /api/deck-builder/save   — save a deck (auth required)
  PUT  /api/deck-builder/<id>   — update a saved deck (auth required)
  GET  /api/deck-builder/my-decks — list user's saved decks (auth required)
  GET  /api/deck-builder/<id>   — load a saved deck (auth required)
  DELETE /api/deck-builder/<id> — delete a saved deck (auth required)
"""

import json
import logging
import os
import re

from flask import Blueprint, jsonify, request, session

from repositories.deck_builder_repo import DeckBuilderRepository
from services.curiosa import CuriosaService
from utils.auth import require_auth
from webapp_config import ALL_CARDS_PATH, CARD_IMAGES_DIR

logger = logging.getLogger(__name__)

deck_builder_bp = Blueprint("deck_builder", __name__)

# ---------------------------------------------------------------------------
# Card metadata + image lookup (cached at module level)
# ---------------------------------------------------------------------------

_card_metadata: dict[str, dict] | None = None
_card_image_map: dict[str, str] | None = None


def _get_card_metadata() -> dict[str, dict]:
    """Return {normalized_name: full metadata} from All_Cards_Array.json."""
    global _card_metadata
    if _card_metadata is not None:
        return _card_metadata

    mapping: dict[str, dict] = {}
    try:
        with open(ALL_CARDS_PATH, "r", encoding="utf-8") as f:
            all_cards = json.load(f)
        for card in all_cards:
            name = card.get("name", "")
            if not name:
                continue
            key = re.sub(r"[^a-z0-9]", "", name.lower())
            guardian = card.get("guardian", {}) or {}
            sets_data = card.get("sets", []) or []

            # Get artist and flavor text from first variant
            artist = ""
            flavor_text = ""
            set_name = ""
            type_text = ""
            if sets_data:
                set_name = sets_data[0].get("name", "")
                variants = sets_data[0].get("variants", [])
                if variants:
                    artist = variants[0].get("artist", "")
                    flavor_text = variants[0].get("flavorText", "")
                    type_text = variants[0].get("typeText", "")

            # Collect all set names
            all_sets = [s.get("name", "") for s in sets_data if s.get("name")]

            thresholds = guardian.get("thresholds", {}) or {}

            mapping[key] = {
                "type": guardian.get("type", ""),
                "rarity": guardian.get("rarity", ""),
                "cost": guardian.get("cost"),
                "attack": guardian.get("attack"),
                "defence": guardian.get("defence"),
                "life": guardian.get("life"),
                "rules_text": guardian.get("rulesText", ""),
                "elements": card.get("elements", "None"),
                "sub_types": card.get("subTypes", ""),
                "thresholds": thresholds,
                "air_threshold": thresholds.get("air", 0),
                "earth_threshold": thresholds.get("earth", 0),
                "fire_threshold": thresholds.get("fire", 0),
                "water_threshold": thresholds.get("water", 0),
                "artist": artist,
                "flavor_text": flavor_text,
                "set": set_name,
                "all_sets": all_sets,
                "type_text": type_text,
            }
    except Exception as e:
        logger.error(f"Failed to load card metadata: {e}")

    _card_metadata = mapping
    return mapping


def _get_card_image_map() -> dict[str, str]:
    """Return {normalized_card_name: filename} dict built from CARD_IMAGES_DIR."""
    global _card_image_map
    if _card_image_map is not None:
        return _card_image_map

    mapping: dict[str, str] = {}
    if CARD_IMAGES_DIR.exists():
        all_files = sorted(os.listdir(CARD_IMAGES_DIR))
        png_files = [f for f in all_files if f.lower().endswith((".png", ".jpg", ".jpeg"))]
        webp_files = [f for f in all_files if f.lower().endswith(".webp")]
        for fname in png_files + webp_files:
            base = re.sub(r"\.(png|jpg|jpeg|webp)$", "", fname, flags=re.IGNORECASE)
            parts = base.split("-")
            if len(parts) >= 2:
                name_key = parts[1]
                mapping[name_key] = fname
    _card_image_map = mapping
    return mapping


def _resolve_card_image(card_name: str) -> str | None:
    """Return image filename for a card name, or None."""
    mapping = _get_card_image_map()
    key = re.sub(r"[^a-z0-9_]", "", card_name.lower().replace(" ", "_"))
    return mapping.get(key)


def _enrich_card(card: dict) -> dict:
    """Enrich a raw Curiosa card with metadata and image."""
    name = card.get("name", "")
    meta_key = re.sub(r"[^a-z0-9]", "", name.lower())
    metadata = _get_card_metadata().get(meta_key, {})

    enriched = {
        "name": name,
        "quantity": card.get("quantity", card.get("qty", 1)),
        "type": metadata.get("type", card.get("type", "")),
        "rarity": metadata.get("rarity", card.get("rarity", "")),
        "cost": metadata.get("cost", card.get("cost", card.get("threshold", 0))),
        "attack": metadata.get("attack"),
        "defence": metadata.get("defence"),
        "life": metadata.get("life"),
        "elements": metadata.get("elements", card.get("elements", "None")),
        "sub_types": metadata.get("sub_types", ""),
        "rules_text": metadata.get("rules_text", ""),
        "artist": metadata.get("artist", ""),
        "flavor_text": metadata.get("flavor_text", ""),
        "set": metadata.get("set", ""),
        "all_sets": metadata.get("all_sets", []),
        "type_text": metadata.get("type_text", ""),
        "thresholds": metadata.get("thresholds", {}),
        "air_threshold": metadata.get("air_threshold", 0),
        "earth_threshold": metadata.get("earth_threshold", 0),
        "fire_threshold": metadata.get("fire_threshold", 0),
        "water_threshold": metadata.get("water_threshold", 0),
        "image": _resolve_card_image(name),
    }
    return enriched


def _enrich_cards(cards: list[dict]) -> list[dict]:
    """Enrich a list of raw Curiosa cards."""
    return [_enrich_card(c) for c in cards]


# Full card name list (cached)
_all_card_names: list[str] | None = None


def _get_all_card_names() -> list[str]:
    """Return sorted list of all card names from the metadata."""
    global _all_card_names
    if _all_card_names is not None:
        return _all_card_names
    try:
        with open(ALL_CARDS_PATH, "r", encoding="utf-8") as f:
            all_cards = json.load(f)
        _all_card_names = sorted(
            [c["name"] for c in all_cards if c.get("name")],
            key=str.lower,
        )
    except Exception as e:
        logger.error(f"Failed to load card names: {e}")
        _all_card_names = []
    return _all_card_names


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


_all_cards_enriched: list[dict] | None = None


@deck_builder_bp.route("/all-cards", methods=["GET"])
def all_cards():
    """Return all available cards with enriched metadata. Cached after first call."""
    global _all_cards_enriched
    if _all_cards_enriched is None:
        names = _get_all_card_names()
        _all_cards_enriched = [_enrich_card({"name": n, "quantity": 1}) for n in names]
    return jsonify(_all_cards_enriched)


@deck_builder_bp.route("/fetch", methods=["POST"])
def fetch_deck():
    """Fetch a deck from Curiosa by URL and return enriched card data."""
    data = request.get_json(silent=True) or {}
    deck_url = (data.get("url") or "").strip()

    if not deck_url:
        return jsonify({"error": "Missing deck URL"}), 400

    # Basic validation
    if "curiosa.io" not in deck_url.lower() and not deck_url.startswith("http"):
        return jsonify({"error": "Invalid deck URL"}), 400

    try:
        service = CuriosaService()
        raw = service.fetch_deck_data(deck_url)
        deck_data = json.loads(raw)

        if not deck_data:
            return jsonify({"error": "Could not fetch deck. Check the URL and try again."}), 404

        # Enrich each section
        avatar = deck_data.get("avatar", [])
        spellbook = deck_data.get("spellbook", [])
        atlas = deck_data.get("atlas", [])
        sideboard = deck_data.get("sideboard", [])

        result = {
            "id": deck_data.get("id", ""),
            "name": deck_data.get("name", "Untitled Deck"),
            "avatar": _enrich_cards(avatar),
            "spellbook": _enrich_cards(spellbook),
            "atlas": _enrich_cards(atlas),
            "sideboard": _enrich_cards(sideboard),
        }

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error fetching deck: {e}")
        return jsonify({"error": "Failed to fetch deck data"}), 500


# ---------------------------------------------------------------------------
# Saved decks (auth required)
# ---------------------------------------------------------------------------

_repo = DeckBuilderRepository()


@deck_builder_bp.route("/save", methods=["POST"])
@require_auth
def save_deck():
    """Save a new deck for the logged-in user."""
    user_id = str(session["user_id"])
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Deck name is required"}), 400

    mainboard = data.get("mainboard", [])
    if not mainboard:
        return jsonify({"error": "Mainboard cannot be empty"}), 400

    deck_id = _repo.save_deck(
        user_id=user_id,
        name=name,
        mainboard=mainboard,
        sideboard=data.get("sideboard", []),
        card_tags=data.get("card_tags", {}),
        avatar=data.get("avatar"),
        source_url=data.get("source_url"),
    )
    return jsonify({"id": deck_id, "message": "Deck saved"}), 201


@deck_builder_bp.route("/<int:deck_id>", methods=["PUT"])
@require_auth
def update_deck(deck_id):
    """Update an existing saved deck."""
    user_id = str(session["user_id"])
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Deck name is required"}), 400

    updated = _repo.update_deck(
        deck_id=deck_id,
        user_id=user_id,
        name=name,
        mainboard=data.get("mainboard", []),
        sideboard=data.get("sideboard", []),
        card_tags=data.get("card_tags", {}),
        avatar=data.get("avatar"),
    )
    if not updated:
        return jsonify({"error": "Deck not found"}), 404
    return jsonify({"message": "Deck updated"})


@deck_builder_bp.route("/my-decks", methods=["GET"])
@require_auth
def list_my_decks():
    """List all saved decks for the logged-in user."""
    user_id = str(session["user_id"])
    search = request.args.get("q", "").strip() or None
    decks = _repo.list_decks(user_id, search=search)
    return jsonify(decks)


@deck_builder_bp.route("/<int:deck_id>", methods=["GET"])
@require_auth
def get_saved_deck(deck_id):
    """Load a saved deck by id (only if owned by user)."""
    user_id = str(session["user_id"])
    deck = _repo.get_deck(deck_id, user_id)
    if not deck:
        return jsonify({"error": "Deck not found"}), 404
    return jsonify(deck)


@deck_builder_bp.route("/<int:deck_id>", methods=["DELETE"])
@require_auth
def delete_saved_deck(deck_id):
    """Delete a saved deck."""
    user_id = str(session["user_id"])
    deleted = _repo.delete_deck(deck_id, user_id)
    if not deleted:
        return jsonify({"error": "Deck not found"}), 404
    return jsonify({"message": "Deck deleted"})
