"""API routes for Sorcery Deck Rec.

Endpoints:
  GET /api/deck-rec/decks                        — list all archetype seeds
  GET /api/deck-rec/<deck_id>/recommendations    — archetype aggregation for a seed
"""

import json
import logging
import os
import re

from flask import Blueprint, jsonify, request, session

from repositories.deck_rec_repo import DeckRecRepository
from services.curiosa import CuriosaService
from services.deck_similarity import SIMILARITY_THRESHOLD, aggregate_archetype, average_similarity, build_clusters, jaccard
from utils.auth import is_admin, require_admin
from webapp_config import CARD_IMAGES_DIR

logger = logging.getLogger(__name__)

deck_rec_bp = Blueprint("deck_rec", __name__)

# ---------------------------------------------------------------------------
# Card image lookup — built once, cached at module level
# ---------------------------------------------------------------------------

_card_image_map: dict[str, str] | None = None


def _get_card_image_map() -> dict[str, str]:
    """Return a {normalized_card_name: filename} dict built from CARD_IMAGES_DIR."""
    global _card_image_map
    if _card_image_map is not None:
        return _card_image_map

    mapping: dict[str, str] = {}
    if CARD_IMAGES_DIR.exists():
        # Process png/jpg first, then webp so webp takes precedence
        all_files = sorted(os.listdir(CARD_IMAGES_DIR))
        png_files = [f for f in all_files if f.lower().endswith((".png", ".jpg", ".jpeg"))]
        webp_files = [f for f in all_files if f.lower().endswith(".webp")]
        for fname in png_files + webp_files:
            # Filename format: {set}-{card_name_slug}-{edition}-{rarity}.ext
            # e.g. pro-witch-ai-f.webp → card name slug is parts[1] = "witch"
            base = re.sub(r"\.(png|jpg|jpeg|webp)$", "", fname, flags=re.IGNORECASE)
            parts = base.split("-")
            if len(parts) >= 2:
                name_key = parts[1]  # card name slug is always the second segment
                mapping[name_key] = fname
    _card_image_map = mapping
    return mapping


def _resolve_card_image(card_name: str) -> str | None:
    """Return image filename for a card name, or None if not found."""
    mapping = _get_card_image_map()
    key = card_name.lower().replace(" ", "_").replace("'", "").replace(",", "")
    return mapping.get(key)


def _attach_images(cards: list[dict]) -> list[dict]:
    """Add 'image' field to each card dict."""
    for card in cards:
        card["image"] = _resolve_card_image(card["card_name"])
    return cards


def _load_and_cluster():
    """Load all decks and build clusters. Returns (repo, seeds, community, clusters)."""
    repo = DeckRecRepository()
    all_decks = repo.load_all_decks()
    seeds = [d for d in all_decks if d.is_seed]
    community = [d for d in all_decks if not d.is_seed]
    clusters = build_clusters(seeds, community)
    return repo, seeds, community, clusters


@deck_rec_bp.route("/decks")
def get_decks():
    """Return all top-8 archetype seed decks with cluster size preview."""
    try:
        _repo, seeds, _community, clusters = _load_and_cluster()

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
                    "elements": sorted(seed.elements),
                    "event_year": seed.event_year,
                    "is_admin_rec": seed.is_admin_rec,
                    "primer": seed.primer or "",
                    "stars": seed.stars,
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
        repo, seeds, community, _clusters = _load_and_cluster()

        # Find the seed
        seed = next((s for s in seeds if s.deck_id == deck_id), None)
        if seed is None:
            return jsonify({"error": f"Deck '{deck_id}' not found among archetype seeds"}), 404

        # Use inclusive matching so admin picks and tournament seeds are treated
        # identically — show all community decks above the threshold, not just
        # those whose single best-match seed happens to be this one.
        members = [d for d in community if jaccard(seed.card_names, d.card_names) >= SIMILARITY_THRESHOLD]
        tiers = aggregate_archetype(members)
        avg_sim = average_similarity(seed, members)
        win_data = repo.compute_cluster_win_rate(seed)

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
                "wins": win_data["wins"],
                "losses": win_data["losses"],
                "win_rate": win_data["win_rate"],
                "core_cards": _attach_images(tiers["core"]),
                "common_cards": _attach_images(tiers["common"]),
                "tech_cards": _attach_images(tiers["tech"]),
                "fringe_cards": _attach_images(tiers["fringe"]),
            }
        )

    except Exception as e:
        logger.exception("Error in get_recommendations for %s: %s", deck_id, e)
        return jsonify({"error": "Failed to compute recommendations"}), 500


@deck_rec_bp.route("/admin/add-deck", methods=["POST"])
@require_admin
def admin_add_deck():
    """Add an admin-recommended deck by Curiosa URL. Admin only."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        curiosa_url = (data.get("curiosa_url") or "").strip()
        if not curiosa_url:
            return jsonify({"error": "curiosa_url is required"}), 400

        primer = (data.get("primer") or "").strip()
        raw_stars = data.get("stars")
        stars = int(raw_stars) if raw_stars in (1, 2, 3, "1", "2", "3") else None

        svc = CuriosaService()
        deck_id = svc.get_deck_id_from_url(curiosa_url)
        if not deck_id:
            return jsonify({"error": "Could not extract deck ID from URL"}), 400

        json_deck_data = svc.fetch_deck_data(curiosa_url)
        deck_data = json.loads(json_deck_data) if json_deck_data not in ("{}", "") else {}

        deck_name = deck_data.get("name", "") or ""
        avatar_name = (deck_data.get("avatar") or [{}])[0].get("name", "") or ""
        added_by = session.get("username") or str(session.get("user_id", "admin"))

        repo = DeckRecRepository()
        repo.save_admin_deck(
            deck_id=deck_id,
            curiosa_url=curiosa_url,
            deck_name=deck_name,
            avatar_name=avatar_name,
            json_deck_data=json_deck_data,
            added_by=added_by,
            primer=primer,
            stars=stars,
        )

        # Invalidate card image cache so new deck renders correctly
        global _card_image_map
        _card_image_map = None

        return jsonify({
            "ok": True,
            "deck_id": deck_id,
            "deck_name": deck_name,
            "avatar_name": avatar_name,
        })

    except Exception as e:
        logger.exception("Error in admin_add_deck: %s", e)
        return jsonify({"error": "Failed to add deck"}), 500


@deck_rec_bp.route("/admin/update-deck/<deck_id>", methods=["PATCH"])
@require_admin
def admin_update_deck(deck_id: str):
    """Update primer and stars for an existing admin deck. Admin only."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        primer = (data.get("primer") or "").strip()
        raw_stars = data.get("stars")
        stars = int(raw_stars) if raw_stars in (1, 2, 3, "1", "2", "3") else None

        repo = DeckRecRepository()
        updated = repo.update_admin_deck_meta(deck_id, primer, stars)
        if not updated:
            return jsonify({"error": "Deck not found"}), 404
        return jsonify({"ok": True})
    except Exception as e:
        logger.exception("Error in admin_update_deck for %s: %s", deck_id, e)
        return jsonify({"error": "Failed to update deck"}), 500


@deck_rec_bp.route("/admin/remove-deck/<deck_id>", methods=["DELETE"])
@require_admin
def admin_remove_deck(deck_id: str):
    """Remove an admin-recommended deck. Admin only."""
    try:
        repo = DeckRecRepository()
        deleted = repo.delete_admin_deck(deck_id)
        if not deleted:
            return jsonify({"error": "Deck not found"}), 404
        return jsonify({"ok": True})
    except Exception as e:
        logger.exception("Error in admin_remove_deck for %s: %s", deck_id, e)
        return jsonify({"error": "Failed to remove deck"}), 500
