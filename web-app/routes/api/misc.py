"""Miscellaneous API routes."""

from flask import Blueprint, jsonify

misc_bp = Blueprint("misc", __name__)


@misc_bp.route("/status")
def status():
    """Simple API endpoint to check if the server is running."""
    return jsonify({"status": "online", "message": "Summit Web App is running!"})
