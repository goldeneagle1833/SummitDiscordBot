"""API routes for the Deck Archetypes page.

Endpoints:
  GET /api/deck-archetypes                — archetype list
  GET /api/deck-archetypes/<group_id>     — one archetype's cards and decks

Both take:
  source=all|tournament   all (default) groups tournament decks and every ranked
                          match deck; tournament groups tournament decks only
  from=YYYY-MM-DD, to=YYYY-MM-DD
                          only count tournaments and ranked games in this range
  min_event_decks=N       only count tournaments that published at least N decks
"""

import logging
import re

from flask import Blueprint, jsonify, request

from services import deck_archetypes

logger = logging.getLogger(__name__)

deck_archetypes_bp = Blueprint("deck_archetypes", __name__)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _source() -> str:
    source = request.args.get("source", "all")
    return source if source in deck_archetypes.SOURCES else "all"


def _filters() -> deck_archetypes.Filters:
    def date(name):
        value = (request.args.get(name) or "").strip()
        return value if _DATE_RE.match(value) else None

    try:
        min_decks = max(0, min(10000, int(request.args.get("min_event_decks") or 0)))
    except ValueError:
        min_decks = 0
    start, end = date("from"), date("to")
    if start and end and start > end:
        start, end = end, start
    return deck_archetypes.Filters(start=start, end=end, min_event_decks=min_decks)


def _building():
    # 202 tells the page the first build is still running; it polls until ready.
    return jsonify({"status": "building"}), 202


@deck_archetypes_bp.route("/deck-archetypes")
def list_archetypes():
    try:
        result = deck_archetypes.get_list(_source(), _filters())
        if result is None:
            return _building()
        return jsonify({"status": "ready", **result})
    except Exception as e:
        logger.exception("Error listing deck archetypes: %s", e)
        return jsonify({"error": "Failed to load deck archetypes"}), 500


@deck_archetypes_bp.route("/deck-archetypes/<group_id>")
def get_archetype(group_id: str):
    try:
        detail = deck_archetypes.get_detail(_source(), group_id, _filters())
        if detail is None:
            return _building()
        if not detail:
            return jsonify({"error": "Archetype not found"}), 404
        return jsonify({"status": "ready", **detail})
    except Exception as e:
        logger.exception("Error loading deck archetype %s: %s", group_id, e)
        return jsonify({"error": "Failed to load deck archetype"}), 500
