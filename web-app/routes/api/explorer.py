"""Explorer Standings API routes."""

import csv
import io
import json
import logging
import re

from flask import Blueprint, Response, jsonify, request

from repositories.explorer import ExplorerRepository
from utils.auth import require_admin, require_explorer_admin

logger = logging.getLogger(__name__)

explorer_bp = Blueprint("explorer", __name__)

DEFAULT_POINTS_CONFIG = {
    "participation": 10,
    "bonus_pathfinder": {"0": 5, "1": 4, "2": 3},
    "persecutor": {"1": 10, "2": 5, "3": 4, "4": 4, "5": 3, "6": 3, "7": 2, "8": 2},
    "trials_threshold": 10,
}


# ── Seasons ───────────────────────────────────────────────────────────────────


@explorer_bp.route("/seasons")
def get_seasons():
    """List all Explorer seasons. Public."""
    try:
        repo = ExplorerRepository()
        seasons = repo.get_all_seasons()
        for s in seasons:
            if s.get("points_config"):
                try:
                    s["points_config"] = json.loads(s["points_config"])
                except (json.JSONDecodeError, TypeError):
                    s["points_config"] = DEFAULT_POINTS_CONFIG
            else:
                s["points_config"] = DEFAULT_POINTS_CONFIG
        return jsonify(seasons)
    except Exception as e:
        logger.error(f"Error fetching explorer seasons: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@explorer_bp.route("/seasons", methods=["POST"])
@require_explorer_admin
def create_season():
    """Create a new Explorer season."""
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Season name is required"}), 400

    description = (data.get("description") or "").strip() or None
    points_config = data.get("points_config") or DEFAULT_POINTS_CONFIG
    points_config_json = json.dumps(points_config)

    try:
        repo = ExplorerRepository()
        season = repo.create_season(name, description, points_config_json)
        if season.get("points_config"):
            season["points_config"] = json.loads(season["points_config"])
        return jsonify({"success": True, "season": season}), 201
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            return jsonify({"error": f"Season '{name}' already exists"}), 409
        logger.error(f"Error creating explorer season: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@explorer_bp.route("/seasons/<int:season_id>", methods=["DELETE"])
@require_explorer_admin
def delete_season(season_id):
    """Delete a season and all its events/results."""
    try:
        repo = ExplorerRepository()
        if not repo.get_season(season_id):
            return jsonify({"error": "Season not found"}), 404
        repo.delete_season(season_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error deleting explorer season: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@explorer_bp.route("/seasons/<int:season_id>/events")
def get_season_events(season_id):
    """List all events in a season. Public."""
    try:
        repo = ExplorerRepository()
        if not repo.get_season(season_id):
            return jsonify({"error": "Season not found"}), 404
        events = repo.get_events_for_season(season_id)
        return jsonify(events)
    except Exception as e:
        logger.error(f"Error fetching season events: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ── Events ────────────────────────────────────────────────────────────────────


@explorer_bp.route("/events/preview", methods=["POST"])
@require_explorer_admin
def preview_event():
    """Fetch event data from sorcerytcg.com and return a preview without saving."""
    data = request.get_json() or {}
    url = (data.get("url") or "").strip()
    season_id = data.get("season_id")

    if not url or not season_id:
        return jsonify({"error": "url and season_id are required"}), 400

    try:
        from services.explorer import ExplorerFetchError, ExplorerService
        repo = ExplorerRepository()

        service = ExplorerService()
        event_data = service.fetch_event_data(url)

        existing = repo.get_event_by_cardeio_id(event_data["event_id"])
        if existing:
            return jsonify({"error": "Event already imported"}), 409

        return jsonify(event_data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        if "ExplorerFetchError" in type(e).__name__:
            return jsonify({"error": f"Failed to fetch event from sorcerytcg.com: {e}"}), 502
        logger.error(f"Error previewing explorer event: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@explorer_bp.route("/events", methods=["POST"])
@require_explorer_admin
def save_event():
    """Import and save an event from a sorcerytcg.com URL."""
    data = request.get_json() or {}
    url = (data.get("url") or "").strip()
    season_id = data.get("season_id")

    if not url or not season_id:
        return jsonify({"error": "url and season_id are required"}), 400

    try:
        from services.explorer import ExplorerFetchError, ExplorerService
        repo = ExplorerRepository()

        service = ExplorerService()
        event_data = service.fetch_event_data(url)

        existing = repo.get_event_by_cardeio_id(event_data["event_id"])
        if existing:
            return jsonify({"error": "Event already imported"}), 409

        if not repo.get_season(season_id):
            return jsonify({"error": "Season not found"}), 404

        event = repo.create_event(
            season_id=season_id,
            event_external_id=event_data["event_id"],
            event_name=event_data["event_name"],
            event_date=event_data.get("event_date"),
            total_players=event_data.get("total_players"),
            play_format=event_data.get("play_format"),
            venue_name=event_data.get("venue_name"),
            source_url=url,
        )
        repo.save_results(event["id"], event_data["results"])
        _geocode_event_in_background(event["id"], event_data.get("venue_name"))

        return jsonify({
            "success": True,
            "event": {
                "id": event["id"],
                "event_name": event["event_name"],
                "total_players": event["total_players"],
            },
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        if "ExplorerFetchError" in type(e).__name__:
            return jsonify({"error": f"Failed to fetch event from sorcerytcg.com: {e}"}), 502
        logger.error(f"Error saving explorer event: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@explorer_bp.route("/events/<int:event_id>", methods=["DELETE"])
@require_explorer_admin
def delete_event(event_id):
    """Remove an event and all its results."""
    try:
        repo = ExplorerRepository()
        if not repo.get_event(event_id):
            return jsonify({"error": "Event not found"}), 404
        repo.delete_event(event_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error deleting explorer event: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ── Leaderboard ───────────────────────────────────────────────────────────────


@explorer_bp.route("/leaderboard/<int:season_id>")
def get_leaderboard(season_id):
    """Compute and return the three-track season leaderboard. Public."""
    try:
        from services.explorer import ExplorerService
        repo = ExplorerRepository()
        if not repo.get_season(season_id):
            return jsonify({"error": "Season not found"}), 404
        service = ExplorerService()
        return jsonify(service.compute_leaderboard(season_id))
    except Exception as e:
        logger.error(f"Error computing explorer leaderboard: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


STANDINGS_CSV_COLUMNS = [
    ("rank", "Rank"),
    ("display_name", "Player"),
    ("team_name", "Team"),
    ("grand_explorer", "Grand Explorer"),
    ("pathfinder_total", "Pathfinder"),
    ("persecutor_total", "Persecutor"),
    ("events_played", "Events"),
    ("qualified", "Qualified"),
    ("cardeio_user_id", "Player ID"),
]

RESULTS_CSV_COLUMNS = [
    ("event_name", "Event"),
    ("event_date", "Date"),
    ("venue_name", "Venue"),
    ("event_total_players", "Event Players"),
    ("display_name", "Player"),
    ("team_name", "Team"),
    ("final_standing", "Place"),
    ("wins", "Wins"),
    ("pathfinder", "Pathfinder"),
    ("persecutor", "Persecutor"),
    ("grand_explorer", "Grand Explorer"),
    ("rank", "Series Rank"),
    ("cardeio_user_id", "Player ID"),
    ("source_url", "Event Link"),
]


def _csv_safe(value):
    """Stop spreadsheet apps treating imported names as formulas."""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if value is None:
        return ""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _csv_response(columns, rows, filename):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([label for _, label in columns])
    for row in rows:
        writer.writerow([_csv_safe(row.get(key)) for key, _ in columns])
    # A BOM lets Excel open names with accents correctly.
    return Response(
        "\ufeff" + buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@explorer_bp.route("/leaderboard/<int:season_id>/export.csv")
@require_explorer_admin
def export_leaderboard_csv(season_id):
    """Download a series as CSV. Explorer admins only.

    ``?view=standings`` (default) gives one row per player as the leaderboard
    shows it; ``?view=results`` gives one row per player per event.
    """
    view = request.args.get("view", "standings")
    if view not in ("standings", "results"):
        return jsonify({"error": "view must be standings or results"}), 400

    from services.explorer import ExplorerService
    board = ExplorerService().compute_leaderboard(season_id)
    if board is None:
        return jsonify({"error": "Season not found"}), 404

    slug = re.sub(r"[^a-z0-9]+", "-", (board.get("season_name") or "series").lower()).strip("-")
    slug = slug or f"series-{season_id}"
    players = board["players"]

    if view == "standings":
        return _csv_response(STANDINGS_CSV_COLUMNS, players, f"{slug}-standings.csv")

    rows = []
    for player in players:
        for result in player["event_results"]:
            rows.append({**player, **result})
    rows.sort(key=lambda r: (r.get("event_date") or "", str(r.get("event_id") or ""),
                             r.get("final_standing") or 10**6))
    return _csv_response(RESULTS_CSV_COLUMNS, rows, f"{slug}-results.csv")


# ── Venue Attendance ──────────────────────────────────────────────────────


@explorer_bp.route("/venue-attendance", methods=["POST"])
@require_explorer_admin
def venue_attendance():
    """Fetch past event attendance for a venue/store. Explorer admin only."""
    data = request.get_json() or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400

    try:
        from services.explorer import ExplorerFetchError, ExplorerService
        service = ExplorerService()
        result = service.fetch_venue_attendance(url)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        if "ExplorerFetchError" in type(e).__name__:
            return jsonify({"error": f"Failed to fetch venue data: {e}"}), 502
        logger.error(f"Error fetching venue attendance: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ── Admins ────────────────────────────────────────────────────────────────────


@explorer_bp.route("/admins")
@require_admin
def get_admins():
    """List Explorer admins. Global admin only."""
    try:
        repo = ExplorerRepository()
        return jsonify(repo.get_explorer_admins())
    except Exception as e:
        logger.error(f"Error fetching explorer admins: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@explorer_bp.route("/admins", methods=["POST"])
@require_admin
def add_admin():
    """Add an Explorer admin. Global admin only."""
    data = request.get_json() or {}
    discord_user_id = (data.get("discord_user_id") or "").strip()
    display_name = (data.get("display_name") or "").strip() or None
    if not discord_user_id:
        return jsonify({"error": "discord_user_id is required"}), 400
    try:
        repo = ExplorerRepository()
        repo.add_explorer_admin(discord_user_id, display_name)
        return jsonify({"success": True}), 201
    except Exception as e:
        logger.error(f"Error adding explorer admin: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ── Player Aliases / Merge ────────────────────────────────────────────────


@explorer_bp.route("/players/duplicates")
@require_explorer_admin
def get_potential_duplicates():
    """Find players that may be duplicates (name match). Explorer admin only."""
    try:
        from services.explorer import ExplorerService
        service = ExplorerService()
        return jsonify(service.find_potential_duplicates())
    except Exception as e:
        logger.error(f"Error finding duplicates: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@explorer_bp.route("/players/aliases")
@require_explorer_admin
def get_aliases():
    """List all player aliases. Explorer admin only."""
    try:
        repo = ExplorerRepository()
        return jsonify(repo.get_all_aliases())
    except Exception as e:
        logger.error(f"Error fetching aliases: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@explorer_bp.route("/players/merge", methods=["POST"])
@require_explorer_admin
def merge_players():
    """Merge two player IDs (alias -> canonical). Explorer admin only."""
    data = request.get_json() or {}
    alias_user_id = (data.get("alias_user_id") or "").strip()
    canonical_user_id = (data.get("canonical_user_id") or "").strip()
    alias_display_name = (data.get("alias_display_name") or "").strip() or None
    canonical_display_name = (data.get("canonical_display_name") or "").strip() or None

    if not alias_user_id or not canonical_user_id:
        return jsonify({"error": "alias_user_id and canonical_user_id are required"}), 400
    if alias_user_id == canonical_user_id:
        return jsonify({"error": "Cannot alias a player to themselves"}), 400

    try:
        repo = ExplorerRepository()
        alias = repo.create_alias(
            alias_user_id, canonical_user_id,
            alias_display_name, canonical_display_name,
        )
        return jsonify({"success": True, "alias": alias}), 201
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            return jsonify({"error": "This player is already aliased"}), 409
        logger.error(f"Error merging players: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@explorer_bp.route("/players/aliases/<int:alias_id>", methods=["DELETE"])
@require_explorer_admin
def delete_alias(alias_id):
    """Remove a player alias. Explorer admin only."""
    try:
        repo = ExplorerRepository()
        removed = repo.delete_alias(alias_id)
        if not removed:
            return jsonify({"error": "Alias not found"}), 404
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error deleting alias: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@explorer_bp.route("/players")
@require_explorer_admin
def get_all_players():
    """List all unique players across all events. Explorer admin only."""
    try:
        repo = ExplorerRepository()
        return jsonify(repo.get_all_unique_players())
    except Exception as e:
        logger.error(f"Error fetching players: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@explorer_bp.route("/admins/<discord_user_id>", methods=["DELETE"])
@require_admin
def remove_admin(discord_user_id):
    """Remove an Explorer admin. Global admin only."""
    try:
        repo = ExplorerRepository()
        removed = repo.remove_explorer_admin(discord_user_id)
        if not removed:
            return jsonify({"error": "Admin not found"}), 404
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error removing explorer admin: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


def _geocode_event_in_background(event_id, venue_name):
    """Place a newly imported event on the map without holding up the import.

    Nominatim is rate limited and the app runs on a couple of sync workers, so
    this never runs inline. A venue we cannot place is simply absent from the
    map until an admin retries it.
    """
    import threading

    if not (venue_name or "").strip():
        return

    def run():
        try:
            from services.geocoding import geocode_location
            coords = geocode_location(venue_name, None, None)
            if coords:
                ExplorerRepository().set_event_coordinates(event_id, *coords)
        except Exception:
            logger.exception("Background geocoding failed for event %s", event_id)

    threading.Thread(target=run, daemon=True).start()


# ── Settings & events map ─────────────────────────────────────────────────────

EVENTS_MAP_SETTING = "events_map_enabled"

# Booleans live in a TEXT column, so normalise on the way in and out.
_TRUE = "1"
_FALSE = "0"


def _events_map_enabled(repo) -> bool:
    # Off until an admin turns it on, so the map never appears half-geocoded.
    return repo.get_setting(EVENTS_MAP_SETTING, _FALSE) == _TRUE


@explorer_bp.route("/settings")
def get_settings():
    """Public Explorer settings that the Community Series page reads."""
    try:
        repo = ExplorerRepository()
        return jsonify({"events_map_enabled": _events_map_enabled(repo)})
    except Exception as e:
        logger.error(f"Error reading explorer settings: {e}", exc_info=True)
        # A settings failure should never take the leaderboard down with it.
        return jsonify({"events_map_enabled": False})


@explorer_bp.route("/settings", methods=["POST"])
@require_explorer_admin
def update_settings():
    """Toggle the public events map. Explorer admin only."""
    data = request.get_json(silent=True) or {}
    if "events_map_enabled" not in data:
        return jsonify({"error": "events_map_enabled is required"}), 400

    repo = ExplorerRepository()
    repo.set_setting(
        EVENTS_MAP_SETTING, _TRUE if data["events_map_enabled"] else _FALSE
    )
    return jsonify({"events_map_enabled": _events_map_enabled(repo)})


@explorer_bp.route("/events-map")
def events_map():
    """Geocoded events for the Community Series map. Public.

    Returns an empty list when the map is switched off, so the page never
    shows events an admin has chosen to hide.
    """
    season_id = request.args.get("season_id", type=int)
    try:
        repo = ExplorerRepository()
        if not _events_map_enabled(repo):
            return jsonify({"enabled": False, "events": []})
        return jsonify({
            "enabled": True,
            "events": repo.get_events_with_coordinates(season_id),
        })
    except Exception as e:
        logger.error(f"Error building events map: {e}", exc_info=True)
        return jsonify({"enabled": False, "events": []})


@explorer_bp.route("/events/unmapped")
@require_explorer_admin
def unmapped_events():
    """Events with no coordinates yet. Explorer admin only."""
    repo = ExplorerRepository()
    return jsonify({"events": repo.get_events_missing_coordinates()})


@explorer_bp.route("/events/<int:event_id>/geocode", methods=["POST"])
@require_explorer_admin
def geocode_event(event_id):
    """Place one event on the map from its venue name. Explorer admin only."""
    from services.geocoding import geocode_location

    repo = ExplorerRepository()
    event = repo.get_event(event_id)
    if not event:
        return jsonify({"error": "Event not found"}), 404

    venue = (event.get("venue_name") or "").strip()
    if not venue:
        return jsonify({"error": "This event has no venue name to look up"}), 400

    coords = geocode_location(venue, None, None)
    if not coords:
        return jsonify({"error": f"Could not find '{venue}' on the map"}), 404

    repo.set_event_coordinates(event_id, *coords)
    return jsonify({"success": True, "latitude": coords[0], "longitude": coords[1]})


# ── Site content (the Explorer Series mini-site's editable text) ─────────────

SITE_CONTENT_SETTING = "site_content"

# Shown until an Explorer admin saves their own wording.
DEFAULT_SITE_CONTENT = {
    "announcement": "",
    "kicker": "",
    "title": "The Explorer Series",
    "intro": (
        "A player-run annual circuit for Sorcery TCG. The Series promotes a diverse "
        "range of local events, rewards players who travel to play the game, and "
        "builds relationships across our communities."
    ),
    "discord_url": "",
    "member_url": "",
    "show_points_guide": True,
    "host_title": "Bring the Series to your store",
    "host_text": (
        "Each Explorer Series event is run by a local tournament organizer with "
        "their community of Sorcery players."
    ),
    "sections": [],
}

_TEXT_LIMITS = {
    "announcement": 500, "kicker": 80, "title": 120, "intro": 1500,
    "host_title": 120, "host_text": 1000,
}
_URL_FIELDS = ("discord_url", "member_url")
MAX_SECTIONS = 20
MAX_SECTION_TITLE = 120
MAX_SECTION_BODY = 10000


def _clean_url(value) -> str:
    url = str(value or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://[^\s<>\"']+$", url, re.IGNORECASE) or len(url) > 500:
        raise ValueError("Links must start with http:// or https://")
    return url


def _clean_site_content(data: dict) -> dict:
    """Validate an admin's edit. Unknown keys are dropped."""
    out = dict(DEFAULT_SITE_CONTENT)
    for key, limit in _TEXT_LIMITS.items():
        if key in data:
            text = str(data.get(key) or "").strip()
            if len(text) > limit:
                raise ValueError(f"{key} is too long (max {limit} characters)")
            out[key] = text
    for key in _URL_FIELDS:
        if key in data:
            out[key] = _clean_url(data.get(key))
    if "show_points_guide" in data:
        out["show_points_guide"] = bool(data.get("show_points_guide"))
    if "sections" in data:
        sections = data.get("sections") or []
        if not isinstance(sections, list):
            raise ValueError("sections must be a list")
        if len(sections) > MAX_SECTIONS:
            raise ValueError(f"At most {MAX_SECTIONS} sections")
        cleaned = []
        for s in sections:
            if not isinstance(s, dict):
                raise ValueError("Each section needs a title and text")
            title = str(s.get("title") or "").strip()
            body = str(s.get("body") or "").strip()
            if not title and not body:
                continue
            if len(title) > MAX_SECTION_TITLE:
                raise ValueError(f"Section titles max {MAX_SECTION_TITLE} characters")
            if len(body) > MAX_SECTION_BODY:
                raise ValueError(f"Section text max {MAX_SECTION_BODY} characters")
            cleaned.append({"title": title, "body": body, "hidden": bool(s.get("hidden"))})
        out["sections"] = cleaned
    return out


def _load_site_content(repo) -> dict:
    raw = repo.get_setting(SITE_CONTENT_SETTING)
    content = dict(DEFAULT_SITE_CONTENT)
    if raw:
        try:
            saved = json.loads(raw)
            if isinstance(saved, dict):
                content.update({k: v for k, v in saved.items() if k in DEFAULT_SITE_CONTENT})
        except (json.JSONDecodeError, TypeError):
            logger.warning("Explorer site content is not valid JSON; using defaults")
    return content


@explorer_bp.route("/site-content")
def get_site_content():
    """The Explorer Series site's editable text. Public."""
    try:
        return jsonify(_load_site_content(ExplorerRepository()))
    except Exception as e:
        logger.error(f"Error reading explorer site content: {e}", exc_info=True)
        return jsonify(DEFAULT_SITE_CONTENT)


@explorer_bp.route("/site-content", methods=["POST"])
@require_explorer_admin
def update_site_content():
    """Save the Explorer Series site's text. Explorer admin only."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Send the content as JSON"}), 400
    try:
        content = _clean_site_content(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    repo = ExplorerRepository()
    repo.set_setting(SITE_CONTENT_SETTING, json.dumps(content))
    return jsonify(_load_site_content(repo))
