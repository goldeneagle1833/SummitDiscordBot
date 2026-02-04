"""API endpoints for streaming status."""

from flask import Blueprint, jsonify
import sqlite3
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

streamers_bp = Blueprint("streamers", __name__)

# Database path - same as used by the Discord bot
DB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "streamers.db"


def get_active_streamers():
    """Get all currently active streamers from the database."""
    if not DB_PATH.exists():
        return []

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, username, display_name, avatar_url, stream_url, 
                   stream_title, game_name, platform, started_at
            FROM active_streamers
            ORDER BY started_at DESC
        """)
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error fetching streamers: {e}")
        return []


@streamers_bp.route("/streamers")
def list_streamers():
    """Get all currently streaming members.

    Returns:
        JSON array of streamer objects with the following fields:
        - user_id: Discord user ID
        - username: Discord username
        - display_name: Server display name
        - avatar_url: URL to the user's avatar
        - stream_url: URL to the stream (Twitch, YouTube, etc.)
        - stream_title: Title of the stream
        - game_name: Name of the game being played
        - platform: Streaming platform (Twitch, YouTube, etc.)
        - started_at: ISO timestamp when streaming started
    """
    streamers = get_active_streamers()
    return jsonify({"count": len(streamers), "streamers": streamers})


@streamers_bp.route("/streamers/banner")
def streamer_banner():
    """Get a simplified response for the banner display.

    Returns only essential info for displaying a "someone is live" banner.
    """
    streamers = get_active_streamers()

    if not streamers:
        return jsonify({"is_live": False, "streamer": None})

    # Return the most recent streamer for the banner
    first_streamer = streamers[0]
    return jsonify(
        {
            "is_live": True,
            "count": len(streamers),
            "streamer": {
                "display_name": first_streamer["display_name"],
                "avatar_url": first_streamer["avatar_url"],
                "stream_url": first_streamer["stream_url"],
                "stream_title": first_streamer["stream_title"],
                "game_name": first_streamer["game_name"],
                "platform": first_streamer["platform"],
            },
        }
    )
