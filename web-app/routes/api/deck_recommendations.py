"""API routes for Sorcery Deck Rec.

Endpoints:
  GET  /api/deck-rec/decks                        — list all archetype seeds
  GET  /api/deck-rec/<deck_id>/recommendations    — archetype aggregation for a seed
  POST /api/deck-rec/<deck_id>/pso-table          — open a Sorcery Online table with the deck
"""

import json
import logging
import os
import random
import re
import sqlite3
import threading
import time
from array import array
from datetime import date
from typing import NamedTuple

from flask import Blueprint, jsonify, request, session

from repositories.deck_rec_repo import DeckRecRepository, DeckRecord, MatchOutcomeIndex, _get_card_details
from services.curiosa import CuriosaService
from services.deck_similarity import (
    aggregate_archetype,
    build_card_index,
    build_clusters,
    jaccard,
    similar_members,
)
from services.sorcery_online_table import (
    TableUnavailable,
    claim_slot,
    is_configured,
    provision_deck_table,
    release_slot,
)
from utils.auth import is_admin, require_admin
from utils.formatting import normalize_card_name
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
            else:
                card_name_normalized = base
            is_standard = "-b-s" in fname.lower() or "-bt-s" in fname.lower()
            if card_name_normalized not in mapping or is_standard:
                mapping[card_name_normalized] = fname
    _card_image_map = mapping
    return mapping


def _resolve_card_image(card_name: str) -> str | None:
    """Return image filename for a card name, or None if not found."""
    mapping = _get_card_image_map()
    key = normalize_card_name(card_name)
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


# ---------------------------------------------------------------------------
# Deck corpus caches
# ---------------------------------------------------------------------------
#
# Two separate caches, because the two things pages ask for cost wildly
# different amounts:
#
#   seeds  — tournament + admin decks only, read from JSON files and a small
#            table. Under a second. Enough to render a deck page.
#   corpus — the above plus every community deck in the match archive, and the
#            clustering that ranks the listing. Tens of thousands of decks.
#
# Endpoints that only need to look a deck up by id take the cheap one. The
# expensive one is refreshed on a background thread while the previous snapshot
# keeps being served, so no visitor waits behind a rebuild.

_SEED_CACHE_TTL = 300      # 5 minutes
_CORPUS_CACHE_TTL = 900    # 15 minutes

_seed_cache: tuple[DeckRecRepository, list[DeckRecord]] | None = None
_seed_cache_time = 0.0
_seed_lock = threading.Lock()


class DeckCorpus(NamedTuple):
    """One immutable snapshot of every deck plus the indexes built over it."""

    repo: DeckRecRepository
    seeds: list[DeckRecord]
    community: list[DeckRecord]
    clusters: dict[str, list[DeckRecord]]
    community_index: dict[str, array]
    community_lengths: array
    outcomes: MatchOutcomeIndex


_corpus_cache: DeckCorpus | None = None
_corpus_cache_time = 0.0
_corpus_lock = threading.Lock()
_corpus_refreshing = False


def _load_seeds() -> tuple[DeckRecRepository, list[DeckRecord]]:
    """Return (repo, seed decks) — tournament and admin decks only.

    Skips the match archive and the clustering entirely, so endpoints that just
    need to find one deck by id do not pay for the whole corpus.
    """
    global _seed_cache, _seed_cache_time
    cached = _seed_cache
    if cached is not None and (time.monotonic() - _seed_cache_time) < _SEED_CACHE_TTL:
        return cached

    with _seed_lock:
        # Another thread may have rebuilt it while we waited for the lock.
        cached = _seed_cache
        if cached is not None and (time.monotonic() - _seed_cache_time) < _SEED_CACHE_TTL:
            return cached
        repo = DeckRecRepository()
        result = (repo, repo.load_seed_decks())
        _seed_cache = result
        _seed_cache_time = time.monotonic()
        return result


def _build_corpus() -> DeckCorpus:
    """Load every deck and build the clustering and lookup indexes."""
    started = time.monotonic()
    repo = DeckRecRepository()
    all_decks, outcomes = repo.load_corpus()
    seeds = [d for d in all_decks if d.is_seed]
    community = [d for d in all_decks if not d.is_seed]
    clusters = build_clusters(seeds, community)
    community_index, community_lengths = build_card_index(community)
    logger.info(
        "Built deck corpus: %d seeds, %d community decks in %.1fs",
        len(seeds),
        len(community),
        time.monotonic() - started,
    )
    return DeckCorpus(repo, seeds, community, clusters, community_index, community_lengths, outcomes)


def _refresh_corpus_async() -> None:
    """Rebuild the corpus on a background thread, if one is not already running."""
    global _corpus_refreshing
    with _corpus_lock:
        if _corpus_refreshing:
            return
        _corpus_refreshing = True

    def run() -> None:
        global _corpus_cache, _corpus_cache_time, _corpus_refreshing
        try:
            _corpus_cache = _build_corpus()
        except Exception:
            logger.exception("Background deck corpus refresh failed; serving the previous snapshot")
        finally:
            # Either way, wait a full TTL before trying again rather than
            # rebuilding on every request while the data source is unhappy.
            _corpus_cache_time = time.monotonic()
            _corpus_refreshing = False

    threading.Thread(target=run, name="deck-rec-corpus-refresh", daemon=True).start()


def _load_and_cluster() -> DeckCorpus:
    """Return the current deck corpus snapshot.

    A stale snapshot is returned immediately and refreshed in the background.
    Only the very first call (or one right after an invalidation) blocks, and
    concurrent callers share that single build instead of each starting one.
    """
    global _corpus_cache, _corpus_cache_time

    snapshot = _corpus_cache
    if snapshot is not None:
        if (time.monotonic() - _corpus_cache_time) >= _CORPUS_CACHE_TTL:
            _refresh_corpus_async()
        return snapshot

    with _corpus_lock:
        if _corpus_cache is not None:
            return _corpus_cache
        _corpus_cache = _build_corpus()
        _corpus_cache_time = time.monotonic()
        return _corpus_cache


def warm_deck_caches() -> None:
    """Build the corpus ahead of the first request, on a background thread."""
    threading.Thread(target=_load_and_cluster, name="deck-rec-corpus-warmup", daemon=True).start()


def _invalidate_cluster_cache():
    """Clear the deck caches so the next request reloads fresh data."""
    global _corpus_cache, _corpus_cache_time, _seed_cache, _seed_cache_time
    _corpus_cache = None
    _corpus_cache_time = 0.0
    _seed_cache = None
    _seed_cache_time = 0.0


# ---------------------------------------------------------------------------
# Live Curiosa lookups
# ---------------------------------------------------------------------------
#
# Staff picks are re-fetched from Curiosa so edits show up without re-adding the
# deck, but a single page view hits both /info and /recommendations. Without a
# cache that is two uncached external calls — each rate-limited, each with a
# 30 second ceiling — for identical data.

_LIVE_DECK_TTL = 300  # 5 minutes
_live_deck_cache: dict[str, tuple[float, dict | None]] = {}
_live_deck_lock = threading.Lock()


def _fetch_live_deck(curiosa_url: str) -> dict | None:
    """Return freshly fetched Curiosa deck data, cached briefly. None on failure."""
    now = time.monotonic()
    with _live_deck_lock:
        entry = _live_deck_cache.get(curiosa_url)
        if entry is not None and (now - entry[0]) < _LIVE_DECK_TTL:
            return entry[1]

    data = None
    try:
        fresh_json = CuriosaService().fetch_deck_data(curiosa_url)
        if fresh_json and fresh_json not in ("{}", ""):
            data = json.loads(fresh_json)
    except Exception as e:
        logger.warning("Could not fetch live Curiosa data for %s: %s", curiosa_url, e)

    with _live_deck_lock:
        # Negative results are cached too, so an unreachable Curiosa costs one
        # slow call per deck per TTL rather than one on every page view.
        _live_deck_cache[curiosa_url] = (time.monotonic(), data)
    return data


def _get_newest_admin_deck(repo):
    """Return the newest admin deck if added within the last 48 hours, else None."""
    from datetime import datetime, timezone, timedelta
    try:
        conn = sqlite3.connect(str(repo._db_path))
        conn.row_factory = sqlite3.Row
        repo._ensure_admin_table(conn)
        cur = conn.execute(
            "SELECT deck_id, added_at FROM admin_recommended_decks ORDER BY added_at DESC LIMIT 1"
        )
        row = cur.fetchone()
        conn.close()
        if not row or not row["added_at"]:
            return None
        added = datetime.fromisoformat(row["added_at"]).replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - added > timedelta(hours=48):
            return None
        # Find the matching DeckRecord from the loaded admin decks
        admin_decks = repo._load_admin_decks()
        return next((d for d in admin_decks if d.deck_id == row["deck_id"]), None)
    except Exception:
        return None


@deck_rec_bp.route("/staff-pick")
def staff_pick():
    """Return a staff-pick deck for the homepage carousel.

    Shows the newest admin deck for 48 hours after it's added, then
    rotates daily through a random pick until a new deck is added.
    """
    try:
        repo = DeckRecRepository()
        admin_decks = repo._load_admin_decks()
        if not admin_decks:
            return jsonify({"success": False})

        # Check for a recently added deck (within 48 hours)
        deck = _get_newest_admin_deck(repo)
        is_new = deck is not None

        if deck is None:
            # Rotate daily through a random pick
            rng = random.Random(str(date.today()) + "staff-pick")
            deck = rng.choice(admin_decks)

        # Resolve avatar image — strip non-alphanumeric for fuzzy match
        avatar_image = None
        if deck.avatar_name:
            norm = normalize_card_name(deck.avatar_name).replace("_", "")
            from webapp_config import AVATAR_IMAGES_DIR
            if AVATAR_IMAGES_DIR.exists():
                for fname in os.listdir(AVATAR_IMAGES_DIR):
                    if not fname.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                        continue
                    fname_norm = normalize_card_name(fname.rsplit('.', 1)[0]).replace("_", "")
                    if norm in fname_norm or fname_norm.startswith(norm):
                        avatar_image = f"/avatar-images/{fname}"
                        break

        return jsonify({
            "success": True,
            "staff_pick": {
                "deck_id": deck.deck_id,
                "deck_name": deck.deck_name,
                "avatar_name": deck.avatar_name,
                "primer": deck.primer or "",
                "stars": deck.stars,
                "curiosa_url": deck.curiosa_url,
                "is_new": is_new,
                "avatar_image": avatar_image,
            },
        })
    except Exception as e:
        logger.exception("Error in staff_pick: %s", e)
        return jsonify({"success": False}), 500


@deck_rec_bp.route("/decks")
def get_decks():
    """Return all top-8 archetype seed decks with cluster size preview."""
    try:
        corpus = _load_and_cluster()
        seeds, clusters = corpus.seeds, corpus.clusters

        # Filter out hidden decks (admins can opt-in to see them)
        hidden_ids = corpus.repo.get_hidden_deck_ids()
        show_hidden = request.args.get("show_hidden") == "1" and is_admin()

        deck_list = []
        for seed in seeds:
            is_hidden = seed.deck_id in hidden_ids
            if is_hidden and not show_hidden:
                continue
            cluster_members = clusters.get(seed.deck_id, [])
            entry = {
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
            if show_hidden:
                entry["is_hidden"] = is_hidden
            deck_list.append(entry)

        # Sort: most community engagement first, then alphabetical
        deck_list.sort(key=lambda d: (-d["cluster_size"], d["deck_name"].lower()))

        return jsonify({"decks": deck_list, "total": len(deck_list), "hidden_count": len(hidden_ids)})

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
        _repo, seeds = _load_seeds()
        seed = next((d for d in seeds if d.deck_id == deck_id), None)

        # Fallback: fetch from Curiosa for non-seed decks (event page links)
        if seed is None:
            return _fetch_curiosa_deck_info(deck_id)

        # For admin/staff decks, fetch live from Curiosa
        detail_source = seed.card_details
        sideboard_source = seed.sideboard_details
        if (seed.is_admin_rec or not detail_source) and seed.curiosa_url:
            fresh_data = _fetch_live_deck(seed.curiosa_url)
            if fresh_data:
                live_details = _get_card_details(
                    fresh_data.get("spellbook", []),
                    fresh_data.get("atlas", []),
                )
                if live_details:
                    detail_source = live_details
                live_sideboard = _get_card_details(fresh_data.get("sideboard", []))
                if live_sideboard:
                    sideboard_source = live_sideboard

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
    curiosa_url = f"https://sorcerytcg.com/decks/{deck_id}"
    try:
        fresh_data = _fetch_live_deck(curiosa_url)
        if not fresh_data:
            return jsonify({"error": f"Deck '{deck_id}' not found on Curiosa"}), 404

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
        corpus = _load_and_cluster()
        seeds = corpus.seeds

        # Find the seed
        seed = next((s for s in seeds if s.deck_id == deck_id), None)
        if seed is None:
            # Non-seed deck (e.g. event page link) — no recommendations available
            return jsonify({"tiers": [], "avg_similarity": 0, "similar_seeds": [], "cluster_size": 0})

        # Use inclusive matching so admin picks and tournament seeds are treated
        # identically — show all community decks above the threshold, not just
        # those whose single best-match seed happens to be this one.
        scored_members = similar_members(
            seed, corpus.community, corpus.community_index, corpus.community_lengths
        )
        members = [deck for deck, _score in scored_members]
        tiers = aggregate_archetype(members)
        avg_sim = (
            round(sum(score for _deck, score in scored_members) / len(scored_members), 4)
            if scored_members
            else 0.0
        )
        win_data = corpus.repo.compute_cluster_win_rate(seed, corpus.outcomes)

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
            fresh_data = _fetch_live_deck(seed.curiosa_url)
            if fresh_data:
                live_details = _get_card_details(
                    fresh_data.get("spellbook", []),
                    fresh_data.get("atlas", []),
                )
                if live_details:
                    detail_source = live_details

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


# ---------------------------------------------------------------------------
# "Try this Deck" — open a Sorcery Online table with the deck preloaded
# ---------------------------------------------------------------------------

_DECK_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}$")


def _client_key() -> str:
    """Identify the caller for throttling — session first, then client IP."""
    user_id = session.get("user_id")
    if user_id:
        return f"user:{user_id}"
    ip = (
        request.headers.get("CF-Connecting-IP")
        or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.remote_addr
        or "unknown"
    )
    return f"ip:{ip}"


def _resolve_deck_url(deck_id: str) -> tuple[str | None, str]:
    """Return (curiosa_url, deck_name) for a deck-rec deck, or (None, "") if unusable.

    Seeds carry their own Curiosa URL. Decks linked from the event pages aren't
    seeds, so they get the canonical Curiosa URL for their id — the same
    fallback `get_deck_info` uses.
    """
    repo, seeds = _load_seeds()
    seed = next((d for d in seeds if d.deck_id == deck_id), None)

    if seed is not None:
        if seed.deck_id in repo.get_hidden_deck_ids() and not is_admin():
            return None, ""
        return seed.curiosa_url or f"https://sorcerytcg.com/decks/{deck_id}", seed.deck_name or ""
    return f"https://sorcerytcg.com/decks/{deck_id}", ""


@deck_rec_bp.route("/<deck_id>/pso-table", methods=["POST"])
def create_pso_table(deck_id: str):
    """Provision a Sorcery Online table with this deck already loaded.

    Same provisioning the LFG queue uses when it pairs two players, except the
    second seat is left open — the visitor gets the deck, and `invite_url` is
    the link an opponent can join on.
    """
    if not _DECK_ID_RE.match(deck_id or ""):
        return jsonify({"error": "Invalid deck id"}), 400
    if not is_configured():
        return jsonify({"error": "Sorcery Online is not connected right now."}), 503

    try:
        deck_url, deck_name = _resolve_deck_url(deck_id)
    except Exception as e:
        logger.exception("Error resolving deck %s for Sorcery Online: %s", deck_id, e)
        return jsonify({"error": "Failed to load that deck"}), 500
    if not deck_url:
        return jsonify({"error": "Deck not found"}), 404

    client_key = _client_key()
    wait_seconds = claim_slot(client_key)
    if wait_seconds:
        return jsonify({
            "error": "Give it a few seconds before opening another table.",
            "retry_after": wait_seconds,
        }), 429

    # Only Discord sessions carry an id Sorcery Online recognises; Google
    # logins (prefixed "google_") and anonymous visitors get a generated seat id.
    user_id = str(session.get("user_id") or "")
    display_name = session.get("username") or "Summit Player"
    try:
        table = provision_deck_table(
            deck_url,
            display_name=display_name,
            player_id=user_id if user_id.isdigit() else None,
        )
    except TableUnavailable as e:
        release_slot(client_key)
        return jsonify({"error": str(e)}), 502
    except Exception as e:
        release_slot(client_key)
        logger.exception("Unexpected Sorcery Online failure for %s: %s", deck_id, e)
        return jsonify({"error": "Could not open a Sorcery Online table."}), 502

    logger.info("Opened Sorcery Online table for deck %s (%s)", deck_id, deck_name)
    return jsonify({
        "game_url": table.game_url,
        "invite_url": table.invite_url,
        "deck_name": deck_name,
    })


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


@deck_rec_bp.route("/admin/hide-deck/<deck_id>", methods=["POST"])
@require_admin
def admin_hide_deck(deck_id: str):
    """Hide a deck from the public listing. Admin only."""
    try:
        hidden_by = session.get("username") or str(session.get("user_id", "admin"))
        repo = DeckRecRepository()
        repo.hide_deck(deck_id, hidden_by)
        return jsonify({"ok": True})
    except Exception as e:
        logger.exception("Error in admin_hide_deck for %s: %s", deck_id, e)
        return jsonify({"error": "Failed to hide deck"}), 500


@deck_rec_bp.route("/admin/unhide-deck/<deck_id>", methods=["POST"])
@require_admin
def admin_unhide_deck(deck_id: str):
    """Unhide a previously hidden deck. Admin only."""
    try:
        repo = DeckRecRepository()
        repo.unhide_deck(deck_id)
        return jsonify({"ok": True})
    except Exception as e:
        logger.exception("Error in admin_unhide_deck for %s: %s", deck_id, e)
        return jsonify({"error": "Failed to unhide deck"}), 500
