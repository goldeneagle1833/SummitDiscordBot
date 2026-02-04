"""Miscellaneous API routes."""

from flask import Blueprint, jsonify
from services.youtube import get_latest_videos

misc_bp = Blueprint("misc", __name__)


@misc_bp.route("/status")
def status():
    """Simple API endpoint to check if the server is running."""
    return jsonify({"status": "online", "message": "Summit Web App is running!"})


@misc_bp.route("/youtube-videos")
def youtube_videos():
    """Get latest videos from community YouTube channels."""
    videos = get_latest_videos()
    return jsonify(videos)
