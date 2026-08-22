"""Card points API routes for the points-based deck restriction system."""

import json
import logging
import os
import re

import requests as http_requests
from flask import Blueprint, jsonify, request

from repositories.card_catalog import CardCatalogRepository
from repositories.card_points import CardPointsRepository
from services.curiosa import CuriosaService
from utils.auth import require_admin, require_card_points_admin
from webapp_config import CARD_IMAGES_DIR

logger = logging.getLogger(__name__)

card_points_bp = Blueprint("card_points", __name__)


@card_points_bp.route("/search-cards", methods=["GET"])
@require_card_points_admin
def search_cards():
    """Search for cards by name (from card_catalog DB table)."""
    q = request.args.get("q", "").strip().lower()
    if len(q) < 2:
        return jsonify({"success": True, "cards": []})

    catalog = CardCatalogRepository()
    matches = catalog.search_cards(q, limit=20)
    return jsonify({"success": True, "cards": matches})


@card_points_bp.route("", methods=["GET"])
@require_card_points_admin
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
@require_card_points_admin
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
@require_card_points_admin
def delete_card_points(card_name):
    """Remove a card's point assignment."""
    repo = CardPointsRepository()
    deleted = repo.delete_card_points(card_name)
    if not deleted:
        return jsonify({"success": False, "error": "Card not found"}), 404
    return jsonify({"success": True})


@card_points_bp.route("/config", methods=["GET"])
@require_card_points_admin
def get_config():
    """Get points system configuration."""
    repo = CardPointsRepository()
    return jsonify({
        "success": True,
        "max_budget": repo.get_max_budget(),
    })


@card_points_bp.route("/config", methods=["POST"])
@require_card_points_admin
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
            for suffix in ["-b-s", "-b-f", "-bt-s", "-bt-f", "-scg-f", "-bt-s-r", "-d-s", "-d-f", "-op-s", "-tc-f"]:
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
    repo = CardPointsRepository()
    cards = repo.get_all_card_points()
    max_budget = repo.get_max_budget()

    image_lookup = _build_card_image_lookup()
    catalog = CardCatalogRepository()
    for card in cards:
        card["image"] = _find_card_image(card["card_name"], image_lookup)
        meta = catalog.get_card_metadata(card["card_name"])
        card["type"] = meta.get("type", "")
        card["element"] = meta.get("element", "")
        card["rarity"] = meta.get("rarity", "")

    return jsonify({
        "success": True,
        "cards": cards,
        "max_budget": max_budget,
    })


@card_points_bp.route("/history", methods=["GET"])
def get_card_points_history():
    """Public endpoint: get recent card points change history."""
    repo = CardPointsRepository()
    history = repo.get_history(limit=200)
    return jsonify({"success": True, "history": history})


def _is_draftsorcery_url(url: str) -> bool:
    """Check if a URL is from draftsorcery.com."""
    return "draftsorcery.com" in url.lower()


def _fetch_draftsorcery_deck(url: str) -> dict | None:
    """Fetch and normalize a deck from DraftSorcery API.

    Returns deck data in the same format as Curiosa (with avatar, spellbook, atlas, sideboard sections)
    or None on failure.
    """
    from urllib.parse import urlparse, parse_qs

    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    deck_code = params.get("deck", [None])[0]
    if not deck_code:
        return None

    try:
        response = http_requests.get(
            f"https://draftsorcery.com/api/decks/{deck_code}",
            timeout=30,
        )
        if response.status_code != 200:
            logger.warning(f"DraftSorcery API returned status {response.status_code}")
            return None

        data = response.json()
    except (http_requests.exceptions.RequestException, json.JSONDecodeError) as e:
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


@card_points_bp.route("/check-deck", methods=["POST"])
def check_deck():
    """Check if a deck URL meets the points budget."""
    data = request.get_json()
    if not data or not data.get("deck_url", "").strip():
        return jsonify({"success": False, "error": "Deck URL is required."}), 400

    deck_url = data["deck_url"].strip()

    # Fetch deck from DraftSorcery or Curiosa
    if _is_draftsorcery_url(deck_url):
        deck_data = _fetch_draftsorcery_deck(deck_url)
        if not deck_data:
            return jsonify({"success": False, "error": "Could not fetch deck data from DraftSorcery. Check the URL and try again."}), 400
    else:
        service = CuriosaService()
        deck_json_str = service.fetch_deck_data(deck_url)
        if not deck_json_str or deck_json_str == "{}":
            return jsonify({"success": False, "error": "Could not fetch deck data. Check the URL and try again."}), 400

        try:
            deck_data = json.loads(deck_json_str)
        except json.JSONDecodeError:
            return jsonify({"success": False, "error": "Invalid deck data received."}), 400

    # Calculate points
    repo = CardPointsRepository()
    card_points_map = {c["card_name"].lower(): c["point_value"] for c in repo.get_all_card_points()}
    max_budget = repo.get_max_budget()

    total = 0
    costed_cards = []
    for section in ("avatar", "spellbook", "atlas", "sideboard"):
        cards_in_section = deck_data.get(section)
        if not cards_in_section:
            continue
        for card in cards_in_section:
            name = card.get("name", "")
            quantity = card.get("quantity", 1)
            pts = card_points_map.get(name.lower(), 0)
            if pts > 0:
                card_total = pts * quantity
                total += card_total
                costed_cards.append({
                    "name": name,
                    "quantity": quantity,
                    "points_each": pts,
                    "points_total": card_total,
                })

    costed_cards.sort(key=lambda c: -c["points_total"])

    return jsonify({
        "success": True,
        "is_valid": total <= max_budget,
        "total_points": total,
        "max_budget": max_budget,
        "costed_cards": costed_cards,
    })


# ── Card Points Admins (global admin only) ───────────────────────────────────


@card_points_bp.route("/admins", methods=["GET"])
@require_admin
def get_card_points_admins():
    """List card points admins. Global admin only."""
    try:
        repo = CardPointsRepository()
        return jsonify(repo.get_card_points_admins())
    except Exception as e:
        logger.error(f"Error fetching card points admins: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@card_points_bp.route("/admins", methods=["POST"])
@require_admin
def add_card_points_admin():
    """Add a card points admin. Global admin only."""
    data = request.get_json() or {}
    discord_user_id = (data.get("discord_user_id") or "").strip()
    display_name = (data.get("display_name") or "").strip() or None
    if not discord_user_id:
        return jsonify({"error": "discord_user_id is required"}), 400
    try:
        repo = CardPointsRepository()
        repo.add_card_points_admin(discord_user_id, display_name)
        return jsonify({"success": True}), 201
    except Exception as e:
        logger.error(f"Error adding card points admin: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@card_points_bp.route("/admins/<discord_user_id>", methods=["DELETE"])
@require_admin
def remove_card_points_admin(discord_user_id):
    """Remove a card points admin. Global admin only."""
    try:
        repo = CardPointsRepository()
        removed = repo.remove_card_points_admin(discord_user_id)
        if not removed:
            return jsonify({"error": "Admin not found"}), 404
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error removing card points admin: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
