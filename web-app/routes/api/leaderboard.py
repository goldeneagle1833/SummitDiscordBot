"""Leaderboard API routes."""

import logging
import sqlite3
from collections import Counter
from flask import Blueprint, jsonify

from services.leaderboard import LeaderboardService
from webapp_config import SEASON_FILTERS, MATCH_RECORDS_DB_PATH

logger = logging.getLogger(__name__)

leaderboard_bp = Blueprint("leaderboard", __name__)


@leaderboard_bp.route("/leaderboard")
def get_leaderboard():
    """Get lifetime ELO leaderboard with win/loss records (admin only)."""
    from utils.auth import is_admin

    if not is_admin():
        return jsonify({"error": "Lifetime leaderboard is only available to admins."}), 403
    try:
        service = LeaderboardService()
        leaderboard_data = service.get_leaderboard()
        return jsonify(leaderboard_data)
    except Exception as e:
        logger.error(f"Error fetching leaderboard: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@leaderboard_bp.route("/leaderboard/event")
def get_event_leaderboard():
    """Get current event ELO leaderboard."""
    try:
        service = LeaderboardService()
        event_data = service.get_event_leaderboard()
        return jsonify(event_data)
    except Exception as e:
        logger.error(f"Error fetching event leaderboard: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@leaderboard_bp.route("/leaderboard/combined")
def get_combined_leaderboard():
    """Get both lifetime and event leaderboards. Lifetime data only included for admins."""
    from utils.auth import is_admin

    try:
        service = LeaderboardService()
        combined_data = service.get_combined_leaderboard()
        if not is_admin():
            combined_data.pop("lifetime", None)
        return jsonify(combined_data)
    except Exception as e:
        logger.error(f"Error fetching combined leaderboard: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@leaderboard_bp.route("/leaderboard/paper")
def get_paper_leaderboard():
    """Get paper ELO leaderboard (web-reported matches only)."""
    try:
        service = LeaderboardService()
        leaderboard_data = service.get_paper_leaderboard()
        return jsonify(leaderboard_data)
    except Exception as e:
        logger.error(f"Error fetching paper leaderboard: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@leaderboard_bp.route("/leaderboard/paper-event")
def get_paper_event_leaderboard():
    """Get paper event ELO leaderboard (web-reported matches only)."""
    try:
        service = LeaderboardService()
        event_data = service.get_paper_event_leaderboard()
        return jsonify(event_data)
    except Exception as e:
        logger.error(f"Error fetching paper event leaderboard: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@leaderboard_bp.route("/leaderboard/limited")
def get_limited_leaderboard():
    """Get limited format ELO leaderboard. Requires pilot or admin."""
    from utils.auth import is_admin
    from services.pilots import is_pilot_active

    if not is_admin() and not is_pilot_active("limited_leaderboard"):
        return jsonify({"error": "Limited leaderboard is not currently available."}), 403
    try:
        service = LeaderboardService()
        leaderboard_data = service.get_limited_leaderboard()
        return jsonify(leaderboard_data)
    except Exception as e:
        logger.error(f"Error fetching limited leaderboard: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@leaderboard_bp.route("/elo-distribution")
def get_elo_distribution():
    """Get ELO distribution across bands (public, based on lifetime ELO)."""
    try:
        service = LeaderboardService()
        distribution = service.get_elo_distribution()
        return jsonify(distribution)
    except Exception as e:
        logger.error(f"Error fetching ELO distribution: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@leaderboard_bp.route("/leaderboard/sources")
def get_leaderboard_sources():
    """Get all available match sources (Discord, external platforms, etc.)."""
    try:
        from repositories.matches import MatchRepository

        repo = MatchRepository()
        sources = repo.get_distinct_sources()
        return jsonify(sources)
    except Exception as e:
        logger.error(f"Error fetching leaderboard sources: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@leaderboard_bp.route("/leaderboard/source/<source>")
def get_source_leaderboard(source):
    """Get ELO leaderboard for a specific external source."""
    try:
        service = LeaderboardService()
        leaderboard_data = service.get_source_leaderboard(source)
        return jsonify(leaderboard_data)
    except Exception as e:
        logger.error(f"Error fetching source leaderboard: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@leaderboard_bp.route("/events")
def get_events():
    """Get all events for ELO filtering."""
    try:
        from repositories.elo import EloRepository

        repo = EloRepository()
        events = repo.get_all_events()
        active_event = repo.get_active_event()

        # Append season date-range filters at the end
        for sf in SEASON_FILTERS:
            events.append({
                "event_id": sf["id"],
                "event_name": sf["name"],
                "start_date": sf["start_date"],
                "end_date": sf["end_date"],
                "is_active": False,
            })

        return jsonify(
            {
                "events": events,
                "active_event": active_event,
            }
        )
    except Exception as e:
        logger.error(f"Error fetching events: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@leaderboard_bp.route("/player/<player_id>/event/<int:event_id>")
def get_player_event_stats(player_id, event_id):
    """Get a player's stats for a specific past event."""
    try:
        from repositories.elo import EloRepository

        # Normalize player_id (strip 'google_' prefix for Google OAuth users)
        player_id_str = str(player_id)
        if player_id_str.startswith("google_"):
            player_id = player_id_str[7:]  # Remove 'google_' prefix

        repo = EloRepository()
        # Keep as string to avoid overflow with large Google IDs
        stats = repo.get_player_event_elo(player_id, event_id)
        if stats:
            return jsonify(stats)
        return jsonify({"error": "No data found for this player in this event"}), 404
    except Exception as e:
        logger.error(f"Error fetching player event stats: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@leaderboard_bp.route("/leaderboard/archived/<int:event_id>")
def get_archived_event_leaderboard(event_id):
    """Get full leaderboard for a specific archived event."""
    try:
        from repositories.elo import EloRepository

        repo = EloRepository()
        leaderboard = repo.get_archived_event_leaderboard(event_id)
        event_info = None

        # Get event info
        all_events = repo.get_all_events()
        for event in all_events:
            if event["event_id"] == event_id:
                event_info = event
                break

        return jsonify({
            "event_info": event_info,
            "leaderboard": leaderboard
        })
    except Exception as e:
        logger.error(f"Error fetching archived event leaderboard: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@leaderboard_bp.route("/leaderboard/archived/season/<season_id>")
def get_season_leaderboard(season_id):
    """Get leaderboard for a season date-range filter (computed from match records)."""
    season_key = f"season_{season_id}" if not season_id.startswith("season_") else season_id
    season = None
    for sf in SEASON_FILTERS:
        if sf["id"] == season_key:
            season = sf
            break
    if not season:
        return jsonify({"error": "Season not found"}), 404

    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()
        player_stats = Counter()
        player_names = {}

        # Query match_records within date range
        for table in ("match_records", "match_records_archive"):
            try:
                cur.execute(f"""
                    SELECT winner_id, winner_display_name, losser_id, losser_display_name
                    FROM {table}
                    WHERE (source = 'Discord' OR source IS NULL)
                      AND timestamp >= ? AND timestamp <= ?
                """, (season["start_date"], season["end_date"]))
                for row in cur.fetchall():
                    winner_id, winner_name, loser_id, loser_name = row
                    if winner_id:
                        player_stats[str(winner_id)] += 1
                        player_names[str(winner_id)] = winner_name or str(winner_id)
                    if loser_id:
                        player_stats[str(loser_id)] += 0
                        player_names[str(loser_id)] = loser_name or str(loser_id)
            except sqlite3.OperationalError:
                pass

        # Build leaderboard sorted by wins
        leaderboard = []
        for pid, wins in player_stats.most_common():
            leaderboard.append({
                "user_id": pid,
                "display_name": player_names.get(pid, pid),
                "event_elo": wins,  # Using wins count as the displayed value
            })

        conn.close()

        event_info = {
            "event_id": season["id"],
            "event_name": season["name"],
            "start_date": season["start_date"],
            "end_date": season["end_date"],
            "is_active": False,
        }

        return jsonify({
            "event_info": event_info,
            "leaderboard": leaderboard
        })
    except Exception as e:
        logger.error(f"Error fetching season leaderboard: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
