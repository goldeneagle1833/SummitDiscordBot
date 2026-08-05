"""API routes for Sorcery Deck Rec.

Endpoints:
  GET /api/deck-rec/decks                        — list all archetype seeds
  GET /api/deck-rec/<deck_id>/recommendations    — archetype aggregation for a seed
"""

import json
import logging
import os
import re
import time

from flask import Blueprint, jsonify, request, session

from repositories.deck_rec_repo import DeckRecRepository, _get_card_details
from services.curiosa import CuriosaService
from services.deck_similarity import SIMILARITY_THRESHOLD, aggregate_archetype, average_similarity, build_clusters, jaccard
from utils.auth import is_admin, require_admin
from repositories.card_catalog import CardCatalogRepository
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
        all_files = sorted(os.listdir(CARD_IMAGES_DIR))
        png_files = [f for f in all_files if f.lower().endswith((".png", ".jpg", ".jpeg"))]
        webp_files = [f for f in all_files if f.lower().endswith(".webp")]
        for fname in png_files + webp_files:
            base = re.sub(r"\.(png|jpg|jpeg|webp)$", "", fname, flags=re.IGNORECASE).lower()
            for suffix in ["-b-s", "-b-f", "-bt-s", "-bt-f", "-scg-f", "-bt-s-r", "-d-s", "-d-f", "-op-s", "-tc-f"]:
                if base.endswith(suffix):
                    base = base[:-len(suffix)]
                    break
            if "-" in base:
                card_name_normalized = base.split("-", 1)[1]
                is_standard = "-b-s" in fname.lower() or "-bt-s" in fname.lower()
                if card_name_normalized not in mapping or is_standard:
                    mapping[card_name_normalized] = fname
    _card_image_map = mapping
    return mapping


def _resolve_card_image(card_name: str) -> str | None:
    """Return image filename for a card name, or None if not found."""
    mapping = _get_card_image_map()
    key = re.sub(r"[^a-z0-9_]", "", card_name.lower().replace(" ", "_"))
    return mapping.get(key)


def _attach_images(cards: list[dict]) -> list[dict]:
    """Add 'image' field to each card dict."""
    for card in cards:
        card["image"] = _resolve_card_image(card["card_name"])
    return cards


# ---------------------------------------------------------------------------
# Card metadata lookup — elements, rarity, attack, defence
# ---------------------------------------------------------------------------

_card_metadata: dict[str, dict] | None = None


def _get_card_metadata() -> dict[str, dict]:
    """Return {normalized_name: {elements, rarity, attack, defence}} from card_catalog DB."""
    global _card_metadata
    if _card_metadata is not None:
        return _card_metadata

    meta: dict[str, dict] = {}
    try:
        catalog = CardCatalogRepository()
        for card in catalog.get_all_cards():
            name = (card.get("name") or "").strip().lower()
            if not name:
                continue
            meta[name] = {
                "elements": card.get("elements", "None"),
                "rarity": card.get("rarity", "Unknown"),
                "attack": card.get("attack"),
                "defence": card.get("defence"),
            }
    except Exception as e:
        logger.warning("Failed to load card metadata: %s", e)
    _card_metadata = meta
    return meta


def _enrich_card(card_dict: dict) -> dict:
    """Add elements, rarity, attack, defence to a card dict from All_Cards_Array."""
    meta = _get_card_metadata()
    key = (card_dict.get("name") or "").strip().lower()
    info = meta.get(key, {})
    card_dict["elements"] = info.get("elements", "None")
    card_dict["rarity"] = info.get("rarity", "Unknown")
    card_dict["attack"] = info.get("attack")
    card_dict["defence"] = info.get("defence")
    return card_dict


_cluster_cache = None
_cluster_cache_time = 0
_CLUSTER_CACHE_TTL = 300  # 5 minutes


def _load_and_cluster():
    """Load all decks and build clusters. Returns (repo, seeds, community, clusters).

    Results are cached for 5 minutes to avoid reloading 17k+ decks on every request.
    """
    global _cluster_cache, _cluster_cache_time
    now = time.monotonic()
    if _cluster_cache is not None and (now - _cluster_cache_time) < _CLUSTER_CACHE_TTL:
        return _cluster_cache

    repo = DeckRecRepository()
    all_decks = repo.load_all_decks()
    seeds = [d for d in all_decks if d.is_seed]
    community = [d for d in all_decks if not d.is_seed]
    clusters = build_clusters(seeds, community)
    result = (repo, seeds, community, clusters)
    _cluster_cache = result
    _cluster_cache_time = now
    return result


def _invalidate_cluster_cache():
    """Clear the deck/cluster cache so the next request reloads fresh data."""
    global _cluster_cache, _cluster_cache_time
    _cluster_cache = None
    _cluster_cache_time = 0


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


@deck_rec_bp.route("/<deck_id>/info")
def get_deck_info(deck_id: str):
    """Return seed info + deck contents without expensive clustering.

    Falls back to fetching directly from Curiosa if the deck isn't a seed
    (e.g. event decks linked from the top-8 page).
    """
    try:
        _repo, seeds, _community, _clusters = _load_and_cluster()
        seed = next((d for d in seeds if d.deck_id == deck_id), None)

        # Fallback: fetch from Curiosa for non-seed decks (event page links)
        if seed is None:
            return _fetch_curiosa_deck_info(deck_id)

        # For admin/staff decks, fetch live from Curiosa
        detail_source = seed.card_details
        sideboard_source = seed.sideboard_details
        if (seed.is_admin_rec or not detail_source) and seed.curiosa_url:
            try:
                fresh_json = CuriosaService().fetch_deck_data(seed.curiosa_url)
                if fresh_json and fresh_json not in ("{}", ""):
                    fresh_data = json.loads(fresh_json)
                    live_details = _get_card_details(
                        fresh_data.get("spellbook", []),
                        fresh_data.get("atlas", []),
                    )
                    if live_details:
                        detail_source = live_details
                    live_sideboard = _get_card_details(fresh_data.get("sideboard", []))
                    if live_sideboard:
                        sideboard_source = live_sideboard
            except Exception as e:
                logger.warning("Could not fetch live Curiosa data for %s: %s", seed.deck_id, e)

        seed_cards = [{"name": c["name"], "qty": c["qty"]} for c in detail_source]
        seed_spellbook = [
            _enrich_card({
                "name": c["name"],
                "qty": c["qty"],
                "type": c["type"],
                "threshold": c["threshold"],
                "image": _resolve_card_image(c["name"]),
            })
            for c in detail_source
        ]
        seed_sideboard = [
            _enrich_card({
                "name": c["name"],
                "qty": c["qty"],
                "type": c["type"],
                "threshold": c["threshold"],
                "image": _resolve_card_image(c["name"]),
            })
            for c in sideboard_source
        ]

        return jsonify({
            "seed": {
                "deck_id": seed.deck_id,
                "deck_name": seed.deck_name,
                "avatar_name": seed.avatar_name,
                "player_name": seed.player_name,
                "event_name": seed.event_name,
                "card_count": seed.card_count,
                "curiosa_url": seed.curiosa_url,
                "primer": seed.primer or "",
            },
            "seed_cards": seed_cards,
            "seed_spellbook": seed_spellbook,
            "seed_sideboard": seed_sideboard,
        })
    except Exception as e:
        logger.exception("Error in get_deck_info for %s: %s", deck_id, e)
        return jsonify({"error": "Failed to load deck info"}), 500


def _fetch_curiosa_deck_info(deck_id: str):
    """Fetch deck info directly from Curiosa API for non-seed decks."""
    curiosa_url = f"https://curiosa.io/decks/{deck_id}"
    try:
        fresh_json = CuriosaService().fetch_deck_data(curiosa_url)
        if not fresh_json or fresh_json in ("{}", ""):
            return jsonify({"error": f"Deck '{deck_id}' not found on Curiosa"}), 404

        fresh_data = json.loads(fresh_json)
        deck_name = fresh_data.get("name", "Unnamed Deck")
        username = fresh_data.get("username", "Unknown")
        avatar_list = fresh_data.get("avatar", [])
        avatar_name = avatar_list[0].get("name", "Unknown") if avatar_list else "Unknown"

        detail_source = _get_card_details(
            fresh_data.get("spellbook", []),
            fresh_data.get("atlas", []),
        )
        sideboard_source = _get_card_details(fresh_data.get("sideboard", []))

        seed_cards = [{"name": c["name"], "qty": c["qty"]} for c in detail_source]
        seed_spellbook = [
            _enrich_card({
                "name": c["name"],
                "qty": c["qty"],
                "type": c["type"],
                "threshold": c["threshold"],
                "image": _resolve_card_image(c["name"]),
            })
            for c in detail_source
        ]
        seed_sideboard = [
            _enrich_card({
                "name": c["name"],
                "qty": c["qty"],
                "type": c["type"],
                "threshold": c["threshold"],
                "image": _resolve_card_image(c["name"]),
            })
            for c in sideboard_source
        ]

        return jsonify({
            "seed": {
                "deck_id": deck_id,
                "deck_name": deck_name,
                "avatar_name": avatar_name,
                "player_name": username,
                "event_name": "",
                "card_count": sum(c["qty"] for c in detail_source),
                "curiosa_url": curiosa_url,
                "primer": "",
            },
            "seed_cards": seed_cards,
            "seed_spellbook": seed_spellbook,
            "seed_sideboard": seed_sideboard,
        })
    except Exception as e:
        logger.warning("Could not fetch Curiosa deck %s: %s", deck_id, e)
        return jsonify({"error": f"Deck '{deck_id}' not found"}), 404


@deck_rec_bp.route("/<deck_id>/recommendations")
def get_recommendations(deck_id: str):
    """Return aggregated archetype recommendation for a top-8 seed deck."""
    try:
        repo, seeds, community, _clusters = _load_and_cluster()

        # Find the seed
        seed = next((s for s in seeds if s.deck_id == deck_id), None)
        if seed is None:
            # Non-seed deck (e.g. event page link) — no recommendations available
            return jsonify({"tiers": [], "avg_similarity": 0, "similar_seeds": [], "cluster_size": 0})

        # Use inclusive matching so admin picks and tournament seeds are treated
        # identically — show all community decks above the threshold, not just
        # those whose single best-match seed happens to be this one.
        members = [d for d in community if jaccard(seed.card_names, d.card_names) >= SIMILARITY_THRESHOLD]
        tiers = aggregate_archetype(members)
        avg_sim = average_similarity(seed, members)
        win_data = repo.compute_cluster_win_rate(seed)

        # Find similar tournament seed decks (>= 60% Jaccard similarity)
        SIMILAR_SEED_THRESHOLD = 0.6
        similar_seeds = []
        for other in seeds:
            if other.deck_id == seed.deck_id:
                continue
            score = jaccard(seed.card_names, other.card_names)
            if score >= SIMILAR_SEED_THRESHOLD:
                similar_seeds.append({
                    "deck_id": other.deck_id,
                    "deck_name": other.deck_name,
                    "avatar_name": other.avatar_name,
                    "player_name": other.player_name,
                    "event_name": other.event_name,
                    "similarity": round(score, 3),
                })
        similar_seeds.sort(key=lambda x: x["similarity"], reverse=True)

        # For admin/staff decks (or any seed missing card details), fetch live from Curiosa
        detail_source = seed.card_details
        if (seed.is_admin_rec or not detail_source) and seed.curiosa_url:
            try:
                fresh_json = CuriosaService().fetch_deck_data(seed.curiosa_url)
                if fresh_json and fresh_json not in ("{}", ""):
                    fresh_data = json.loads(fresh_json)
                    live_details = _get_card_details(
                        fresh_data.get("spellbook", []),
                        fresh_data.get("atlas", []),
                    )
                    if live_details:
                        detail_source = live_details
            except Exception as e:
                logger.warning("Could not fetch live Curiosa data for %s: %s", seed.deck_id, e)

        # seed_cards: flat list for TCGPlayer buy link (spellbook + atlas)
        seed_cards = [
            {"name": c["name"], "qty": c["qty"]}
            for c in detail_source
        ]

        # seed_spellbook: rich list for deck contents display
        seed_spellbook = [
            _enrich_card({
                "name": c["name"],
                "qty": c["qty"],
                "type": c["type"],
                "threshold": c["threshold"],
                "image": _resolve_card_image(c["name"]),
            })
            for c in detail_source
        ]

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
                    "primer": seed.primer or "",
                },
                "seed_cards": seed_cards,
                "seed_spellbook": seed_spellbook,
                "cluster_size": len(members),
                "avg_similarity": avg_sim,
                "wins": win_data["wins"],
                "losses": win_data["losses"],
                "win_rate": win_data["win_rate"],
                "core_cards": _attach_images(tiers["core"]),
                "common_cards": _attach_images(tiers["common"]),
                "tech_cards": _attach_images(tiers["tech"]),
                "fringe_cards": _attach_images(tiers["fringe"]),
                "similar_seeds": similar_seeds,
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

        # Invalidate caches so new deck renders correctly
        global _card_image_map
        _card_image_map = None
        _invalidate_cluster_cache()

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
        _invalidate_cluster_cache()
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
        _invalidate_cluster_cache()
        return jsonify({"ok": True})
    except Exception as e:
        logger.exception("Error in admin_remove_deck for %s: %s", deck_id, e)
        return jsonify({"error": "Failed to remove deck"}), 500
