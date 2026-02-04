"""API endpoints for streaming status."""

from flask import Blueprint, jsonify, request
import sqlite3
from pathlib import Path
import logging
import os

logger = logging.getLogger(__name__)

streamers_bp = Blueprint("streamers", __name__)

# Database path - same as used by the Discord bot
DB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "streamers.db"

# Demo mode - set to True to show dummy data for testing
DEMO_MODE = os.environ.get("STREAMER_DEMO", "0") == "1"

DEMO_STREAMERS = [
    {
        "user_id": 123456789,
        "username": "goldeneagle1833",
        "display_name": "Goldeneagle",
        "avatar_url": "https://cdn.discordapp.com/embed/avatars/0.png",
        "stream_url": "https://www.twitch.tv/goldeneagle1833",
        "stream_title": "Playing Sorcery TCG - Come hang out!",
        "game_name": "Sorcery: Contested Realm",
        "platform": "Twitch",
        "started_at": "2026-02-04T12:00:00",
    },
    {
        "user_id": 987654321,
        "username": "oldfashionednerds",
        "display_name": "OldFashionedNerds",
        "avatar_url": "https://cdn.discordapp.com/embed/avatars/1.png",
        "stream_url": "https://www.youtube.com/@Oldfashionednerds",
        "stream_title": "Sorcery Draft Night!",
        "game_name": "Sorcery: Contested Realm",
        "platform": "YouTube",
        "started_at": "2026-02-04T11:30:00",
    },
    {
        "user_id": 555555555,
        "username": "sorcerystreamer",
        "display_name": "SorceryStreamer",
        "avatar_url": "https://cdn.discordapp.com/embed/avatars/2.png",
        "stream_url": "https://www.twitch.tv/sorcerystreamer",
        "stream_title": "Competitive Matches",
        "game_name": "Sorcery: Contested Realm",
        "platform": "Twitch",
        "started_at": "2026-02-04T10:00:00",
    },
]

# For single-streamer endpoints
DEMO_STREAMER = DEMO_STREAMERS[0]


def get_active_streamers():
    """Get all currently active streamers from the database."""
    # Return demo data if in demo mode
    if DEMO_MODE:
        return [DEMO_STREAMER]

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
    # Force demo mode for localhost testing
    if request.host.startswith("127.0.0.1") or request.host.startswith("localhost"):
        return jsonify({"count": len(DEMO_STREAMERS), "streamers": DEMO_STREAMERS})

    streamers = get_active_streamers()
    return jsonify({"count": len(streamers), "streamers": streamers})


@streamers_bp.route("/streamers/banner")
def streamer_banner():
    """Get a simplified response for the banner display.

    Returns only essential info for displaying a "someone is live" banner.
    """
    # Force demo mode for localhost testing
    if request.host.startswith("127.0.0.1") or request.host.startswith("localhost"):
        streamer = DEMO_STREAMER
        return jsonify(
            {
                "is_live": True,
                "count": 1,
                "streamer": {
                    "display_name": streamer["display_name"],
                    "avatar_url": streamer["avatar_url"],
                    "stream_url": streamer["stream_url"],
                    "stream_title": streamer["stream_title"],
                    "game_name": streamer["game_name"],
                    "platform": streamer["platform"],
                },
            }
        )

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
