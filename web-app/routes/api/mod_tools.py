"""Mod Tools: the moderator side of the website.

Moderators (Discord IDs an admin adds here) can read player reports, sort
and filter them, look players up by name or Discord ID, and time out, ban or
pairing-block someone (or lift it). They get nothing else: these routes
return report and moderation data only, never profile, deck or match data,
and every other admin route still requires a real admin.
"""

import logging
import re

from flask import Blueprint, jsonify, request, session

from utils.auth import require_admin, require_moderator

mod_tools_bp = Blueprint("mod_tools", __name__)
logger = logging.getLogger(__name__)

DISCORD_ID = re.compile(r"^\d{15,25}$")
SORTS = ("newest", "oldest", "most_reported", "name")
STATES = ("all", "open", "actioned")


def _me():
    return session.get("user_id", 0), session.get("username", "API")


def _role() -> str:
    from utils.auth import is_admin
    return "admin" if is_admin() else "moderator"


def _resolver():
    from routes.api.admin import _player_name_resolver
    return _player_name_resolver()


def _all_reports() -> list[dict]:
    from repositories.player_reports_repo import PlayerReportsRepository
    rows, _ = PlayerReportsRepository().get_all_reports(limit=100000, offset=0)
    return rows


@mod_tools_bp.route("/mod/reports", methods=["GET"])
@require_moderator
def mod_reports():
    """Player reports for moderators.

    Query: sort (newest | oldest | most_reported | name), state (all | open |
    actioned: open = no timeout/ban/pairing block on the reported player
    since the report), reason (one REPORT_REASONS value), q (name or Discord
    ID of either player), reported_id (one player), limit, offset.
    """
    from repositories.moderation_repo import ModerationRepository
    from services.discord_moderation import is_discord_id

    sort = request.args.get("sort", "newest")
    sort = sort if sort in SORTS else "newest"
    state = request.args.get("state", "all")
    state = state if state in STATES else "all"
    reason = (request.args.get("reason") or "").strip()
    q = (request.args.get("q") or "").strip().lower()
    reported_id = (request.args.get("reported_id") or "").strip()
    limit = min(max(1, request.args.get("limit", 50, type=int)), 200)
    offset = max(0, request.args.get("offset", 0, type=int))

    resolve = _resolver()
    rows = _all_reports()
    against: dict[str, int] = {}
    for r in rows:
        against[str(r["reported_id"])] = against.get(str(r["reported_id"]), 0) + 1

    entries = []
    for r in rows:
        entries.append({
            "id": r["id"],
            "reporter_id": r["reporter_id"],
            "reporter_name": resolve(r["reporter_id"], r["reporter_name"]),
            "reported_id": r["reported_id"],
            "reported_name": resolve(r["reported_id"], r["reported_name"]),
            "match_type": r["match_type"],
            "reasons": r["reasons"],
            "details": r["details"],
            "source": r.get("source"),
            "created_at": r["created_at"],
            "reports_against": against.get(str(r["reported_id"]), 0),
        })

    if reported_id:
        entries = [e for e in entries if str(e["reported_id"]) == reported_id]
    if reason:
        entries = [e for e in entries if reason in (e["reasons"] or [])]
    if q:
        entries = [
            e for e in entries
            if q in str(e["reported_name"] or "").lower() or q in str(e["reporter_name"] or "").lower()
            or q == str(e["reported_id"]) or q == str(e["reporter_id"])
        ]

    repo = ModerationRepository()
    history = repo.history(e["reported_id"] for e in entries)
    punitive = ("timeout", "ban", "pairing_block")
    for e in entries:
        acted = [a for a in history.get(str(e["reported_id"]), [])
                 if a["action"] in punitive and (a["created_at"] or "") >= (e["created_at"] or "")]
        e["actioned"] = bool(acted)
    if state == "open":
        entries = [e for e in entries if not e["actioned"]]
    elif state == "actioned":
        entries = [e for e in entries if e["actioned"]]

    if sort == "oldest":
        entries.sort(key=lambda e: (e["created_at"] or "", e["id"]))
    elif sort == "most_reported":
        entries.sort(key=lambda e: (-e["reports_against"], str(e["reported_name"]).lower(),
                                    _neg(e["created_at"]), -e["id"]))
    elif sort == "name":
        entries.sort(key=lambda e: (str(e["reported_name"]).lower(), _neg(e["created_at"]), -e["id"]))
    # newest: already newest first from the repository

    total = len(entries)
    page = entries[offset: offset + limit]
    targets = [e["reported_id"] for e in page]
    latest = repo.latest_by_target(targets)
    status = repo.status_by_target(targets)
    for e in page:
        target = str(e["reported_id"])
        e["can_moderate"] = is_discord_id(target)
        e["moderation"] = latest.get(target)
        e["status"] = status.get(target)

    return jsonify({"success": True, "entries": page, "total": total}), 200


def _neg(text):
    """Sort key that puts later timestamps first inside an ascending sort."""
    return tuple(-ord(c) for c in (text or ""))


@mod_tools_bp.route("/mod/players", methods=["GET"])
@require_moderator
def mod_player_search():
    """Find players by name or Discord ID: report counts and moderation only.

    No profile, deck or match data is returned.
    """
    from repositories.blocked_users_repo import BlockedUsersRepository  # noqa: F401 (table)
    from repositories.elo import EloRepository
    from repositories.moderation_repo import ModerationRepository
    from repositories.user_profiles import UserProfileRepository
    from services.discord_moderation import is_discord_id
    import sqlite3
    import webapp_config

    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"success": False, "error": "Type at least 2 characters"}), 400

    resolve = _resolver()
    found: dict[str, str] = {}
    if DISCORD_ID.match(q):
        found[q] = resolve(q)
    for row in UserProfileRepository().search_users(q, limit=15):
        found.setdefault(str(row["user_id"]), row["display_name"])
    for row in EloRepository().search_players_by_name(q, limit=15):
        found.setdefault(str(row["user_id"]), row["display_name"])
    # Players who were reported but never played a rated game
    ql = q.lower()
    for r in _all_reports():
        name = resolve(r["reported_id"], r["reported_name"])
        if ql in str(name).lower():
            found.setdefault(str(r["reported_id"]), name)
        if len(found) >= 25:
            break

    ids = list(found)[:25]
    against: dict[str, int] = {}
    filed: dict[str, int] = {}
    for r in _all_reports():
        against[str(r["reported_id"])] = against.get(str(r["reported_id"]), 0) + 1
        filed[str(r["reporter_id"])] = filed.get(str(r["reporter_id"]), 0) + 1

    blocked_by: dict[str, int] = {}
    if ids:
        BlockedUsersRepository(db_path=webapp_config.MATCH_RECORDS_DB_PATH)
        conn = sqlite3.connect(str(webapp_config.MATCH_RECORDS_DB_PATH))
        try:
            marks = ",".join("?" * len(ids))
            for uid, n in conn.execute(
                f"SELECT blocked_user_id, COUNT(*) FROM blocked_users WHERE blocked_user_id IN ({marks}) "
                "GROUP BY blocked_user_id", ids,
            ):
                blocked_by[str(uid)] = n
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()

    repo = ModerationRepository()
    latest = repo.latest_by_target(ids)
    status = repo.status_by_target(ids)
    players = [
        {
            "user_id": uid,
            "name": found[uid],
            "reports_against": against.get(uid, 0),
            "reports_filed": filed.get(uid, 0),
            "blocked_by": blocked_by.get(uid, 0),
            "can_moderate": is_discord_id(uid),
            "moderation": latest.get(uid),
            "status": status.get(uid),
        }
        for uid in ids
    ]
    players.sort(key=lambda p: (-p["reports_against"], str(p["name"]).lower()))
    return jsonify({"success": True, "players": players}), 200


@mod_tools_bp.route("/mod/actions", methods=["GET"])
@require_moderator
def mod_recent_actions():
    """Recent timeouts, bans and pairing blocks (and lifts), newest first."""
    from repositories.moderation_repo import ModerationRepository

    limit = min(max(1, request.args.get("limit", 50, type=int)), 200)
    offset = max(0, request.args.get("offset", 0, type=int))
    rows, total = ModerationRepository().recent_actions(limit=limit, offset=offset)
    return jsonify({"success": True, "entries": rows, "total": total}), 200


@mod_tools_bp.route("/mod/action", methods=["POST"])
@require_moderator
def mod_action():
    """Time out, ban or pairing-block a player, or lift one. Same body as
    POST /api/admin/moderation (see services/moderation_actions.py)."""
    from services.moderation_actions import run_moderation

    data = request.get_json(silent=True) or {}
    by_id, by_name = _me()
    user_id = str(data.get("user_id") or "").strip()
    if user_id and str(user_id) == str(by_id) and data.get("action") in ("timeout", "ban", "pairing_block"):
        return jsonify({"success": False, "error": "You can't moderate yourself."}), 400
    body, status = run_moderation(
        data, by_id=by_id, by_name=by_name,
        target_name=_resolver()(user_id) if user_id else "", role=_role(),
    )
    return jsonify(body), status


# ── one player's mod page ────────────────────────────────────────────

PLAYER_ID = re.compile(r"^[\w-]{1,64}$")


@mod_tools_bp.route("/mod/players/<user_id>/record", methods=["GET"])
@require_moderator
def mod_player_record(user_id):
    """Everything on record for one player: reports, blocks, actions, mod
    notes, group chats (with saved transcripts) and repeat-offender flags.

    Moderation data only: no profile, deck or match data.
    """
    from repositories.mod_record_repo import ModRecordRepository
    from repositories.moderation_repo import ModerationRepository
    from services.discord_moderation import is_discord_id

    if not PLAYER_ID.match(user_id or ""):
        return jsonify({"success": False, "error": "Unknown player"}), 404
    resolve = _resolver()
    record = ModRecordRepository().record(user_id)
    for r in record["reports"]:
        r["reporter_name"] = resolve(str(r["reporter_id"]), r.get("reporter_name"))
    for b in record["blocks"]:
        b["blocker_name"] = resolve(str(b["user_id"]))
    fallback = record["reports"][0].get("reported_name") if record["reports"] else None
    repo = ModerationRepository()
    return jsonify({
        "success": True,
        "player": {
            "user_id": user_id,
            "name": resolve(user_id, fallback),
            "can_moderate": is_discord_id(user_id),
            "moderation": repo.latest_by_target([user_id]).get(user_id),
            "status": repo.status_by_target([user_id]).get(user_id),
        },
        **record,
    }), 200


@mod_tools_bp.route("/mod/players/<user_id>/notes", methods=["POST"])
@require_moderator
def mod_add_note(user_id):
    """Add a private mod note to a player (the bot's Note button writes the same table)."""
    from repositories.mod_record_repo import ModRecordRepository

    if not PLAYER_ID.match(user_id or ""):
        return jsonify({"success": False, "error": "Unknown player"}), 404
    note = str((request.get_json(silent=True) or {}).get("note") or "").strip()
    if len(note) < 3:
        return jsonify({"success": False, "error": "Write at least a few words"}), 400
    if len(note) > 1000:
        return jsonify({"success": False, "error": "Keep notes under 1000 characters"}), 400
    by_id, by_name = _me()
    label = by_name if _role() == "admin" else f"{by_name} (moderator)"
    note_id = ModRecordRepository().add_note(user_id, note, by_id, label)
    return jsonify({"success": True, "id": note_id}), 201


@mod_tools_bp.route("/mod/players/<user_id>/send-summary", methods=["POST"])
@require_moderator
def mod_send_summary(user_id):
    """Ask the bot to post this player's summary, with all the mod buttons,
    in the Discord mod channel (it checks every 30 seconds)."""
    from repositories.mod_record_repo import ModRequestsRepository

    if not PLAYER_ID.match(user_id or ""):
        return jsonify({"success": False, "error": "Unknown player"}), 404
    by_id, by_name = _me()
    ModRequestsRepository().request_summary(user_id, by_id, by_name)
    return jsonify({"success": True}), 201


@mod_tools_bp.route("/mod/players/<user_id>/matches", methods=["GET"])
@require_admin
def mod_player_matches(user_id):
    """The player's matches this season, for flipping results (admins only)."""
    from repositories.mod_record_repo import ModRequestsRepository
    from utils.match_tables import live_matches

    if not PLAYER_ID.match(user_id or ""):
        return jsonify({"success": False, "error": "Unknown player"}), 404
    repo = ModRequestsRepository()
    flips = repo.flips_for(user_id)
    latest = {}
    for f in flips:  # newest first: keep each match's latest flip
        latest.setdefault(f["match_id"], f)
    matches = []
    for m in repo.player_matches(user_id, live_matches()):
        won = str(m["winner_id"]) == str(user_id)
        matches.append({
            "id": m["id"],
            "timestamp": m["timestamp"],
            "won": won,
            "opponent_id": str(m["losser_id"] if won else m["winner_id"]),
            "opponent_name": m["losser_display_name"] if won else m["winner_display_name"],
            "match_type": m.get("match_type"),
            "source": m.get("source"),
            "avatar": m.get("winner_avatar") if won else m.get("loser_avatar"),
            "flip": latest.get(m["id"]),
        })
    return jsonify({"success": True, "matches": matches, "flips": flips}), 200


@mod_tools_bp.route("/mod/players/<user_id>/flip-matches", methods=["POST"])
@require_admin
def mod_flip_matches(user_id):
    """Flip the result of some of the player's matches (admins only).

    The bot does it (same as !correct_match): winner and loser swap and every
    later rated game of both players is recalculated. Body: match_ids, confirm.
    """
    from repositories.mod_record_repo import ModRequestsRepository
    from utils.match_tables import live_matches

    if not PLAYER_ID.match(user_id or ""):
        return jsonify({"success": False, "error": "Unknown player"}), 404
    data = request.get_json(silent=True) or {}
    if data.get("confirm") is not True:
        return jsonify({"success": False, "error": "Confirmation required"}), 400
    try:
        wanted = {int(m) for m in data.get("match_ids") or []}
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Bad match list"}), 400
    if not wanted or len(wanted) > 100:
        return jsonify({"success": False, "error": "Pick between 1 and 100 matches"}), 400
    repo = ModRequestsRepository()
    theirs = {m["id"] for m in repo.player_matches(user_id, live_matches(), limit=100000)}
    if not wanted <= theirs:
        return jsonify({"success": False, "error": "Some of those matches aren't this player's"}), 400
    by_id, by_name = _me()
    added = repo.request_flips(user_id, sorted(wanted), by_id, by_name)
    try:
        from repositories.audit import AuditRepository
        AuditRepository().log_action(
            by_id, by_name, "web_flip_matches", target_id=str(user_id),
            new_state={"match_ids": sorted(wanted)},
            details=f"Asked the bot to flip {added} match result(s) from Mod Tools",
        )
    except Exception as e:
        logger.warning(f"Match flip request not audit-logged: {e}")
    return jsonify({"success": True, "queued": added}), 201


# ── moderator list (admins only) ─────────────────────────────────────

@mod_tools_bp.route("/mod/moderators", methods=["GET"])
@require_admin
def list_moderators():
    from repositories.moderation_repo import ModeratorsRepository

    resolve = _resolver()
    mods = ModeratorsRepository().list()
    for m in mods:
        m["name"] = resolve(m["discord_user_id"], m.get("display_name"))
    return jsonify({"success": True, "moderators": mods}), 200


@mod_tools_bp.route("/mod/moderators", methods=["POST"])
@require_admin
def add_moderator():
    """Body: {"discord_id": "<17-19 digit Discord ID>"}"""
    from repositories.audit import AuditRepository
    from repositories.moderation_repo import ModeratorsRepository

    data = request.get_json(silent=True) or {}
    uid = str(data.get("discord_id") or "").strip()
    if not DISCORD_ID.match(uid):
        return jsonify({"success": False, "error": "That doesn't look like a Discord ID (17-19 digits)."}), 400
    name = _resolver()(uid)
    by_id, by_name = _me()
    if not ModeratorsRepository().add(uid, display_name=None if name == uid else name,
                                      by_id=by_id, by_name=by_name):
        return jsonify({"success": False, "error": "They're already a moderator."}), 400
    AuditRepository().log_action(by_id, by_name, "add_moderator", target_id=uid, target_name=name)
    return jsonify({"success": True, "moderator": {"discord_user_id": uid, "name": name}}), 200


@mod_tools_bp.route("/mod/moderators/<discord_id>", methods=["DELETE"])
@require_admin
def remove_moderator(discord_id):
    from repositories.audit import AuditRepository
    from repositories.moderation_repo import ModeratorsRepository

    if not ModeratorsRepository().remove(discord_id):
        return jsonify({"success": False, "error": "Not a moderator."}), 404
    by_id, by_name = _me()
    AuditRepository().log_action(by_id, by_name, "remove_moderator", target_id=discord_id,
                                 target_name=_resolver()(discord_id))
    return jsonify({"success": True}), 200
