"""Reaction roles admin API routes."""

import logging
import unicodedata

from flask import Blueprint, jsonify, request

from repositories.reaction_roles import ReactionRolesRepository
from utils.auth import require_admin

logger = logging.getLogger(__name__)

reaction_roles_bp = Blueprint("reaction_roles", __name__)

# Discord limits: 20 distinct reactions per message, 256-char embed titles.
MAX_REACTIONS = 20
TITLE_MAX = 256
BODY_MAX = 2000


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

    return jsonify({"success": True, "messages": messages, "posts": repo.get_open_posts()})


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
    repo.enqueue("sync", message_id=message_id)
    return jsonify({"success": True, "message": msg}), 201


@reaction_roles_bp.route("/messages/<message_id>", methods=["PATCH"])
@require_admin
def update_message(message_id):
    """Edit the title/body of a message the bot posted; the bot edits it in Discord."""
    data = request.get_json() or {}
    title = str(data.get("title", "")).strip()
    body = str(data.get("body", "")).strip()
    if not title:
        return jsonify({"success": False, "error": "Title is required"}), 400
    if len(title) > TITLE_MAX or len(body) > BODY_MAX:
        return jsonify({"success": False, "error": "Title or text is too long"}), 400

    repo = ReactionRolesRepository()
    if not repo.update_message_text(message_id, title, body):
        return jsonify({"success": False, "error": "Only messages posted by the bot can be edited"}), 404
    repo.enqueue("sync", message_id=message_id)
    return jsonify({"success": True})


@reaction_roles_bp.route("/messages/<message_id>", methods=["DELETE"])
@require_admin
def delete_message(message_id):
    """Remove a tracked message and all its mappings."""
    repo = ReactionRolesRepository()
    msg = repo.get_message(message_id)
    if not msg or not repo.delete_message(message_id):
        return jsonify({"success": False, "error": "Message not found"}), 404
    # Bot-posted messages are deleted from Discord; for others the bot only
    # takes back its own reactions.
    action = "delete_post" if msg.get("managed") else "clear"
    repo.enqueue(action, message_id=message_id, channel_id=msg["channel_id"])
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

    # Normalize emoji: convert names like ":volcano:" or "volcano" to the Unicode character
    if emoji.isascii():
        name = emoji.strip(":").strip()
        if name:
            try:
                emoji = unicodedata.lookup(name.upper())
            except KeyError:
                pass  # Keep original (may be a custom emoji name like "HATE")

    repo = ReactionRolesRepository()

    # Verify message is tracked
    tracked = repo.get_all_message_ids()
    if message_id not in tracked:
        return jsonify({"success": False, "error": "Message is not tracked. Add the message first."}), 400
    if repo.count_mappings(message_id) >= MAX_REACTIONS:
        return jsonify({
            "success": False,
            "error": f"Discord allows {MAX_REACTIONS} different reactions per message. Start a new message for more roles.",
        }), 400

    try:
        mapping = repo.add_mapping(message_id, emoji, role_id, role_name, emoji_id)
    except Exception as e:
        if "UNIQUE" in str(e):
            return jsonify({"success": False, "error": "This emoji is already mapped on this message"}), 409
        raise
    repo.enqueue("sync", message_id=message_id)
    return jsonify({"success": True, "mapping": mapping}), 201


@reaction_roles_bp.route("/mappings/<int:mapping_id>", methods=["DELETE"])
@require_admin
def delete_mapping(mapping_id):
    """Remove an emoji -> role mapping."""
    repo = ReactionRolesRepository()
    mapping = repo.get_mapping(mapping_id)
    if not mapping or not repo.delete_mapping(mapping_id):
        return jsonify({"success": False, "error": "Mapping not found"}), 404
    repo.enqueue("sync", message_id=mapping["message_id"])
    return jsonify({"success": True})


@reaction_roles_bp.route("/posts", methods=["POST"])
@require_admin
def create_post():
    """Have the bot post a new role message; roles are added to it afterwards."""
    data = request.get_json() or {}
    channel_id = str(data.get("channel_id", "")).strip()
    title = str(data.get("title", "")).strip()
    body = str(data.get("body", "")).strip()
    if not channel_id.isdigit():
        return jsonify({"success": False, "error": "A numeric Channel ID is required"}), 400
    if not title:
        return jsonify({"success": False, "error": "Title is required"}), 400
    if len(title) > TITLE_MAX or len(body) > BODY_MAX:
        return jsonify({"success": False, "error": "Title or text is too long"}), 400

    repo = ReactionRolesRepository()
    post = repo.create_post(channel_id, title, body)
    repo.enqueue("post", channel_id=channel_id, post_id=post["id"])
    return jsonify({"success": True, "post": post}), 201


@reaction_roles_bp.route("/posts/<int:post_id>", methods=["DELETE"])
@require_admin
def delete_post(post_id):
    """Dismiss a pending or failed post."""
    repo = ReactionRolesRepository()
    if not repo.delete_post(post_id):
        return jsonify({"success": False, "error": "Post not found"}), 404
    return jsonify({"success": True})
