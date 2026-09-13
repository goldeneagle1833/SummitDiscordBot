"""API routes for event deck management."""

import json
import logging
import os
import tempfile
import threading
import uuid

from flask import Blueprint, jsonify, request

from repositories.events import EventRepository
from utils.auth import is_admin, require_admin
from utils.formatting import format_event_name

# File-based job store for background Curiosa fetching.
# Using files instead of an in-memory dict so that jobs are visible
# across multiple Gunicorn worker processes.
_JOBS_DIR = os.path.join(tempfile.gettempdir(), "summit_event_jobs")
os.makedirs(_JOBS_DIR, exist_ok=True)


def _job_path(job_id):
    """Return the filesystem path for a job's status file."""
    # Sanitise to prevent path traversal
    safe_id = job_id.replace(os.sep, "").replace("/", "").replace("..", "")
    return os.path.join(_JOBS_DIR, f"{safe_id}.json")


def _write_job(job_id, data):
    """Atomically write job status to disk."""
    path = _job_path(job_id)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def _read_job(job_id):
    """Read job status from disk, or return None."""
    path = _job_path(job_id)
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _delete_job(job_id):
    """Remove a job status file."""
    try:
        os.remove(_job_path(job_id))
    except FileNotFoundError:
        pass

logger = logging.getLogger(__name__)

events_bp = Blueprint("events", __name__)


@events_bp.route("/top-8-events")
def list_top8_events():
    """Return all top-8 event folders with metadata."""
    try:
        repo = EventRepository()
        events = repo.get_all_events()
        featured = repo.get_featured_event()
        return jsonify({"events": events, "is_admin": is_admin(), "featured_event": featured})
    except Exception as e:
        logger.exception("Error listing events: %s", e)
        return jsonify({"error": "Failed to load events"}), 500


@events_bp.route("/events/<event_folder>")
def get_event_detail(event_folder: str):
    """Return deck tables, card stats, and element charts for a single event."""
    try:
        repo = EventRepository()
        decks = repo.get_event_decks(event_folder)
        if decks is None:
            return jsonify({"error": "Event not found"}), 404

        stats = repo.get_event_stats(event_folder)
        element_stats = repo.get_event_element_stats(event_folder)
        element_stats_by_group = repo.get_event_element_stats_by_group(event_folder)
        description = repo.get_event_description(event_folder)

        return jsonify({
            "event_name": format_event_name(event_folder),
            "event_folder": event_folder,
            "description": description,
            "top8_decks": decks["top8_decks"],
            "all_decks": decks["all_decks"],
            "card_data": stats["card_data"] if stats else [],
            "top8_card_data": stats["top8_card_data"] if stats else [],
            "element_stats": element_stats,
            "element_stats_by_group": element_stats_by_group,
            "is_admin": is_admin(),
        })
    except Exception as e:
        logger.exception("Error loading event %s: %s", event_folder, e)
        return jsonify({"error": "Failed to load event data"}), 500


@events_bp.route("/events/compare")
def compare_events():
    """Return comparison data for multiple events."""
    folders_param = request.args.get("folders", "")
    folders = [f.strip() for f in folders_param.split(",") if f.strip()]
    top8_only = request.args.get("top8_only", "").lower() in ("1", "true", "yes")

    if len(folders) < 2:
        return jsonify({"error": "At least 2 event folders required"}), 400
    if len(folders) > 10:
        return jsonify({"error": "Maximum 10 events for comparison"}), 400

    try:
        repo = EventRepository()
        results = []
        for folder in folders:
            decks = repo.get_event_decks(folder)
            if decks is None:
                continue

            # Choose raw decks based on top8_only flag
            if top8_only:
                files = repo._find_json_files(folder)
                raw_decks = []
                if files and files["top8"] and files["top8"].exists():
                    try:
                        with open(files["top8"], "r", encoding="utf-8") as f:
                            raw_decks = json.load(f)[:8]
                    except Exception:
                        pass
                if not raw_decks:
                    # Fallback: use all decks if no top8 file
                    raw_decks = repo._load_all_decks(folder) or []
            else:
                raw_decks = repo._load_all_decks(folder) or []

            element_stats = repo._compute_element_stats(raw_decks)

            # Count avatars
            avatar_counts = {}
            for deck in raw_decks:
                av_list = deck.get("avatar", [])
                av_name = av_list[0].get("name", "Unknown") if av_list else "Unknown"
                avatar_counts[av_name] = avatar_counts.get(av_name, 0) + 1

            # Count rarity distribution
            rarity_counts = {}
            for deck in raw_decks:
                for card in deck.get("spellbook", []):
                    rarity = card.get("rarity", "Unknown")
                    qty = card.get("quantity", 1)
                    rarity_counts[rarity] = rarity_counts.get(rarity, 0) + qty

            # Mono vs multi-element breakdown
            elements_order = ["Fire", "Water", "Earth", "Air"]
            mono_count = 0
            multi_count = 0
            element_combo_counts = {}
            for deck in raw_decks:
                el_qty = {e: 0 for e in elements_order}
                for card in deck.get("spellbook", []):
                    for el in card.get("elements", "None").split(", "):
                        el = el.strip()
                        if el in el_qty:
                            el_qty[el] += card.get("quantity", 1)
                present = sorted([e for e in elements_order if el_qty[e] > 0])
                if len(present) <= 1:
                    mono_count += 1
                else:
                    multi_count += 1
                combo_key = "/".join(present) if present else "None"
                element_combo_counts[combo_key] = element_combo_counts.get(combo_key, 0) + 1

            # Full card stats (type, element, rarity, count, avg, % decks)
            card_stats = repo._compute_card_stats(raw_decks)

            # Also build card_deck_presence for overlap computation
            total_decks = len(raw_decks)
            card_deck_presence = {}
            for deck in raw_decks:
                seen_cards = set()
                for card in deck.get("spellbook", []):
                    name = card.get("name", "Unknown")
                    if name not in seen_cards:
                        card_deck_presence[name] = card_deck_presence.get(name, 0) + 1
                        seen_cards.add(name)

            # Keep top_cards for backwards compat (subset of card_stats)
            top_cards = sorted(
                [
                    {"name": c["name"], "total_copies": c["count"], "deck_percent": float(c["deck_percent"])}
                    for c in card_stats
                ],
                key=lambda x: x["deck_percent"],
                reverse=True,
            )[:20]

            # Winner's Meta: top 8 finishers from the top8 file
            winners = []
            files = repo._find_json_files(folder)
            if files and files["top8"] and files["top8"].exists():
                try:
                    with open(files["top8"], "r", encoding="utf-8") as f:
                        top8_raw = json.load(f)[:8]
                    for i, deck in enumerate(top8_raw):
                        av_list = deck.get("avatar", [])
                        av_name = av_list[0].get("name", "Unknown") if av_list else "Unknown"
                        deck_elements = []
                        el_qty = {e: 0 for e in elements_order}
                        for card in deck.get("spellbook", []):
                            for el in card.get("elements", "None").split(", "):
                                el = el.strip()
                                if el in el_qty:
                                    el_qty[el] += card.get("quantity", 1)
                        deck_elements = sorted([e for e in elements_order if el_qty[e] > 0],
                                               key=lambda e: el_qty[e], reverse=True)
                        winners.append({
                            "place": i + 1,
                            "avatar": av_name,
                            "elements": deck_elements,
                            "player": deck.get("username", "Unknown"),
                        })
                except Exception:
                    pass

            # Top 8 Conversion Rate: avatar/element counts for top8 vs all
            top8_avatar_counts = {}
            top8_element_counts = {e: 0 for e in elements_order}
            all_element_counts = {e: 0 for e in elements_order}
            if files and files["top8"] and files["top8"].exists():
                try:
                    with open(files["top8"], "r", encoding="utf-8") as f:
                        t8_raw = json.load(f)[:8]
                    for deck in t8_raw:
                        av_list = deck.get("avatar", [])
                        av_name = av_list[0].get("name", "Unknown") if av_list else "Unknown"
                        top8_avatar_counts[av_name] = top8_avatar_counts.get(av_name, 0) + 1
                        el_qty = {e: 0 for e in elements_order}
                        for card in deck.get("spellbook", []):
                            for el in card.get("elements", "None").split(", "):
                                el = el.strip()
                                if el in el_qty:
                                    el_qty[el] += card.get("quantity", 1)
                        dominant = max(elements_order, key=lambda e: el_qty[e]) if any(el_qty[e] > 0 for e in elements_order) else None
                        if dominant:
                            top8_element_counts[dominant] = top8_element_counts.get(dominant, 0) + 1
                except Exception:
                    pass

            # Dominant element counts for all decks
            all_decks_for_elements = repo._load_all_decks(folder) or []
            for deck in all_decks_for_elements:
                el_qty = {e: 0 for e in elements_order}
                for card in deck.get("spellbook", []):
                    for el in card.get("elements", "None").split(", "):
                        el = el.strip()
                        if el in el_qty:
                            el_qty[el] += card.get("quantity", 1)
                dominant = max(elements_order, key=lambda e: el_qty[e]) if any(el_qty[e] > 0 for e in elements_order) else None
                if dominant:
                    all_element_counts[dominant] = all_element_counts.get(dominant, 0) + 1

            # All-decks avatar counts (for conversion rate)
            all_avatar_counts = {}
            for deck in all_decks_for_elements:
                av_list = deck.get("avatar", [])
                av_name = av_list[0].get("name", "Unknown") if av_list else "Unknown"
                all_avatar_counts[av_name] = all_avatar_counts.get(av_name, 0) + 1

            # Card set for overlap computation (top card names)
            card_set = set(card_deck_presence.keys())

            results.append({
                "folder": folder,
                "name": format_event_name(folder),
                "total_decks": len(decks["all_decks"]),
                "top8_count": len(decks["top8_decks"]),
                "deck_count_used": total_decks,
                "element_stats": element_stats,
                "avatar_counts": dict(sorted(avatar_counts.items(), key=lambda x: x[1], reverse=True)),
                "unique_avatars": len(avatar_counts),
                "rarity_counts": rarity_counts,
                "mono_count": mono_count,
                "multi_count": multi_count,
                "element_combos": dict(sorted(element_combo_counts.items(), key=lambda x: x[1], reverse=True)),
                "top_cards": top_cards,
                "card_stats": card_stats,
                "winners": winners,
                "top8_avatar_counts": top8_avatar_counts,
                "all_avatar_counts": all_avatar_counts,
                "top8_element_counts": top8_element_counts,
                "all_element_counts": all_element_counts,
                "_card_set": card_set,  # internal, stripped before response
            })

        if len(results) < 2:
            return jsonify({"error": "Could not load enough events for comparison"}), 404

        # Load metadata overrides for display names
        meta = repo._load_metadata_overrides()
        for r in results:
            override = meta.get(r["folder"], {})
            if override.get("name"):
                r["name"] = override["name"]

        # Compute card overlap (Jaccard similarity) between events
        card_overlap = []
        for i, a in enumerate(results):
            for j, b in enumerate(results):
                if j <= i:
                    continue
                set_a = a.get("_card_set", set())
                set_b = b.get("_card_set", set())
                union = len(set_a | set_b)
                intersection = len(set_a & set_b)
                jaccard = round(intersection / union * 100, 1) if union else 0
                card_overlap.append({
                    "event_a": a["folder"],
                    "event_b": b["folder"],
                    "name_a": a["name"],
                    "name_b": b["name"],
                    "shared_cards": intersection,
                    "total_unique": union,
                    "jaccard": jaccard,
                })

        # Strip internal fields
        for r in results:
            r.pop("_card_set", None)

        return jsonify({"events": results, "card_overlap": card_overlap})
    except Exception as e:
        logger.exception("Error comparing events: %s", e)
        return jsonify({"error": "Failed to compare events"}), 500


@events_bp.route("/events/<event_folder>/metadata", methods=["PUT"])
@require_admin
def update_event_metadata(event_folder):
    """Update display name and/or star rating for an event (admin only)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    name = data.get("name")
    rating = data.get("rating")
    description = data.get("description")
    event_date = data.get("event_date")

    if name is not None and (not isinstance(name, str) or not name.strip()):
        return jsonify({"success": False, "error": "Name must be a non-empty string"}), 400

    if rating is not None:
        if not isinstance(rating, int) or rating < 1 or rating > 3:
            return jsonify({"success": False, "error": "Rating must be 1, 2, or 3"}), 400

    if description is not None and not isinstance(description, str):
        return jsonify({"success": False, "error": "Description must be a string"}), 400

    repo = EventRepository()
    result = repo.update_event_metadata(
        event_folder,
        name=name.strip() if name else None,
        rating=rating,
        description=description.strip() if description else description,
        event_date=event_date.strip() if isinstance(event_date, str) else event_date,
    )

    status = 200 if result.get("success") else 400
    return jsonify(result), status


@events_bp.route("/events/<event_folder>/reorder", methods=["POST"])
@require_admin
def reorder_event_decks(event_folder):
    """Reorder decks in an event's JSON file (admin only)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    table_type = data.get("table")
    if table_type not in ("top8", "all"):
        return jsonify({"success": False, "error": "table must be 'top8' or 'all'"}), 400

    new_order = data.get("order")
    if not isinstance(new_order, list) or not all(isinstance(i, int) for i in new_order):
        return jsonify({"success": False, "error": "order must be a list of integers"}), 400

    repo = EventRepository()
    result = repo.reorder_event_decks(event_folder, table_type, new_order)

    status = 200 if result.get("success") else 400
    return jsonify(result), status


def _run_event_creation(job_id, title, valid_ranked, valid_bulk):
    """Background worker for event creation — fetches from Curiosa and saves."""
    try:
        from services.curiosa import CuriosaService
        curiosa = CuriosaService()

        errors = []
        top8_decks = []
        bulk_decks = []

        total_batches = 0
        if valid_ranked:
            total_batches += max(1, -(-len(valid_ranked) // 10))
        if valid_bulk:
            total_batches += max(1, -(-len(valid_bulk) // 10))

        completed_batches = [0]

        # Monkey-patch the rate_limit to update progress
        original_rate_limit = curiosa._rate_limit
        def _tracking_rate_limit():
            original_rate_limit()
            completed_batches[0] += 1
            _write_job(job_id, {"status": "processing", "progress": f"Fetching batch {completed_batches[0]}/{total_batches}"})
        curiosa._rate_limit = _tracking_rate_limit

        if valid_ranked:
            top8_decks, ranked_errors = curiosa.fetch_decks_batch(valid_ranked)
            errors.extend(ranked_errors)

        if valid_bulk:
            bulk_decks, bulk_errors = curiosa.fetch_decks_batch(valid_bulk)
            errors.extend(bulk_errors)

        if not top8_decks and not bulk_decks:
            _write_job(job_id, {
                "status": "failed",
                "result": {
                    "success": False,
                    "error": "No decks could be fetched. Check your URLs.",
                    "fetch_errors": errors,
                },
            })
            return

        repo = EventRepository()
        result = repo.create_event(title, top8_decks, bulk_decks if bulk_decks else None)

        if result.get("success"):
            result["top8_added"] = len(top8_decks)
            result["bulk_added"] = len(bulk_decks)
            if errors:
                result["warnings"] = errors

        _write_job(job_id, {
            "status": "completed" if result.get("success") else "failed",
            "result": result,
        })

    except Exception as e:
        logger.exception("Background event creation failed: %s", e)
        _write_job(job_id, {
            "status": "failed",
            "result": {"success": False, "error": f"Internal error: {e}"},
        })


@events_bp.route("/events/create", methods=["POST"])
@require_admin
def create_event():
    """Create a new event from Curiosa deck URLs (admin only).

    Returns a job_id immediately; the client polls /events/jobs/<job_id>.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    title = data.get("title", "").strip()
    if not title:
        return jsonify({"success": False, "error": "Title is required"}), 400

    ranked_urls = data.get("ranked_urls", [])
    if not isinstance(ranked_urls, list):
        return jsonify({"success": False, "error": "ranked_urls must be a list"}), 400

    bulk_urls = data.get("bulk_urls", [])
    if not isinstance(bulk_urls, list):
        return jsonify({"success": False, "error": "bulk_urls must be a list"}), 400

    valid_ranked = [u.strip() for u in ranked_urls if u and isinstance(u, str) and u.strip()]
    valid_bulk = [u.strip() for u in bulk_urls if u and isinstance(u, str) and u.strip()]

    if not valid_ranked and not valid_bulk:
        return jsonify({"success": False, "error": "At least one deck URL is required"}), 400

    job_id = str(uuid.uuid4())
    _write_job(job_id, {"status": "processing", "progress": "Starting..."})

    thread = threading.Thread(
        target=_run_event_creation,
        args=(job_id, title, valid_ranked, valid_bulk),
        daemon=True,
    )
    thread.start()

    return jsonify({"success": True, "job_id": job_id}), 202


@events_bp.route("/events/jobs/<job_id>")
@require_admin
def get_event_job_status(job_id):
    """Poll for background event job status."""
    job = _read_job(job_id)

    if not job:
        return jsonify({"error": "Job not found"}), 404

    response = {"status": job["status"]}
    if "progress" in job:
        response["progress"] = job["progress"]
    if "result" in job:
        response["result"] = job["result"]
        # Clean up completed/failed jobs after they're read
        _delete_job(job_id)

    return jsonify(response)


def _run_event_deck_update(job_id, event_folder, table_type, urls, mode):
    """Background worker for updating event decks."""
    try:
        from services.curiosa import CuriosaService
        curiosa = CuriosaService()

        decks, errors = curiosa.fetch_decks_batch(urls)

        if not decks:
            _write_job(job_id, {
                "status": "failed",
                "result": {
                    "success": False,
                    "error": "No decks could be fetched. Check your URLs.",
                    "fetch_errors": errors,
                },
            })
            return

        repo = EventRepository()
        result = repo.update_event_decks(event_folder, table_type, decks, mode)

        if result.get("success"):
            result["decks_added"] = len(decks)
            if errors:
                result["warnings"] = errors

        _write_job(job_id, {
            "status": "completed" if result.get("success") else "failed",
            "result": result,
        })

    except Exception as e:
        logger.exception("Background deck update failed: %s", e)
        _write_job(job_id, {
            "status": "failed",
            "result": {"success": False, "error": f"Internal error: {e}"},
        })


@events_bp.route("/events/<event_folder>/decks", methods=["POST"])
@require_admin
def update_event_decks(event_folder):
    """Add or replace decks in an existing event via Curiosa URLs (admin only)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    table_type = data.get("table")
    if table_type not in ("top8", "all"):
        return jsonify({"success": False, "error": "table must be 'top8' or 'all'"}), 400

    mode = data.get("mode", "replace")
    if mode not in ("replace", "append"):
        return jsonify({"success": False, "error": "mode must be 'replace' or 'append'"}), 400

    urls = data.get("urls", [])
    if not isinstance(urls, list):
        return jsonify({"success": False, "error": "urls must be a list"}), 400

    job_id = str(uuid.uuid4())
    _write_job(job_id, {"status": "processing", "progress": "Starting..."})

    thread = threading.Thread(
        target=_run_event_deck_update,
        args=(job_id, event_folder, table_type, urls, mode),
        daemon=True,
    )
    thread.start()

    return jsonify({"success": True, "job_id": job_id}), 202


@events_bp.route("/events/<event_folder>", methods=["DELETE"])
@require_admin
def delete_event(event_folder):
    """Delete an event and all its data (admin only)."""
    repo = EventRepository()
    result = repo.delete_event(event_folder)

    status = 200 if result.get("success") else 400
    return jsonify(result), status


def _run_event_refresh(job_id, event_folder):
    """Background worker for refreshing event decks."""
    try:
        from services.curiosa import CuriosaService
        curiosa = CuriosaService()

        repo = EventRepository()
        result = repo.refresh_event_decks(event_folder, curiosa)

        _write_job(job_id, {
            "status": "completed" if result.get("success") else "failed",
            "result": result,
        })

    except Exception as e:
        logger.exception("Background event refresh failed: %s", e)
        _write_job(job_id, {
            "status": "failed",
            "result": {"success": False, "error": f"Internal error: {e}"},
        })


@events_bp.route("/events/<event_folder>/refresh", methods=["POST"])
@require_admin
def refresh_event(event_folder):
    """Re-fetch all deck data from Curiosa for an event (admin only)."""
    job_id = str(uuid.uuid4())
    _write_job(job_id, {"status": "processing", "progress": "Refreshing decks..."})

    thread = threading.Thread(
        target=_run_event_refresh,
        args=(job_id, event_folder),
        daemon=True,
    )
    thread.start()

    return jsonify({"success": True, "job_id": job_id}), 202


def _run_event_import(job_id, title, event_url):
    """Background worker for importing an event from a sorcerytcg.com URL."""
    try:
        from services.curiosa import CuriosaService
        curiosa = CuriosaService()

        def on_progress(msg):
            _write_job(job_id, {"status": "processing", "progress": msg})

        # Step 1: Discover deck IDs from event snapshots
        discovery = curiosa.fetch_event_deck_ids(event_url, on_progress=on_progress)
        errors = list(discovery.get("errors", []))

        if not discovery["players"]:
            _write_job(job_id, {
                "status": "failed",
                "result": {
                    "success": False,
                    "error": "No decks could be discovered from this event.",
                    "fetch_errors": errors,
                },
            })
            return

        # Use event name as title if not provided
        if not title:
            title = discovery["event_name"] or "Imported Event"

        players = discovery["players"]  # already sorted by standing
        deck_ids = [p["deck_id"] for p in players]
        top_cut = discovery.get("top_cut_size", 8)
        on_progress(f"Found {len(deck_ids)} decks, fetching deck data...")

        # Step 2: Fetch full deck data using discovered IDs
        total = len(deck_ids)
        completed = [0]
        original_rate_limit = curiosa._rate_limit
        def _tracking_rate_limit():
            original_rate_limit()
            completed[0] += 1
            _write_job(job_id, {
                "status": "processing",
                "progress": f"Fetching deck {completed[0]}/{total}...",
            })
        curiosa._rate_limit = _tracking_rate_limit

        decks, failed_ids = curiosa.fetch_decks_by_ids(deck_ids)
        if failed_ids:
            errors.extend([f"Failed to fetch deck: {did}" for did in failed_ids])

        if not decks:
            _write_job(job_id, {
                "status": "failed",
                "result": {
                    "success": False,
                    "error": "No decks could be fetched. They may be private.",
                    "fetch_errors": errors,
                },
            })
            return

        # Step 3: Re-sort fetched decks by standing order
        # Build deck_id -> standing index from the discovery order
        deck_id_order = {p["deck_id"]: idx for idx, p in enumerate(players)}
        decks.sort(key=lambda d: deck_id_order.get(d.get("id", ""), 9999))

        # Split into top cut and bulk
        top8_decks = decks[:top_cut]
        bulk_decks = decks[top_cut:] if len(decks) > top_cut else None

        on_progress("Creating event...")
        repo = EventRepository()
        result = repo.create_event(title, top8_decks, bulk_decks)

        if result.get("success"):
            result["top8_added"] = len(top8_decks)
            result["bulk_added"] = len(bulk_decks) if bulk_decks else 0
            result["event_name"] = discovery["event_name"]
            if discovery["event_date"]:
                # Auto-set the event date from sorcerytcg.com
                repo.update_event_metadata(
                    title, event_date=discovery["event_date"]
                )
                result["event_date"] = discovery["event_date"]
            if errors:
                result["warnings"] = errors

        _write_job(job_id, {
            "status": "completed" if result.get("success") else "failed",
            "result": result,
        })

    except Exception as e:
        logger.exception("Background event import failed: %s", e)
        _write_job(job_id, {
            "status": "failed",
            "result": {"success": False, "error": f"Internal error: {e}"},
        })


@events_bp.route("/events/import-from-url", methods=["POST"])
@require_admin
def import_event_from_url():
    """Import an event by discovering decks from a sorcerytcg.com event URL.

    Returns a job_id immediately; the client polls /events/jobs/<job_id>.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    event_url = data.get("event_url", "").strip()
    if not event_url:
        return jsonify({"success": False, "error": "event_url is required"}), 400

    from services.curiosa import CuriosaService
    if not CuriosaService.get_event_id_from_url(event_url):
        return jsonify({
            "success": False,
            "error": "Invalid URL. Must be a sorcerytcg.com event URL.",
        }), 400

    title = data.get("title", "").strip()

    job_id = str(uuid.uuid4())
    _write_job(job_id, {"status": "processing", "progress": "Starting import..."})

    thread = threading.Thread(
        target=_run_event_import,
        args=(job_id, title, event_url),
        daemon=True,
    )
    thread.start()

    return jsonify({"success": True, "job_id": job_id}), 202


@events_bp.route("/events/featured", methods=["PUT"])
@require_admin
def set_featured_event():
    """Set or clear the featured (latest) event on the top 8 page (admin only)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    folder = data.get("folder")  # None to clear
    if folder is not None and (not isinstance(folder, str) or not folder.strip()):
        return jsonify({"success": False, "error": "folder must be a non-empty string or null"}), 400

    repo = EventRepository()
    result = repo.set_featured_event(folder.strip() if folder else None)

    status = 200 if result.get("success") else 400
    return jsonify(result), status


@events_bp.route("/events/reorder", methods=["POST"])
@require_admin
def reorder_events_list():
    """Reorder the events listing page (admin only)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    folder_order = data.get("order")
    if not isinstance(folder_order, list) or not all(isinstance(f, str) for f in folder_order):
        return jsonify({"success": False, "error": "order must be a list of folder name strings"}), 400

    repo = EventRepository()
    result = repo.save_event_order(folder_order)

    status = 200 if result.get("success") else 400
    return jsonify(result), status
