"""Miscellaneous API routes."""

import logging
from flask import Blueprint, jsonify, session
from services.youtube import get_latest_videos
from webapp_config import (
    MATCH_RECORDS_DB_PATH,
    ELO_DB_PATH,
    FART_SCORES_DB_PATH,
    COMMUNITY_DB_PATH,
    ADMINS,
)
from utils.auth import is_admin

misc_bp = Blueprint("misc", __name__)
logger = logging.getLogger(__name__)


@misc_bp.route("/me")
def me():
    """Return current authenticated user from session, or 401 if not logged in."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify({
        "user_id": str(user_id),
        "username": session.get("username"),
        "avatar": session.get("avatar"),
        "auth_provider": session.get("auth_provider"),
        "is_admin": str(user_id) in ADMINS,
    })


@misc_bp.route("/logout")
def logout():
    """Clear session and log out user (API alias for /auth/logout)."""
    username = session.get("username", "Unknown")
    session.clear()
    logger.info(f"User {username} logged out via /api/logout")
    return jsonify({"success": True})


@misc_bp.route("/recent-event")
def recent_event():
    """Get the most recently added top-8 event if within 48 hours."""
    from repositories.events import EventRepository
    repo = EventRepository()
    event = repo.get_recent_event(hours=48)
    return jsonify({"event": event})


@misc_bp.route("/status")
def status():
    """Simple API endpoint to check if the server is running."""
    return jsonify({"status": "online", "message": "Summit Web App is running!"})


@misc_bp.route("/youtube-videos")
def youtube_videos():
    """Get latest videos from community YouTube channels."""
    videos = get_latest_videos()
    return jsonify(videos)


@misc_bp.route("/community")
def community():
    """Get community links: Discord servers, websites, and YouTube channels."""
    from repositories.community import CommunityRepository
    repo = CommunityRepository()
    return jsonify({
        "discord_servers": repo.get_discord_servers(),
        "websites": repo.get_websites(),
    })


@misc_bp.route("/debug/database-status")
def database_status():
    """Debug endpoint to check database file paths and existence (admin only)."""
    if not is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    databases = {
        "match_records": {
            "path": str(MATCH_RECORDS_DB_PATH),
            "exists": MATCH_RECORDS_DB_PATH.exists(),
        },
        "elo": {
            "path": str(ELO_DB_PATH),
            "exists": ELO_DB_PATH.exists(),
        },
        "fart_scores": {
            "path": str(FART_SCORES_DB_PATH),
            "exists": FART_SCORES_DB_PATH.exists(),
        },
        "community": {
            "path": str(COMMUNITY_DB_PATH),
            "exists": COMMUNITY_DB_PATH.exists(),
        },
    }

    # Try to get row counts for existing databases
    for db_name, db_info in databases.items():
        if db_info["exists"]:
            try:
                import sqlite3
                conn = sqlite3.connect(db_info["path"])
                cur = conn.cursor()

                # Get table names
                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cur.fetchall()]
                db_info["tables"] = tables

                # Get row counts for main tables
                if db_name == "match_records" and "match_records" in tables:
                    cur.execute("SELECT COUNT(*) FROM match_records")
                    db_info["row_count"] = cur.fetchone()[0]

                conn.close()
            except Exception as e:
                db_info["error"] = str(e)

    return jsonify(databases)
