"""Metagame analysis API routes."""

import io
import logging

from flask import Blueprint, Response, jsonify, request

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
        n_clusters = request.args.get("n_clusters", 5, type=int)
        n_clusters = max(2, min(8, n_clusters))
        result = build_archetype_matchup_matrix(
            min_games=min_games, n_clusters=n_clusters
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"Archetype matchup error: {e}")
        return jsonify({"error": f"Failed to build matchups: {str(e)}"}), 500


@metagame_bp.route("/metagame/matchups/csv")
def archetype_matchups_csv():
    """Export the archetype matchup win-rate matrix as a CSV download."""
    if not is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    try:
        from services.metagame import build_archetype_matchup_matrix

        min_games = request.args.get("min_games", 3, type=int)
        n_clusters = request.args.get("n_clusters", 5, type=int)
        n_clusters = max(2, min(8, n_clusters))
        data = build_archetype_matchup_matrix(
            min_games=min_games, n_clusters=n_clusters
        )

        archetypes = data["archetypes"]
        wr = data["win_rates"]

        buf = io.StringIO()
        buf.write("archetype," + ",".join(archetypes) + "\n")
        for i, name in enumerate(archetypes):
            row_vals = ",".join(str(v) for v in wr[i])
            buf.write(f"{name},{row_vals}\n")

        return Response(
            buf.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=archetype_matchups.csv"},
        )
    except Exception as e:
        logger.error(f"Archetype CSV export error: {e}")
        return jsonify({"error": f"Failed to export: {str(e)}"}), 500
