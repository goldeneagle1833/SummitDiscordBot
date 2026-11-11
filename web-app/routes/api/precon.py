"""Precon ladder (Lavamancer vs Frostmage) standings for the website.

Games come in through the Discord bot (its precon queue, Play Sorcery Online
results relayed to it, and admin reports) and are saved in match_records.db;
this only reads them. Nothing here calls Play Sorcery Online.
"""

import logging
import sqlite3

from flask import Blueprint, jsonify, request

import webapp_config
from services import precon_ladder

logger = logging.getLogger(__name__)

precon_bp = Blueprint("precon", __name__)

_SEASON_FIELDS = ("season_id", "name", "starts_at", "ends_at", "ended_at", "is_open", "last_day")


def _public_season(season):
    return {key: season.get(key) for key in _SEASON_FIELDS} if season else None


@precon_bp.route("/precon/standings")
def get_precon_standings():
    """Standings for one precon season (the current or latest one by default).

    Query: ``season_id`` (optional).
    """
    try:
        conn = sqlite3.connect(str(webapp_config.MATCH_RECORDS_DB_PATH), timeout=10)
        try:
            seasons = precon_ladder.list_seasons(conn)
            season = None
            season_id = request.args.get("season_id", type=int)
            if season_id is not None:
                season = next((s for s in seasons if s["season_id"] == season_id), None)
                if season is None:
                    return jsonify({"error": "Season not found"}), 404
            else:
                season = precon_ladder.current_or_latest_season(conn)
            body = {
                "season": _public_season(season),
                "seasons": [_public_season(s) for s in seasons],
                "precons": precon_ladder.precon_choices(),
                "min_ranked_games": precon_ladder.MIN_RANKED_GAMES,
                "standings": [],
                "stats": None,
                "recent": [],
            }
            if season:
                body["standings"] = precon_ladder.standings(conn, season["season_id"])
                body["stats"] = precon_ladder.season_stats(conn, season["season_id"])
                body["recent"] = precon_ladder.recent_matches(conn, season["season_id"], limit=10)
            return jsonify(body)
        finally:
            conn.close()
    except sqlite3.Error as e:
        logger.error("Could not read precon standings: %s", e, exc_info=True)
        return jsonify({"error": "Could not load the precon ladder"}), 500
