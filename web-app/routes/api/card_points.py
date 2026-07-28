"""Card points API routes for the points-based deck restriction system."""

import json
import logging
import os
import re

from flask import Blueprint, jsonify, request

from repositories.card_points import CardPointsRepository
from services.pilots import is_pilot_active
from utils.auth import require_admin, is_admin
from webapp_config import ALL_CARDS_PATH, CARD_IMAGES_DIR

logger = logging.getLogger(__name__)

card_points_bp = Blueprint("card_points", __name__)

# Lazy-loaded card name list from All_Cards_Array.json
_all_card_names: list[str] | None = None


def _get_all_card_names() -> list[str]:
    """Load and cache all card names from the local card database."""
    global _all_card_names
    if _all_card_names is not None:
        return _all_card_names
    try:
        with open(ALL_CARDS_PATH, "r", encoding="utf-8") as f:
            cards = json.load(f)
        _all_card_names = sorted(
            {card["name"] for card in cards if card.get("name")},
            key=str.lower,
        )
    except Exception as e:
        logger.error(f"Failed to load All_Cards_Array.json: {e}")
        _all_card_names = []
    return _all_card_names


@card_points_bp.route("/search-cards", methods=["GET"])
@require_admin
def search_cards():
    """Search for cards by name (from local All_Cards_Array.json)."""
    q = request.args.get("q", "").strip().lower()
    if len(q) < 2:
        return jsonify({"success": True, "cards": []})

    all_names = _get_all_card_names()
    matches = [name for name in all_names if q in name.lower()][:20]
    return jsonify({"success": True, "cards": matches})


@card_points_bp.route("", methods=["GET"])
@require_admin
def get_card_points():
    """Get all cards with assigned point values and the config."""
    repo = CardPointsRepository()
    cards = repo.get_all_card_points()
    max_budget = repo.get_max_budget()
    return jsonify({
        "success": True,
        "cards": cards,
        "max_budget": max_budget,
    })


@card_points_bp.route("", methods=["POST"])
@require_admin
def set_card_points():
    """Set or update point value for a card."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    card_name = data.get("card_name", "").strip()
    point_value = data.get("point_value")

    if not card_name:
        return jsonify({"success": False, "error": "Card name is required"}), 400
    if point_value is None or not isinstance(point_value, int):
        return jsonify({"success": False, "error": "Point value must be an integer"}), 400

    repo = CardPointsRepository()
    card = repo.set_card_points(card_name, point_value)
    return jsonify({"success": True, "card": card})


@card_points_bp.route("/<path:card_name>", methods=["DELETE"])
@require_admin
def delete_card_points(card_name):
    """Remove a card's point assignment."""
    repo = CardPointsRepository()
    deleted = repo.delete_card_points(card_name)
    if not deleted:
        return jsonify({"success": False, "error": "Card not found"}), 404
    return jsonify({"success": True})


@card_points_bp.route("/config", methods=["GET"])
@require_admin
def get_config():
    """Get points system configuration."""
    repo = CardPointsRepository()
    return jsonify({
        "success": True,
        "max_budget": repo.get_max_budget(),
    })


@card_points_bp.route("/config", methods=["POST"])
@require_admin
def set_config():
    """Update points system configuration."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    repo = CardPointsRepository()

    if "max_budget" in data:
        try:
            budget = int(data["max_budget"])
            if budget < 0:
                return jsonify({"success": False, "error": "Budget must be non-negative"}), 400
            repo.set_max_budget(budget)
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Invalid budget value"}), 400

    return jsonify({"success": True, "max_budget": repo.get_max_budget()})


def _build_card_image_lookup():
    """Build card name -> image filename lookup (same logic as cards.py)."""
    lookup = {}
    if CARD_IMAGES_DIR.exists():
        all_files = sorted(os.listdir(CARD_IMAGES_DIR))
        png_files = [f for f in all_files if f.lower().endswith(".png")]
        webp_files = [f for f in all_files if f.lower().endswith(".webp")]
        for filename in png_files + webp_files:
            base = re.sub(r"\.(png|jpg|jpeg|webp)$", "", filename, flags=re.IGNORECASE).lower()
            for suffix in ["-b-s", "-b-f", "-bt-s", "-bt-f", "-scg-f", "-bt-s-r"]:
                if base.endswith(suffix):
                    base = base[:-len(suffix)]
                    break
            if "-" in base:
                card_name_normalized = base.split("-", 1)[1]
                is_standard = "-b-s" in filename.lower() or "-bt-s" in filename.lower()
                if card_name_normalized not in lookup or is_standard:
                    lookup[card_name_normalized] = filename
    return lookup


def _find_card_image(card_name, lookup):
    """Find matching image filename for a card name."""
    normalized = card_name.lower().replace(" ", "_").replace("'", "").replace(",", "")
    normalized = re.sub(r"[^a-z0-9_]", "", normalized)
    return lookup.get(normalized)


@card_points_bp.route("/public", methods=["GET"])
def get_card_points_public():
    """Public endpoint: get all card points + max budget + card images.

    Only available when PointsQueue pilot is active.
    """
    if not is_pilot_active("PointsQueue") and not is_admin():
        return jsonify({"success": False, "error": "Points system is not currently active."}), 404

    repo = CardPointsRepository()
    cards = repo.get_all_card_points()
    max_budget = repo.get_max_budget()

    image_lookup = _build_card_image_lookup()
    for card in cards:
        card["image"] = _find_card_image(card["card_name"], image_lookup)

    return jsonify({
        "success": True,
        "cards": cards,
        "max_budget": max_budget,
    })
