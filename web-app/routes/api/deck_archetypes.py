"""API routes for the Deck Archetypes page.

Endpoints:
  GET /api/deck-archetypes?source=all|tournament              — archetype list
  GET /api/deck-archetypes/<group_id>?source=all|tournament   — one archetype's cards and decks

source=all (default) groups tournament decks and every ranked match deck;
source=tournament groups tournament decks only.
"""

import logging

from flask import Blueprint, jsonify, request

from services import deck_archetypes

logger = logging.getLogger(__name__)

deck_archetypes_bp = Blueprint("deck_archetypes", __name__)


def _source() -> str:
    source = request.args.get("source", "all")
    return source if source in deck_archetypes.SOURCES else "all"


def _building():
    # 202 tells the page the first build is still running; it polls until ready.
    return jsonify({"status": "building"}), 202


@deck_archetypes_bp.route("/deck-archetypes")
def list_archetypes():
    try:
        snapshot = deck_archetypes.get_snapshot(_source())
        if snapshot is None:
            return _building()
        return jsonify({"status": "ready", "meta": snapshot["meta"], "groups": snapshot["groups"]})
    except Exception as e:
        logger.exception("Error listing deck archetypes: %s", e)
        return jsonify({"error": "Failed to load deck archetypes"}), 500


@deck_archetypes_bp.route("/deck-archetypes/<group_id>")
def get_archetype(group_id: str):
    try:
        snapshot = deck_archetypes.get_snapshot(_source())
        if snapshot is None:
            return _building()
        detail = snapshot["details"].get(group_id)
        if detail is None:
            return jsonify({"error": "Archetype not found"}), 404
        return jsonify({"status": "ready", **detail})
    except Exception as e:
        logger.exception("Error loading deck archetype %s: %s", group_id, e)
        return jsonify({"error": "Failed to load deck archetype"}), 500
