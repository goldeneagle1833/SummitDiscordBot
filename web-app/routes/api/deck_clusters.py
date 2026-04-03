"""Deck clustering API routes."""

from flask import Blueprint, jsonify, request
from services.clustering import ClusteringService

deck_clusters_bp = Blueprint("deck_clusters", __name__)


@deck_clusters_bp.route("/deck-clusters")
def get_deck_clusters():
    """Return clustered deck data from all match reports.

    Query params:
        threshold (float): 0.0-1.0, default 0.6
        metric (str): 'distinct' or 'total', default 'distinct'
        scope (str): 'spells' or 'full', default 'spells'
    """
    threshold = request.args.get("threshold", 0.6, type=float)
    metric = request.args.get("metric", "distinct")
    scope = request.args.get("scope", "spells")

    # Validate params
    threshold = max(0.0, min(1.0, threshold))
    if metric not in ("distinct", "total"):
        metric = "distinct"
    if scope not in ("spells", "full"):
        scope = "spells"

    service = ClusteringService()
    result = service.cluster_match_reports(threshold, metric, scope)

    if result is None:
        return jsonify({"error": "Not enough decks with data to cluster (need at least 2)"}), 404

    return jsonify(result)
