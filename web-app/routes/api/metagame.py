"""Metagame analysis API routes."""

import logging

from flask import Blueprint, jsonify, request

from utils.auth import is_admin

logger = logging.getLogger(__name__)

metagame_bp = Blueprint("metagame", __name__)


@metagame_bp.route("/metagame/solve", methods=["POST"])
def solve_metagame():
    """Solve a matchup matrix for Nash equilibrium.

    Accepts a CSV file upload with a square matchup matrix.
    Returns optimal mixed strategy, game value, and viable intervals.
    """
    if not is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if not file.filename or not file.filename.endswith(".csv"):
        return jsonify({"error": "File must be a CSV"}), 400

    try:
        from services.metagame import analyze_matchups

        divisions = request.form.get("divisions", 10, type=int)
        threshold = request.form.get("threshold", -0.02, type=float)

        result = analyze_matchups(file.stream, divisions, threshold)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Metagame solve error: {e}")
        return jsonify({"error": f"Failed to solve: {str(e)}"}), 500


@metagame_bp.route("/metagame/matchups")
def archetype_matchups():
    """Auto-generated archetype matchup matrix from match history.

    Query params:
        min_games - minimum games for an archetype to be listed (default 3)
    """
    if not is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    try:
        from services.metagame import build_archetype_matchup_matrix

        min_games = request.args.get("min_games", 3, type=int)
        result = build_archetype_matchup_matrix(min_games=min_games)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Archetype matchup error: {e}")
        return jsonify({"error": f"Failed to build matchups: {str(e)}"}), 500
