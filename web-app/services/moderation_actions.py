"""Time out, ban or pairing-block a player, or undo one, from the website.

Shared by the admin panel (``POST /api/admin/moderation``) and Mod Tools
(``POST /api/mod/action``) so both behave exactly the same.
"""

import logging

from repositories.audit import AuditRepository
from repositories.moderation_repo import (
    PAIRING_BLOCK_DURATIONS, ModerationRepository, lift_pairing_block, set_pairing_block,
)
from services import discord_moderation as dm

logger = logging.getLogger(__name__)

ACTIONS = ("timeout", "ban", "pairing_block")
UNDO_ACTIONS = ("remove_timeout", "unban", "lift_pairing_block")


def run_moderation(data: dict, *, by_id, by_name, target_name: str, role: str = "admin"):
    """Do one moderation action. Returns (json_body, http_status).

    ``data``: action, user_id, minutes (timeout), duration (pairing block),
    reason (required for timeout/ban/pairing block, 3+ characters; DMed to
    the player), source_kind ("block" | "report"), source_ref, confirm: true.
    Undo actions take an optional reason that is only kept in the log.
    """
    if data.get("confirm") is not True:
        return {"success": False, "error": "Confirmation required"}, 400

    action = data.get("action")
    if action not in ACTIONS + UNDO_ACTIONS:
        return {"success": False, "error": "Unknown action"}, 400
    user_id = str(data.get("user_id") or "").strip()
    reason = str(data.get("reason") or "").strip()[:1000] or None
    source_kind = data.get("source_kind") if data.get("source_kind") in ("block", "report") else None
    source_ref = str(data.get("source_ref") or "")[:64] or None
    minutes = None
    if action == "timeout":
        try:
            minutes = int(data.get("minutes"))
        except (TypeError, ValueError):
            return {"success": False, "error": "minutes is required for a timeout"}, 400

    if action in ACTIONS and (not reason or len(reason) < 3):
        return {"success": False, "error": "A reason is required; it is sent to the player"}, 400
    if not dm.is_discord_id(user_id):
        return {"success": False, "error": "Not a Discord account."}, 400

    who = by_name if role == "admin" else f"{by_name} (moderator)"
    tag = f"report #{source_ref}, " if source_kind == "report" and (source_ref or "").isdigit() else ""
    suffix = f" ({tag}by {who} on the website)"
    audit_reason = (reason or "Lifted early")[: 400 - len(suffix)] + suffix
    duration_label = None
    bot_done = True
    dm_sent = None

    try:
        if action == "pairing_block":
            duration = data.get("duration")
            if duration not in PAIRING_BLOCK_DURATIONS:
                return {"success": False, "error": "Pick 24 hours, 48 hours, 72 hours or lifetime"}, 400
            duration_label = set_pairing_block(
                None, user_id=user_id, user_name=target_name,
                by_id=by_id, by_name=who, reason=reason, duration_key=duration,
            )
            bot_done = False  # the bot pulls them from the queue and DMs them
        elif action == "timeout":
            dm.timeout_member(user_id, minutes, audit_reason)
            dm_sent = dm.send_dm(user_id, dm.player_dm_embed("timeout", reason, minutes)) is not None
        elif action == "ban":
            # DM first: once banned they share no server with the bot.
            sent = dm.send_dm(user_id, dm.player_dm_embed("ban", reason))
            try:
                dm.ban_user(user_id, audit_reason)
            except dm.ModerationError:
                dm.delete_dm(sent)
                raise
            dm_sent = sent is not None
        elif action == "remove_timeout":
            dm.remove_timeout(user_id, audit_reason)
            dm_sent = dm.send_dm(user_id, dm.lifted_dm_embed(action)) is not None
        elif action == "unban":
            dm.unban_user(user_id, audit_reason)
        elif action == "lift_pairing_block":
            if not lift_pairing_block(None, user_id):
                return {"success": False, "error": "They don't have a pairing block."}, 400
            dm_sent = dm.send_dm(user_id, dm.lifted_dm_embed(action)) is not None
    except dm.ModerationError as e:
        return {"success": False, "error": str(e)}, 400

    repo = ModerationRepository()
    repo.log_action(
        target_id=user_id, target_name=target_name, action=action,
        duration_minutes=minutes, duration_label=duration_label, reason=reason,
        source_kind=source_kind, source_ref=source_ref, by_id=by_id,
        by_name=who, via="web", bot_done=bot_done,
    )
    audit_action = {
        "pairing_block": "web_pairing_ban",
        "lift_pairing_block": "web_pairing_unban",
    }.get(action, f"web_discord_{action}")
    AuditRepository().log_action(
        by_id, who, audit_action,
        target_id=user_id, target_name=target_name,
        new_state={"minutes": minutes, "duration_label": duration_label},
        details=reason,
    )
    logger.info("%s %s: %s %s (%s)", role, by_name, action, user_id, minutes or duration_label)
    return {
        "success": True,
        "moderation": repo.latest_by_target([user_id]).get(user_id),
        "status": repo.status_by_target([user_id]).get(user_id),
        "dm_sent": dm_sent,
    }, 200
