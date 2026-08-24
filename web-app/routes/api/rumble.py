"""Rumble API routes - standings, bones, prizes, and admin management."""

import logging

from flask import Blueprint, jsonify, request, session

from repositories.fart import FartRepository
from repositories.matches import MatchRepository
from repositories.rumble_repo import RumbleRepository
from utils.auth import require_admin, require_auth, require_rumble_admin

logger = logging.getLogger(__name__)

rumble_bp = Blueprint("rumble", __name__)


# --- Public endpoints ---

@rumble_bp.route("/rumble")
def get_rumble():
    """Return rumble standings, recent matches, bones leaderboard, prizes, and earnings config."""
    try:
        match_repo = MatchRepository()
        rumble_repo = RumbleRepository()
        limit = request.args.get("limit", 50, type=int)

        fart_repo = FartRepository()

        standings = match_repo.get_rumble_standings()
        matches = match_repo.get_rumble_matches(limit=limit)
        balances = rumble_repo.get_all_balances()
        prizes = rumble_repo.get_prizes(active_only=True)
        earnings = rumble_repo.get_earnings_config()
        fart_leaderboard = fart_repo.get_leaderboard()
        fart_commands = fart_repo.get_commands()
        fart_shop_items = fart_repo.get_shop_items()

        return jsonify({
            "standings": standings,
            "matches": matches,
            "total_matches": sum(p["wins"] + p["losses"] for p in standings) // 2 if standings else 0,
            "bones": balances,
            "prizes": prizes,
            "earnings": earnings,
            "fart_leaderboard": fart_leaderboard,
            "fart_commands": fart_commands,
            "fart_shop_items": fart_shop_items,
        })
    except Exception as e:
        logger.error(f"Error fetching rumble data: {e}")
        return jsonify({"error": str(e)}), 500


# --- Rumble admin endpoints ---

@rumble_bp.route("/rumble/admin/bones", methods=["POST"])
@require_rumble_admin
def adjust_player_bones():
    """Add or remove bones for a player."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400

    discord_user_id = data.get("discord_user_id")
    amount = data.get("amount")
    reason = data.get("reason", "Manual adjustment")
    display_name = data.get("display_name")

    if not discord_user_id or amount is None:
        return jsonify({"error": "discord_user_id and amount are required"}), 400

    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return jsonify({"error": "amount must be an integer"}), 400

    repo = RumbleRepository()
    admin_id = session.get("user_id")
    new_balance = repo.adjust_bones(
        discord_user_id, amount, reason, display_name, str(admin_id) if admin_id else None
    )
    return jsonify({"success": True, "new_balance": new_balance})


@rumble_bp.route("/rumble/admin/bones/set", methods=["POST"])
@require_rumble_admin
def set_player_bones():
    """Set a player's bones to an exact amount."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400

    discord_user_id = data.get("discord_user_id")
    amount = data.get("amount")
    reason = data.get("reason", "Set by admin")
    display_name = data.get("display_name")

    if not discord_user_id or amount is None:
        return jsonify({"error": "discord_user_id and amount are required"}), 400

    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return jsonify({"error": "amount must be an integer"}), 400

    repo = RumbleRepository()
    admin_id = session.get("user_id")
    new_balance = repo.set_bones(
        discord_user_id, amount, reason, display_name, str(admin_id) if admin_id else None
    )
    return jsonify({"success": True, "new_balance": new_balance})


@rumble_bp.route("/rumble/admin/bones/<discord_user_id>/transactions")
@require_rumble_admin
def get_bone_transactions(discord_user_id):
    """Get transaction history for a player."""
    repo = RumbleRepository()
    transactions = repo.get_transactions(discord_user_id)
    return jsonify({"transactions": transactions})


@rumble_bp.route("/rumble/admin/bones/<discord_user_id>", methods=["PUT"])
@require_rumble_admin
def update_bone_entry(discord_user_id):
    """Update a player's bone entry (display name, balance)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400

    repo = RumbleRepository()
    admin_id = session.get("user_id")
    success = repo.update_bone_entry(
        discord_user_id,
        display_name=data.get("display_name"),
        balance=int(data["balance"]) if data.get("balance") is not None else None,
        admin_user_id=str(admin_id) if admin_id else None,
    )
    if success:
        return jsonify({"success": True})
    return jsonify({"error": "Player not found"}), 404


@rumble_bp.route("/rumble/admin/bones/<discord_user_id>", methods=["DELETE"])
@require_rumble_admin
def delete_bone_entry(discord_user_id):
    """Delete a player's bone balance and transaction history."""
    repo = RumbleRepository()
    if repo.delete_bone_entry(discord_user_id):
        return jsonify({"success": True})
    return jsonify({"error": "Player not found"}), 404


@rumble_bp.route("/rumble/admin/earnings", methods=["PUT"])
@require_rumble_admin
def update_earnings_config():
    """Update bone earnings for a config key."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400

    key = data.get("key")
    bones = data.get("bones")

    if not key or bones is None:
        return jsonify({"error": "key and bones are required"}), 400

    try:
        bones = int(bones)
    except (TypeError, ValueError):
        return jsonify({"error": "bones must be an integer"}), 400

    repo = RumbleRepository()
    if repo.update_earning(key, bones):
        return jsonify({"success": True})
    return jsonify({"error": "Earning key not found"}), 404


@rumble_bp.route("/rumble/admin/standings/<user_id>", methods=["PUT"])
@require_rumble_admin
def update_rumble_standing(user_id):
    """Update a player's rumble standing (display name, wins, losses)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400

    repo = MatchRepository()
    success = repo.update_rumble_player(
        user_id=user_id,
        display_name=data.get("display_name"),
        wins=data.get("wins") if data.get("wins") is not None else None,
        losses=data.get("losses") if data.get("losses") is not None else None,
    )
    if success:
        return jsonify({"success": True})
    return jsonify({"error": "Player not found or update failed"}), 404


@rumble_bp.route("/rumble/admin/standings/<user_id>", methods=["DELETE"])
@require_rumble_admin
def delete_rumble_standing(user_id):
    """Delete all rumble match records for a player."""
    repo = MatchRepository()
    if repo.delete_rumble_player(user_id):
        return jsonify({"success": True})
    return jsonify({"error": "Player not found"}), 404


@rumble_bp.route("/rumble/admin/prizes", methods=["POST"])
@require_rumble_admin
def add_prize():
    """Add a new prize to the prize wall."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400

    name = data.get("name")
    if not name:
        return jsonify({"error": "name is required"}), 400

    repo = RumbleRepository()
    prize_id = repo.add_prize(
        name=name,
        cost=data.get("cost", 0),
        stock=data.get("stock"),
        description=data.get("description"),
        sort_order=data.get("sort_order"),
    )
    return jsonify({"success": True, "id": prize_id})


@rumble_bp.route("/rumble/admin/prizes/<int:prize_id>", methods=["PUT"])
@require_rumble_admin
def update_prize(prize_id):
    """Update a prize (cost, stock, name, etc)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400

    repo = RumbleRepository()
    if repo.update_prize(prize_id, **data):
        return jsonify({"success": True})
    return jsonify({"error": "Prize not found or no valid fields"}), 404


@rumble_bp.route("/rumble/admin/prizes/<int:prize_id>", methods=["DELETE"])
@require_rumble_admin
def delete_prize(prize_id):
    """Delete a prize from the wall."""
    repo = RumbleRepository()
    if repo.delete_prize(prize_id):
        return jsonify({"success": True})
    return jsonify({"error": "Prize not found"}), 404


@rumble_bp.route("/rumble/admin/prizes/reorder", methods=["POST"])
@require_rumble_admin
def reorder_prizes():
    """Swap sort_order between two prizes."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400

    prize_id_a = data.get("prize_id_a")
    prize_id_b = data.get("prize_id_b")
    if not prize_id_a or not prize_id_b:
        return jsonify({"error": "prize_id_a and prize_id_b are required"}), 400

    repo = RumbleRepository()
    if repo.swap_prize_order(int(prize_id_a), int(prize_id_b)):
        return jsonify({"success": True})
    return jsonify({"error": "One or both prizes not found"}), 404


@rumble_bp.route("/rumble/admin/redemptions")
@require_rumble_admin
def get_redemptions():
    """Return recent prize redemption history (rumble admins only)."""
    try:
        limit = request.args.get("limit", 100, type=int)
        repo = RumbleRepository()
        redemptions = repo.get_redemptions(limit=limit)
        return jsonify({"redemptions": redemptions})
    except Exception as e:
        logger.error(f"Error fetching rumble redemptions: {e}")
        return jsonify({"error": str(e)}), 500


# --- Player redemption (requires login) ---

@rumble_bp.route("/rumble/redeem/<int:prize_id>", methods=["POST"])
@require_auth
def redeem_prize(prize_id):
    """Redeem a prize using bones."""
    user_id = session.get("user_id")
    username = session.get("username")

    repo = RumbleRepository()
    result = repo.redeem_prize(
        discord_user_id=str(user_id),
        prize_id=prize_id,
        display_name=username,
    )
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# --- Fart game admin endpoints ---

@rumble_bp.route("/rumble/admin/fart/reset", methods=["POST"])
@require_rumble_admin
def reset_fart_game():
    """Full season reset — clear all scores, history, and every tracking table."""
    repo = FartRepository()
    result = repo.reset_game()
    return jsonify({"success": True, "cleared": result})


@rumble_bp.route("/rumble/admin/fart/evil-start", methods=["POST"])
@require_rumble_admin
def evil_start_fart_game():
    """Evil start - reset game and give players random chaotic starting scores."""
    repo = FartRepository()
    result = repo.evil_start()
    return jsonify({"success": True, **result})


@rumble_bp.route("/rumble/admin/fart/commands")
@require_rumble_admin
def get_fart_commands():
    """Get all fart game command configs."""
    repo = FartRepository()
    return jsonify({"commands": repo.get_commands()})


@rumble_bp.route("/rumble/admin/fart/commands", methods=["POST"])
@require_rumble_admin
def add_fart_command():
    """Add a new fart game command config."""
    data = request.get_json(silent=True)
    if not data or not data.get("name") or not data.get("label"):
        return jsonify({"error": "name and label are required"}), 400

    repo = FartRepository()
    try:
        command_id = repo.add_command(
            name=data["name"],
            label=data["label"],
            description=data.get("description"),
            cost=int(data.get("cost", 0)),
            damage=int(data.get("damage", 0)),
            cooldown=data.get("cooldown", "daily"),
            effect=data.get("effect"),
        )
    except Exception as e:
        if "UNIQUE" in str(e):
            return jsonify({"error": f"Command '{data['name']}' already exists"}), 400
        return jsonify({"error": str(e)}), 400
    return jsonify({"success": True, "id": command_id})


@rumble_bp.route("/rumble/admin/fart/commands/<int:command_id>", methods=["PUT"])
@require_rumble_admin
def update_fart_command(command_id):
    """Update a fart game command config."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400

    repo = FartRepository()
    if repo.update_command(command_id, **data):
        return jsonify({"success": True})
    return jsonify({"error": "Command not found or no valid fields"}), 404


@rumble_bp.route("/rumble/admin/fart/commands/<int:command_id>", methods=["DELETE"])
@require_rumble_admin
def delete_fart_command(command_id):
    """Delete a fart game command config."""
    repo = FartRepository()
    if repo.delete_command(command_id):
        return jsonify({"success": True})
    return jsonify({"error": "Command not found"}), 404


# --- Fart shop item admin endpoints ---

@rumble_bp.route("/rumble/admin/fart/shop")
@require_rumble_admin
def get_fart_shop_items():
    """Get all fart shop item configs."""
    repo = FartRepository()
    return jsonify({"items": repo.get_shop_items()})


@rumble_bp.route("/rumble/admin/fart/shop", methods=["POST"])
@require_rumble_admin
def add_fart_shop_item():
    """Add a new fart shop item."""
    data = request.get_json(silent=True)
    if not data or not data.get("name") or not data.get("label"):
        return jsonify({"error": "name and label are required"}), 400

    repo = FartRepository()
    try:
        item_id = repo.add_shop_item(
            name=data["name"],
            label=data["label"],
            description=data.get("description"),
            cost=int(data.get("cost", 0)),
            damage=int(data.get("damage", 0)),
            cooldown=data.get("cooldown", "none"),
            effect=data.get("effect"),
        )
    except Exception as e:
        if "UNIQUE" in str(e):
            return jsonify({"error": f"Shop item '{data['name']}' already exists"}), 400
        return jsonify({"error": str(e)}), 400
    return jsonify({"success": True, "id": item_id})


@rumble_bp.route("/rumble/admin/fart/shop/<int:item_id>", methods=["PUT"])
@require_rumble_admin
def update_fart_shop_item(item_id):
    """Update a fart shop item."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400

    repo = FartRepository()
    if repo.update_shop_item(item_id, **data):
        return jsonify({"success": True})
    return jsonify({"error": "Shop item not found or no valid fields"}), 404


@rumble_bp.route("/rumble/admin/fart/shop/<int:item_id>", methods=["DELETE"])
@require_rumble_admin
def delete_fart_shop_item(item_id):
    """Delete a fart shop item."""
    repo = FartRepository()
    if repo.delete_shop_item(item_id):
        return jsonify({"success": True})
    return jsonify({"error": "Shop item not found"}), 404


# --- Rumble admin management (global admins only) ---

@rumble_bp.route("/rumble/admin/admins")
@require_admin
def list_rumble_admins():
    """List all rumble admins."""
    repo = RumbleRepository()
    return jsonify({"admins": repo.get_admins()})


@rumble_bp.route("/rumble/admin/admins", methods=["POST"])
@require_admin
def add_rumble_admin():
    """Add a rumble admin (global admins only)."""
    data = request.get_json(silent=True)
    if not data or not data.get("discord_user_id"):
        return jsonify({"error": "discord_user_id is required"}), 400

    repo = RumbleRepository()
    repo.add_admin(data["discord_user_id"], data.get("display_name"))
    return jsonify({"success": True})


@rumble_bp.route("/rumble/admin/admins/<discord_user_id>", methods=["DELETE"])
@require_admin
def remove_rumble_admin(discord_user_id):
    """Remove a rumble admin (global admins only)."""
    repo = RumbleRepository()
    if repo.remove_admin(discord_user_id):
        return jsonify({"success": True})
    return jsonify({"error": "Admin not found"}), 404
