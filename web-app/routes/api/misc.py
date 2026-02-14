"""Miscellaneous API routes."""

import logging
from flask import Blueprint, jsonify
from services.youtube import get_latest_videos
from webapp_config import (
    MATCH_RECORDS_DB_PATH,
    ELO_DB_PATH,
    FART_SCORES_DB_PATH,
    COMMUNITY_DB_PATH,
)
from utils.auth import is_admin

misc_bp = Blueprint("misc", __name__)
logger = logging.getLogger(__name__)


@misc_bp.route("/status")
def status():
    """Simple API endpoint to check if the server is running."""
    return jsonify({"status": "online", "message": "Summit Web App is running!"})


@misc_bp.route("/youtube-videos")
def youtube_videos():
    """Get latest videos from community YouTube channels."""
    videos = get_latest_videos()
    return jsonify(videos)


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
