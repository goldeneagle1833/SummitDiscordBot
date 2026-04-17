"""API routes for Sorcery Deck Rec.

Endpoints:
  GET /api/deck-rec/decks                        — list all archetype seeds
  GET /api/deck-rec/<deck_id>/recommendations    — archetype aggregation for a seed
"""

import logging

from flask import Blueprint, jsonify

from repositories.deck_rec_repo import DeckRecRepository
from services.deck_similarity import aggregate_archetype, average_similarity, build_clusters

logger = logging.getLogger(__name__)

deck_rec_bp = Blueprint("deck_rec", __name__)


def _load_and_cluster():
    """Load all decks and build clusters. Returns (seeds, community, clusters)."""
    repo = DeckRecRepository()
    all_decks = repo.load_all_decks()
    seeds = [d for d in all_decks if d.is_seed]
    community = [d for d in all_decks if not d.is_seed]
    clusters = build_clusters(seeds, community)
    return seeds, community, clusters


@deck_rec_bp.route("/decks")
def get_decks():
    """Return all top-8 archetype seed decks with cluster size preview."""
    try:
        seeds, _community, clusters = _load_and_cluster()

        deck_list = []
        for seed in seeds:
            cluster_members = clusters.get(seed.deck_id, [])
            deck_list.append(
                {
                    "deck_id": seed.deck_id,
                    "deck_name": seed.deck_name,
                    "avatar_name": seed.avatar_name,
                    "player_name": seed.player_name,
                    "event_name": seed.event_name,
                    "card_count": seed.card_count,
                    "curiosa_url": seed.curiosa_url,
                    "cluster_size": len(cluster_members),
                }
            )

        # Sort: most community engagement first, then alphabetical
        deck_list.sort(key=lambda d: (-d["cluster_size"], d["deck_name"].lower()))

        return jsonify({"decks": deck_list, "total": len(deck_list)})

    except Exception as e:
        logger.exception("Error in get_decks: %s", e)
        return jsonify({"error": "Failed to load deck data"}), 500


@deck_rec_bp.route("/<deck_id>/recommendations")
def get_recommendations(deck_id: str):
    """Return aggregated archetype recommendation for a top-8 seed deck."""
    try:
        seeds, _community, clusters = _load_and_cluster()

        # Find the seed
        seed = next((s for s in seeds if s.deck_id == deck_id), None)
        if seed is None:
            return jsonify({"error": f"Deck '{deck_id}' not found among archetype seeds"}), 404

        members = clusters.get(seed.deck_id, [])
        tiers = aggregate_archetype(members)
        avg_sim = average_similarity(seed, members)

        return jsonify(
            {
                "seed": {
                    "deck_id": seed.deck_id,
                    "deck_name": seed.deck_name,
                    "avatar_name": seed.avatar_name,
                    "player_name": seed.player_name,
                    "event_name": seed.event_name,
                    "card_count": seed.card_count,
                    "curiosa_url": seed.curiosa_url,
                },
                "cluster_size": len(members),
                "avg_similarity": avg_sim,
                "core_cards": tiers["core"],
                "common_cards": tiers["common"],
                "tech_cards": tiers["tech"],
                "fringe_cards": tiers["fringe"],
            }
        )

    except Exception as e:
        logger.exception("Error in get_recommendations for %s: %s", deck_id, e)
        return jsonify({"error": "Failed to compute recommendations"}), 500
