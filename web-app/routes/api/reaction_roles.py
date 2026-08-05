"""Reaction roles admin API routes."""

import logging

from flask import Blueprint, jsonify, request

from repositories.reaction_roles import ReactionRolesRepository
from utils.auth import require_admin

logger = logging.getLogger(__name__)

reaction_roles_bp = Blueprint("reaction_roles", __name__)


@reaction_roles_bp.route("/messages", methods=["GET"])
@require_admin
def get_messages():
    """List all tracked reaction role messages with their mappings."""
    repo = ReactionRolesRepository()
    messages = repo.get_all_messages()
    mappings = repo.get_all_mappings()

    # Group mappings by message_id
    by_msg = {}
    for m in mappings:
        by_msg.setdefault(m["message_id"], []).append(m)

    for msg in messages:
        msg["mappings"] = by_msg.get(msg["message_id"], [])

    return jsonify({"success": True, "messages": messages})


@reaction_roles_bp.route("/messages", methods=["POST"])
@require_admin
def add_message():
    """Add a new message to track for reaction roles."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    channel_id = str(data.get("channel_id", "")).strip()
    message_id = str(data.get("message_id", "")).strip()
    label = str(data.get("label", "")).strip()

    if not channel_id or not message_id:
        return jsonify({"success": False, "error": "channel_id and message_id are required"}), 400

    repo = ReactionRolesRepository()
    try:
        msg = repo.add_message(channel_id, message_id, label)
    except Exception as e:
        if "UNIQUE" in str(e):
            return jsonify({"success": False, "error": "Message already tracked"}), 409
        raise
    return jsonify({"success": True, "message": msg}), 201


@reaction_roles_bp.route("/messages/<message_id>", methods=["DELETE"])
@require_admin
def delete_message(message_id):
    """Remove a tracked message and all its mappings."""
    repo = ReactionRolesRepository()
    deleted = repo.delete_message(message_id)
    if not deleted:
        return jsonify({"success": False, "error": "Message not found"}), 404
    return jsonify({"success": True})


@reaction_roles_bp.route("/mappings", methods=["POST"])
@require_admin
def add_mapping():
    """Add an emoji -> role mapping to a tracked message."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    message_id = str(data.get("message_id", "")).strip()
    emoji = str(data.get("emoji", "")).strip()
    role_id = str(data.get("role_id", "")).strip()
    role_name = str(data.get("role_name", "")).strip()
    emoji_id = data.get("emoji_id")
    if emoji_id:
        emoji_id = str(emoji_id).strip()

    if not message_id or not emoji or not role_id:
        return jsonify({"success": False, "error": "message_id, emoji, and role_id are required"}), 400

    repo = ReactionRolesRepository()

    # Verify message is tracked
    tracked = repo.get_all_message_ids()
    if message_id not in tracked:
        return jsonify({"success": False, "error": "Message is not tracked. Add the message first."}), 400

    try:
        mapping = repo.add_mapping(message_id, emoji, role_id, role_name, emoji_id)
    except Exception as e:
        if "UNIQUE" in str(e):
            return jsonify({"success": False, "error": "This emoji is already mapped on this message"}), 409
        raise
    return jsonify({"success": True, "mapping": mapping}), 201


@reaction_roles_bp.route("/mappings/<int:mapping_id>", methods=["DELETE"])
@require_admin
def delete_mapping(mapping_id):
    """Remove an emoji -> role mapping."""
    repo = ReactionRolesRepository()
    deleted = repo.delete_mapping(mapping_id)
    if not deleted:
        return jsonify({"success": False, "error": "Mapping not found"}), 404
    return jsonify({"success": True})
