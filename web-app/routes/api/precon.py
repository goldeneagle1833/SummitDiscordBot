"""Precon ladder (Lavamancer vs Frostmage) standings for the website.

Games come in through the Discord bot (its precon queue, Play Sorcery Online
results relayed to it, and admin reports) and are saved in match_records.db;
this only reads them. Nothing here calls Play Sorcery Online.
"""

import logging
import sqlite3

from flask import Blueprint, jsonify, request, session

import webapp_config
from repositories.audit import AuditRepository
from services import precon_ladder
from services.replays import viewable_replays
from utils.auth import require_admin

logger = logging.getLogger(__name__)

precon_bp = Blueprint("precon", __name__)

_SEASON_FIELDS = ("season_id", "name", "starts_at", "ends_at", "ended_at", "is_open", "last_day")


def _public_season(season):
    if not season:
        return None
    out = {key: season.get(key) for key in _SEASON_FIELDS}
    # Same times with the server's UTC offset, for browsers in other time zones
    for key in ("starts_at", "ends_at", "ended_at", "last_day"):
        out[f"{key}_iso"] = precon_ladder.with_offset(season.get(key))
    return out


@precon_bp.route("/precon/standings")
def get_precon_standings():
    """Standings for one precon season (the current or latest one by default).

    Query: ``season_id`` (optional).
    """
    try:
        conn = sqlite3.connect(str(webapp_config.MATCH_RECORDS_DB_PATH), timeout=10)
        try:
            seasons = precon_ladder.list_seasons(conn)
            season = None
            season_id = request.args.get("season_id", type=int)
            if season_id is not None:
                season = next((s for s in seasons if s["season_id"] == season_id), None)
                if season is None:
                    return jsonify({"error": "Season not found"}), 404
            else:
                season = precon_ladder.current_or_latest_season(conn)
            body = {
                "season": _public_season(season),
                "seasons": [_public_season(s) for s in seasons],
                "precons": precon_ladder.precon_choices(),
                "min_ranked_games": precon_ladder.min_ranked_games(conn),
                "standings": [],
                "stats": None,
                "recent": [],
            }
            if season:
                body["standings"] = precon_ladder.standings(conn, season["season_id"])
                body["stats"] = precon_ladder.season_stats(conn, season["season_id"])
                body["recent"] = precon_ladder.recent_matches(conn, season["season_id"], limit=10)
            return jsonify(body)
        finally:
            conn.close()
    except sqlite3.Error as e:
        logger.error("Could not read precon standings: %s", e, exc_info=True)
        return jsonify({"error": "Could not load the precon ladder"}), 500


@precon_bp.route("/precon/players/<player_id>")
def get_precon_player(player_id):
    """A player's LM / FM ladder standings and latest precon games (public, like the ladder)."""
    if not str(player_id).isdigit():
        return jsonify({"seasons": [], "games": [], "min_ranked_games": precon_ladder.MIN_RANKED_GAMES})
    try:
        conn = sqlite3.connect(str(webapp_config.MATCH_RECORDS_DB_PATH), timeout=10)
        try:
            summary = precon_ladder.player_summary(conn, int(player_id))
        finally:
            conn.close()
    except sqlite3.Error as e:
        logger.error("Could not read precon games for %s: %s", player_id, e, exc_info=True)
        return jsonify({"error": "Could not load precon games"}), 500
    # Same rule as every other replay link: the two players and admins, or
    # everyone when both players made their replays public.
    games = summary["games"]
    allowed = viewable_replays([(g["winner_id"], g["loser_id"]) for g in games]) if games else []
    for game, ok in zip(games, allowed):
        if not ok:
            game["replay_url"] = None
    summary["seasons"] = [
        {**entry, "season": _public_season(entry["season"])} for entry in summary["seasons"]
    ]
    return jsonify(summary)


# --- Admin: run the ladder from the Admin page --------------------------------
#
# Everything the precon bot commands do, without remembering them. The bot reads
# the same tables; after a change we ask it (over its loopback API) to drop its
# one-minute cache and update the LFG status, so the queue button shows or hides
# right away. If the bot can't be reached the change still lands within a minute.


def _connect():
    return sqlite3.connect(str(webapp_config.MATCH_RECORDS_DB_PATH), timeout=10)


def _admin():
    return session.get("user_id", 0), session.get("username", "API/localhost")


def _log(action, target_id=None, target_name=None, details=None):
    admin_id, admin_name = _admin()
    try:
        AuditRepository().log_action(
            admin_id, admin_name, action, target_id=target_id,
            target_name=target_name, details=details,
        )
    except Exception as e:  # noqa: BLE001 - never block the change on the log
        logger.warning("Could not write audit entry for %s: %s", action, e)


def _tell_bot():
    """Best effort: True when the bot picked the change up now."""
    from routes.api.matchmaking import relay_to_bot

    body, status = relay_to_bot("POST", "/precon-refresh", {}, unavailable_body={}, timeout=5)
    return status == 200 and bool(body.get("refreshed"))


def _admin_state(conn, bot_refreshed=None):
    seasons = precon_ladder.list_seasons(conn)
    current = precon_ladder.current_or_latest_season(conn)
    body = {
        "settings": precon_ladder.get_settings(conn),
        "limits": {
            name: {"min": spec[2], "max": spec[3]}
            for name, spec in precon_ladder.SETTINGS.items() if spec[1] is int
        },
        "seasons": [],
        "current_season_id": current["season_id"] if current else None,
        "open_season_id": next((s["season_id"] for s in seasons if s["is_open"]), None),
        "recent": [],
    }
    for season in seasons:
        stats = precon_ladder.season_stats(conn, season["season_id"])
        body["seasons"].append({
            **_public_season(season),
            "games": stats["games"],
            "players": stats["players"],
            "final_posted": bool(season.get("final_posted_at")),
        })
    if current:
        body["recent"] = precon_ladder.recent_matches(conn, current["season_id"], limit=25)
    if bot_refreshed is not None:
        body["bot_refreshed"] = bot_refreshed
    return body


def _body():
    return request.get_json(silent=True) or {}


def _admin_call(work, action, refresh=True):
    """Run one admin change: 400 with the reason on bad input, else the new state."""
    try:
        conn = _connect()
        try:
            result = work(conn)
            if isinstance(result, tuple):
                result, log_target = result
            else:
                log_target = {}
            _log(action, **log_target)
            refreshed = _tell_bot() if refresh else None
            state = _admin_state(conn, refreshed)
            if result is not None:
                state["result"] = result
            return jsonify(state)
        finally:
            conn.close()
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except sqlite3.Error as e:
        logger.error("Precon admin %s failed: %s", action, e, exc_info=True)
        return jsonify({"error": "Could not save the change"}), 500


@precon_bp.route("/precon/admin", methods=["GET"])
@require_admin
def precon_admin_state():
    """Settings, every season with its game count, and the latest games."""
    try:
        conn = _connect()
        try:
            return jsonify(_admin_state(conn))
        finally:
            conn.close()
    except sqlite3.Error as e:
        logger.error("Could not read precon admin state: %s", e, exc_info=True)
        return jsonify({"error": "Could not load the precon ladder"}), 500


@precon_bp.route("/precon/admin/settings", methods=["PUT"])
@require_admin
def precon_admin_settings():
    """Change the queue switch or the rules. Body: any of the setting names."""
    changes = {k: v for k, v in _body().items() if k in precon_ladder.SETTINGS}
    if not changes:
        return jsonify({"error": "Nothing to change"}), 400

    def work(conn):
        precon_ladder.update_settings(conn, changes, updated_by=_admin()[0])
        return None, {"details": ", ".join(f"{k}={v}" for k, v in changes.items())}

    return _admin_call(work, "precon_settings")


@precon_bp.route("/precon/admin/seasons", methods=["POST"])
@require_admin
def precon_admin_start_season():
    """Start a ladder. Body: name, days (optional), starts_at (optional ISO),
    open_queue (optional bool: also switch the queue on)."""
    data = _body()

    def work(conn):
        settings = precon_ladder.get_settings(conn)
        days = data.get("days") or settings["season_days"]
        try:
            days = int(days)
        except (TypeError, ValueError):
            raise ValueError("Length must be a number of days") from None
        starts_at = data.get("starts_at")
        start = precon_ladder.parse_when(starts_at, "Start") if starts_at else None
        season = precon_ladder.start_season(
            conn, data.get("name"), created_by=_admin()[0], days=days, starts_at=start,
        )
        if data.get("open_queue"):
            precon_ladder.update_settings(conn, {"queue_enabled": True}, updated_by=_admin()[0])
        return _public_season(season), {
            "target_id": season["season_id"], "target_name": season["name"],
            "details": f"{days} days from {season['starts_at']}",
        }

    return _admin_call(work, "precon_season_start")


@precon_bp.route("/precon/admin/seasons/<int:season_id>", methods=["PUT"])
@require_admin
def precon_admin_update_season(season_id):
    """Rename a ladder or move its start or end. Body: name, starts_at, ends_at."""
    data = _body()

    def work(conn):
        season = precon_ladder.update_season(
            conn, season_id, name=data.get("name"),
            starts_at=data.get("starts_at"), ends_at=data.get("ends_at"),
        )
        return _public_season(season), {
            "target_id": season_id, "target_name": season["name"],
            "details": f"{season['starts_at']} to {season['ends_at']}",
        }

    return _admin_call(work, "precon_season_edit")


@precon_bp.route("/precon/admin/seasons/end", methods=["POST"])
@require_admin
def precon_admin_end_season():
    """End the running ladder now. The bot posts the final standings."""
    def work(conn):
        season = precon_ladder.end_season(conn)
        if not season:
            raise ValueError("No precon ladder is running")
        return _public_season(season), {"target_id": season["season_id"], "target_name": season["name"]}

    return _admin_call(work, "precon_season_end")


@precon_bp.route("/precon/admin/matches", methods=["POST"])
@require_admin
def precon_admin_report_match():
    """Record a game by hand. Body: winner_id, winner_name, winner_precon,
    loser_id, loser_name, loser_precon (precon as lavamancer/frostmage or LM/FM)."""
    data = _body()

    def work(conn):
        w_key = precon_ladder.normalize_precon(data.get("winner_precon"))
        l_key = precon_ladder.normalize_precon(data.get("loser_precon"))
        winner_id, loser_id = str(data.get("winner_id") or ""), str(data.get("loser_id") or "")
        if not winner_id.isdigit() or not loser_id.isdigit():
            raise ValueError("Pick both players")
        if winner_id == loser_id:
            raise ValueError("The winner and loser must be different players")
        if not w_key or not l_key:
            raise ValueError("Pick each player's precon (Lavamancer or Frostmage)")
        admin_id, admin_name = _admin()
        result = precon_ladder.record_match(
            conn,
            winner_id=int(winner_id), loser_id=int(loser_id),
            winner_name=(data.get("winner_name") or winner_id)[:100],
            loser_name=(data.get("loser_name") or loser_id)[:100],
            winner_precon=w_key, loser_precon=l_key,
            reporter_id=int(admin_id) if str(admin_id).isdigit() else None,
            source="admin", match_comment=f"Reported by admin {admin_name} on the website",
        )
        return result, {
            "target_id": result["match_id"],
            "details": f"{data.get('winner_name')} ({w_key}) beat {data.get('loser_name')} ({l_key})",
        }

    return _admin_call(work, "precon_match_report")


@precon_bp.route("/precon/admin/matches/<int:match_id>", methods=["DELETE"])
@require_admin
def precon_admin_remove_match(match_id):
    """Take a game off the ladder and re-rate its season."""
    def work(conn):
        game = precon_ladder.remove_match(conn, match_id)
        if not game:
            raise ValueError(f"No precon match #{match_id} to remove (or it was already removed)")
        return {"match_id": match_id}, {
            "target_id": match_id,
            "details": f"{game['winner_display_name']} beat {game['loser_display_name']}",
        }

    return _admin_call(work, "precon_match_remove", refresh=False)
