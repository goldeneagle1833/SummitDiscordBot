"""Admin API routes for player and match management."""

import logging
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

from flask import Blueprint, jsonify, request, session

from services.admin import AdminService
from repositories.audit import AuditRepository
from utils.auth import require_admin
from webapp_config import ELO_DB_PATH, MATCH_RECORDS_DB_PATH, BOT_DIR

logger = logging.getLogger(__name__)


def _import_bot_database_utils():
    """Import database utilities from discord-bot at runtime to avoid import conflicts."""
    if str(BOT_DIR) not in sys.path:
        sys.path.insert(0, str(BOT_DIR))

    # Import at runtime to avoid conflicts
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "bot_database",
        BOT_DIR / "utils" / "database.py"
    )
    bot_db = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bot_db)
    return bot_db

admin_bp = Blueprint("admin", __name__)


def _get_admin_info():
    """Get the current admin's ID and name from the session."""
    admin_id = session.get("user_id", 0)
    admin_name = session.get("username", "API/localhost")
    return admin_id, admin_name


@admin_bp.route("/admin/remove-player/<path:user_id>", methods=["DELETE"])
@require_admin
def remove_player(user_id):
    """Remove a player from standings (admin only). Supports both numeric and google_ IDs."""
    service = AdminService()
    # Capture previous state before removal
    current_elo = service._elo_repo.get_user_elo(user_id)
    paper_elo = service._elo_repo.get_user_paper_elo(str(user_id))
    result = service.remove_player(user_id)
    if result.get("success"):
        admin_id, admin_name = _get_admin_info()
        audit = AuditRepository()
        audit.log_action(
            admin_id, admin_name, "web_remove_player",
            target_id=str(user_id),
            previous_state={"elo": current_elo, "paper_elo": paper_elo},
            new_state={"result": "player removed from standings"},
            details=f"Removed player {user_id} from standings (ELO was {current_elo}, paper was {paper_elo})",
        )
    status = 200 if result.get("success") else 404
    return jsonify(result), status


@admin_bp.route("/admin/remove-match/<path:match_id>", methods=["DELETE"])
@require_admin
def remove_match(match_id):
    """Remove a match record and reverse ELO changes (admin only).

    Handles both bot matches (numeric IDs) and web matches (web_N IDs).
    """
    service = AdminService()

    # Capture match details before removal
    is_web = str(match_id).startswith("web_")
    if is_web:
        match = service._match_repo.get_web_match_full_details(match_id)
    else:
        try:
            match = service._match_repo.get_match_full_details(int(match_id))
        except (ValueError, TypeError):
            match = None

    result = service.remove_match(match_id)
    if result.get("success") and match:
        admin_id, admin_name = _get_admin_info()
        audit = AuditRepository()
        match_type = "web" if is_web else "bot"
        audit.log_action(
            admin_id, admin_name, f"web_remove_{match_type}_match",
            target_id=str(match_id),
            previous_state={
                "winner_id": str(match.get("winner_id")),
                "winner_name": match.get("winner_name"),
                "loser_id": str(match.get("loser_id")),
                "loser_name": match.get("loser_name"),
            },
            new_state={"result": f"{match_type} match deleted, ELO reversed"},
            details=f"Removed {match_type} match {match_id}: {match.get('winner_name')} vs {match.get('loser_name')}",
        )
    status = 200 if result.get("success") else 404
    return jsonify(result), status


@admin_bp.route("/admin/reset-elo/<path:user_id>", methods=["POST"])
@require_admin
def reset_elo(user_id):
    """Reset a player's ELO to a specified value (admin only). Supports both numeric and google_ IDs."""
    data = request.get_json(silent=True)
    new_elo = 1500
    source = "both"
    if data:
        if data.get("new_elo") is not None:
            try:
                new_elo = int(data["new_elo"])
            except (ValueError, TypeError):
                return jsonify({"success": False, "error": "new_elo must be a number"}), 400
            if new_elo < 0 or new_elo > 5000:
                return jsonify({"success": False, "error": "ELO must be between 0 and 5000"}), 400
        if data.get("source") in ("bot", "paper", "both"):
            source = data["source"]

    service = AdminService()
    current_bot_elo = service._elo_repo.get_user_elo(user_id)
    current_paper_elo = service._elo_repo.get_user_paper_elo(str(user_id))
    result = service.reset_player_elo(user_id, new_elo, source)
    if result.get("success"):
        admin_id, admin_name = _get_admin_info()
        audit = AuditRepository()
        audit.log_action(
            admin_id, admin_name, "web_reset_elo",
            target_id=str(user_id),
            previous_state={"elo": current_bot_elo, "paper_elo": current_paper_elo},
            new_state={"elo": new_elo, "source": source},
            details=f"Reset ELO for player {user_id} ({source}): bot {current_bot_elo} -> {new_elo}, paper {current_paper_elo} -> {new_elo}",
        )
    status = 200 if result.get("success") else 404
    return jsonify(result), status


@admin_bp.route("/admin/rename-player/<path:user_id>", methods=["POST"])
@require_admin
def rename_player(user_id):
    """Rename a player's display name (admin only). Supports both numeric and google_ IDs."""
    data = request.get_json(silent=True)
    if not data or not data.get("new_name"):
        return jsonify({"success": False, "error": "new_name is required"}), 400

    new_name = str(data["new_name"]).strip()
    if not new_name or len(new_name) > 100:
        return jsonify({"success": False, "error": "Invalid name (1-100 characters)"}), 400

    service = AdminService()
    result = service.rename_player(user_id, new_name)
    if result.get("success"):
        admin_id, admin_name = _get_admin_info()
        audit = AuditRepository()
        audit.log_action(
            admin_id, admin_name, "web_rename_player",
            target_id=str(user_id),
            new_state={"new_name": new_name},
            details=f"Renamed player {user_id} to '{new_name}'",
        )
    status = 200 if result.get("success") else 404
    return jsonify(result), status


@admin_bp.route("/admin/reset-all-elo", methods=["POST"])
@require_admin
def reset_all_elo():
    """DANGER: Completely reset ALL ELO ratings and match history (admin only)."""
    admin_id, admin_name = _get_admin_info()

    try:
        # Capture state before reset
        conn_elo = sqlite3.connect(str(ELO_DB_PATH))
        cur_elo = conn_elo.cursor()
        cur_elo.execute("SELECT COUNT(*) FROM overall_standings")
        player_count = cur_elo.fetchone()[0]
        conn_elo.close()

        conn_match = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur_match = conn_match.cursor()
        cur_match.execute("SELECT COUNT(*) FROM match_records")
        match_count = cur_match.fetchone()[0]
        conn_match.close()

        # Perform reset
        conn_elo = sqlite3.connect(str(ELO_DB_PATH))
        cur_elo = conn_elo.cursor()
        cur_elo.execute("DELETE FROM overall_standings")
        cur_elo.execute("DELETE FROM paper_standings")
        cur_elo.execute("DELETE FROM event_standings_archive")
        cur_elo.execute("DELETE FROM events")
        conn_elo.commit()
        conn_elo.close()

        conn_match = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur_match = conn_match.cursor()
        cur_match.execute("DELETE FROM match_records")
        cur_match.execute("DELETE FROM pairings")
        cur_match.execute("DELETE FROM match_records_archive")
        cur_match.execute("DELETE FROM match_reports_web")
        conn_match.commit()
        conn_match.close()

        # Log action
        audit = AuditRepository()
        audit.log_action(
            admin_id, admin_name, "web_reset_all_elo",
            previous_state={"players": player_count, "matches": match_count},
            new_state={"players": 0, "matches": 0},
            details=f"Full database reset: {player_count} players and {match_count} matches deleted",
        )

        return jsonify({
            "success": True,
            "message": f"All data reset. Deleted {player_count} players and {match_count} matches."
        }), 200

    except Exception as e:
        logger.error(f"Failed to reset database: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/admin/game-activity", methods=["GET"])
@require_admin
def game_activity():
    """Get game statistics for the last X hours (admin only)."""
    hours = request.args.get("hours", 24, type=int)
    if hours < 1 or hours > 8760:  # Max 1 year
        return jsonify({"success": False, "error": "Hours must be between 1 and 8760"}), 400

    try:
        cutoff = datetime.now() - timedelta(hours=hours)
        cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")

        conn_match = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur_match = conn_match.cursor()

        # Bot matches
        cur_match.execute(
            "SELECT COUNT(*) FROM match_records WHERE timestamp >= ?",
            (cutoff_str,)
        )
        bot_matches = cur_match.fetchone()[0]

        # Web matches
        cur_match.execute(
            "SELECT COUNT(*) FROM match_reports_web WHERE timestamp >= ?",
            (cutoff_str,)
        )
        web_matches = cur_match.fetchone()[0]

        # Get unique players (note: column is "losser_id" due to typo in schema)
        cur_match.execute(
            """
            SELECT COUNT(DISTINCT player_id) FROM (
                SELECT winner_id AS player_id FROM match_records WHERE timestamp >= ?
                UNION
                SELECT losser_id AS player_id FROM match_records WHERE timestamp >= ?
            )
            """,
            (cutoff_str, cutoff_str)
        )
        active_players = cur_match.fetchone()[0]

        conn_match.close()

        total_matches = bot_matches + web_matches

        return jsonify({
            "success": True,
            "hours": hours,
            "total_matches": total_matches,
            "bot_matches": bot_matches,
            "web_matches": web_matches,
            "active_players": active_players,
            "start_time": cutoff_str,
            "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }), 200

    except Exception as e:
        logger.error(f"Failed to get game activity: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/admin/dashboard-stats", methods=["GET"])
@require_admin
def dashboard_stats():
    """Get time-series stats for the admin dashboard (unique players, games over time)."""
    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()

        # Detect which optional tables exist
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in cur.fetchall()}
        has_archive = "match_records_archive" in existing_tables
        has_web = "match_reports_web" in existing_tables

        # Build UNION fragments for "all online matches" (current + archive)
        # and "all matches" (online + web). Archive uses same schema as match_records.
        online_tables = ["match_records"]
        if has_archive:
            online_tables.append("match_records_archive")

        def _online_union(select_tpl):
            """Build a UNION ALL across online match tables."""
            return " UNION ALL ".join(select_tpl.format(t=t) for t in online_tables)

        def _all_union(select_tpl, web_select_tpl=None):
            """Build a UNION across all match tables (for distinct counts)."""
            parts = [select_tpl.format(t=t) for t in online_tables]
            if has_web:
                parts.append((web_select_tpl or select_tpl).format(t="match_reports_web"))
            return " UNION ".join(parts)

        # --- Games per week (online = match_records + archive) ---
        cur.execute(f"""
            SELECT week, SUM(games) FROM (
                {_online_union(
                    "SELECT strftime('%Y-%W', timestamp) as week, COUNT(*) as games "
                    "FROM {t} WHERE timestamp IS NOT NULL GROUP BY week"
                )}
            ) GROUP BY week ORDER BY week
        """)
        bot_weekly = {row[0]: row[1] for row in cur.fetchall()}

        # --- Games per week (web) ---
        web_weekly = {}
        if has_web:
            cur.execute("""
                SELECT strftime('%Y-%W', timestamp) as week, COUNT(*) as games
                FROM match_reports_web WHERE timestamp IS NOT NULL
                GROUP BY week ORDER BY week
            """)
            web_weekly = {row[0]: row[1] for row in cur.fetchall()}

        # --- Combined unique players per week ---
        cur.execute(f"""
            SELECT week, COUNT(DISTINCT player_id) as players FROM (
                {_all_union(
                    "SELECT strftime('%Y-%W', timestamp) as week, winner_id as player_id "
                    "FROM {t} WHERE timestamp IS NOT NULL"
                )}
                UNION
                {_all_union(
                    "SELECT strftime('%Y-%W', timestamp) as week, losser_id as player_id "
                    "FROM {t} WHERE timestamp IS NOT NULL"
                )}
            ) GROUP BY week ORDER BY week
        """)
        combined_players_weekly = {row[0]: row[1] for row in cur.fetchall()}

        # --- Summary: total matches ---
        cur.execute(f"""
            SELECT SUM(c) FROM (
                {_online_union("SELECT COUNT(*) as c FROM {t}")}
            )
        """)
        total_bot_matches = cur.fetchone()[0] or 0

        total_web_matches = 0
        if has_web:
            cur.execute("SELECT COUNT(*) FROM match_reports_web")
            total_web_matches = cur.fetchone()[0]

        # --- Summary: total unique players ---
        cur.execute(f"""
            SELECT COUNT(DISTINCT player_id) FROM (
                {_all_union("SELECT winner_id as player_id FROM {t}")}
                UNION
                {_all_union("SELECT losser_id as player_id FROM {t}")}
            )
        """)
        total_players = cur.fetchone()[0]

        # --- Summary: avg games per week (last 12 weeks) ---
        cur.execute(f"""
            SELECT SUM(c) FROM (
                {_online_union(
                    "SELECT COUNT(*) as c FROM {t} WHERE timestamp >= date('now', '-84 days')"
                )}
            )
        """)
        recent_bot = cur.fetchone()[0] or 0
        recent_web = 0
        if has_web:
            cur.execute("""
                SELECT COUNT(*) FROM match_reports_web
                WHERE timestamp >= date('now', '-84 days')
            """)
            recent_web = cur.fetchone()[0]
        avg_weekly_games = round((recent_bot + recent_web) / 12, 1)

        # --- Peak activity hours (day_of_week x hour heatmap) ---
        # strftime %w = 0(Sun)..6(Sat), %H = 00..23
        cur.execute(f"""
            SELECT day_of_week, hour, SUM(cnt) as total FROM (
                {_online_union(
                    "SELECT CAST(strftime('%w', timestamp) AS INTEGER) as day_of_week, "
                    "CAST(strftime('%H', timestamp) AS INTEGER) as hour, "
                    "COUNT(*) as cnt FROM {t} WHERE timestamp IS NOT NULL "
                    "GROUP BY day_of_week, hour"
                )}
                {"UNION ALL "
                 "SELECT CAST(strftime('%w', timestamp) AS INTEGER) as day_of_week, "
                 "CAST(strftime('%H', timestamp) AS INTEGER) as hour, "
                 "COUNT(*) as cnt FROM match_reports_web WHERE timestamp IS NOT NULL "
                 "GROUP BY day_of_week, hour"
                 if has_web else ""}
            ) GROUP BY day_of_week, hour
        """)
        # Build 7x24 grid initialized to 0
        heatmap = [[0] * 24 for _ in range(7)]
        for row in cur.fetchall():
            dow, hour, cnt = int(row[0]), int(row[1]), int(row[2])
            heatmap[dow][hour] = cnt

        # --- Top player dominance (W-L records, win rate, streaks) ---
        # Get per-player wins
        cur.execute(f"""
            SELECT player_id, display_name, SUM(wins) as total_wins FROM (
                {_online_union(
                    "SELECT winner_id as player_id, "
                    "winner_display_name as display_name, "
                    "1 as wins FROM {t}"
                )}
            ) GROUP BY player_id ORDER BY total_wins DESC
        """)
        win_rows = {r[0]: {"name": r[1] or str(r[0]), "wins": r[2]} for r in cur.fetchall()}

        # Get per-player losses
        cur.execute(f"""
            SELECT player_id, SUM(losses) as total_losses FROM (
                {_online_union(
                    "SELECT losser_id as player_id, 1 as losses FROM {t}"
                )}
            ) GROUP BY player_id
        """)
        for r in cur.fetchall():
            pid = r[0]
            if pid in win_rows:
                win_rows[pid]["losses"] = r[1]
            else:
                # Players with only losses (0 wins) - get display name
                win_rows[pid] = {"name": str(pid), "wins": 0, "losses": r[1]}

        # Get display names for loss-only players
        cur.execute(f"""
            SELECT player_id, display_name FROM (
                {_online_union(
                    "SELECT losser_id as player_id, "
                    "losser_display_name as display_name FROM {t}"
                )}
            ) GROUP BY player_id
        """)
        for r in cur.fetchall():
            if r[0] in win_rows and win_rows[r[0]]["name"] == str(r[0]):
                win_rows[r[0]]["name"] = r[1] or str(r[0])

        # Calculate W-L stats for all players
        for pid in win_rows:
            p = win_rows[pid]
            p.setdefault("losses", 0)
            p["games"] = p["wins"] + p["losses"]
            p["win_rate"] = round(p["wins"] / p["games"] * 100, 1) if p["games"] > 0 else 0

        # Sort by wins descending for dominance stats
        sorted_by_wins = sorted(win_rows.values(), key=lambda x: x["wins"], reverse=True)
        total_wins_all = sum(p["wins"] for p in sorted_by_wins)

        dominance = {}
        if sorted_by_wins and total_wins_all > 0:
            n = len(sorted_by_wins)
            top_10_pct = max(1, n // 10)
            top_25_pct = max(1, n // 4)
            top_10_wins = sum(p["wins"] for p in sorted_by_wins[:top_10_pct])
            top_25_wins = sum(p["wins"] for p in sorted_by_wins[:top_25_pct])

            # Top 10 by wins (with W-L and win rate)
            top_10_by_wins = [
                {
                    "name": p["name"], "wins": p["wins"],
                    "losses": p["losses"], "games": p["games"],
                    "win_rate": p["win_rate"],
                }
                for p in sorted_by_wins[:10]
            ]

            # Top 10 most active (by total games)
            sorted_by_games = sorted(win_rows.values(), key=lambda x: x["games"], reverse=True)
            most_active = [
                {
                    "name": p["name"], "wins": p["wins"],
                    "losses": p["losses"], "games": p["games"],
                    "win_rate": p["win_rate"],
                }
                for p in sorted_by_games[:10]
            ]

            dominance = {
                "total_players_with_wins": n,
                "top_10_pct_count": top_10_pct,
                "top_10_pct_win_share": round(top_10_wins / total_wins_all * 100, 1),
                "top_25_pct_count": top_25_pct,
                "top_25_pct_win_share": round(top_25_wins / total_wins_all * 100, 1),
                "top_10_players": top_10_by_wins,
                "most_active": most_active,
            }

        # --- Win streaks (current + longest) for top players ---
        # Fetch all matches ordered by time to compute streaks
        cur.execute(f"""
            SELECT winner_id, losser_id, timestamp FROM (
                {_online_union(
                    "SELECT winner_id, losser_id, timestamp FROM {t} "
                    "WHERE timestamp IS NOT NULL"
                )}
            ) ORDER BY timestamp ASC
        """)
        match_history = cur.fetchall()

        # Track current and best streaks per player
        streaks = {}  # pid -> {"current": int, "best": int, "type": "W"/"L"}
        for winner_id, loser_id, _ in match_history:
            # Winner
            if winner_id not in streaks:
                streaks[winner_id] = {"current": 0, "best": 0, "type": ""}
            s = streaks[winner_id]
            if s["type"] == "W":
                s["current"] += 1
            else:
                s["current"] = 1
                s["type"] = "W"
            s["best"] = max(s["best"], s["current"])

            # Loser - streak broken
            if loser_id not in streaks:
                streaks[loser_id] = {"current": 0, "best": 0, "type": ""}
            s = streaks[loser_id]
            if s["type"] == "L":
                s["current"] += 1
            else:
                s["current"] = 1
                s["type"] = "L"

        # Build streak leaderboard (longest win streaks ever)
        streak_list = []
        for pid, s in streaks.items():
            if s["best"] >= 3 and pid in win_rows:
                streak_list.append({
                    "name": win_rows[pid]["name"],
                    "best_streak": s["best"],
                    "current_streak": s["current"] if s["type"] == "W" else 0,
                })
        streak_list.sort(key=lambda x: x["best_streak"], reverse=True)
        if dominance:
            dominance["streaks"] = streak_list[:10]

        # --- Average games per player per week ---
        # Must use UNION ALL (not UNION) to count every match appearance
        all_match_union = _online_union(
            "SELECT strftime('%Y-%W', timestamp) as week, winner_id as player_id "
            "FROM {t} WHERE timestamp IS NOT NULL"
        ) + " UNION ALL " + _online_union(
            "SELECT strftime('%Y-%W', timestamp) as week, losser_id as player_id "
            "FROM {t} WHERE timestamp IS NOT NULL"
        )
        if has_web:
            all_match_union += (
                " UNION ALL "
                "SELECT strftime('%Y-%W', timestamp) as week, winner_id as player_id "
                "FROM match_reports_web WHERE timestamp IS NOT NULL"
                " UNION ALL "
                "SELECT strftime('%Y-%W', timestamp) as week, losser_id as player_id "
                "FROM match_reports_web WHERE timestamp IS NOT NULL"
            )
        cur.execute(f"""
            SELECT week,
                   COUNT(*) as total_games,
                   COUNT(DISTINCT player_id) as unique_players
            FROM ({all_match_union})
            GROUP BY week ORDER BY week
        """)
        avg_games_per_player = []
        for row in cur.fetchall():
            week, total_games, unique_players = row[0], row[1], row[2]
            # total_games counts each match twice (once per player side),
            # so actual matches = total_games / 2
            matches = total_games / 2
            avg_games_per_player.append({
                "week": week,
                "avg": round(matches / unique_players, 2) if unique_players else 0,
            })

        # --- New player acquisition (first-time players per week) ---
        # Find each player's earliest match, then count by week
        first_match_union = _all_union(
            "SELECT winner_id as player_id, MIN(timestamp) as first_ts "
            "FROM {t} WHERE timestamp IS NOT NULL GROUP BY winner_id"
        ) + " UNION " + _all_union(
            "SELECT losser_id as player_id, MIN(timestamp) as first_ts "
            "FROM {t} WHERE timestamp IS NOT NULL GROUP BY losser_id"
        )
        cur.execute(f"""
            SELECT strftime('%Y-%W', first_match) as week, COUNT(*) as new_players
            FROM (
                SELECT player_id, MIN(first_ts) as first_match
                FROM ({first_match_union})
                GROUP BY player_id
            )
            GROUP BY week ORDER BY week
        """)
        new_players_weekly = {row[0]: row[1] for row in cur.fetchall()}

        # --- Total logged-in users (from user_profiles table) ---
        total_logins = 0
        if "user_profiles" in existing_tables:
            cur.execute("SELECT COUNT(DISTINCT user_id) FROM user_profiles")
            total_logins = cur.fetchone()[0] or 0

        conn.close()

        # Merge all weeks for time-series
        all_weeks = sorted(set(
            list(bot_weekly.keys()) + list(web_weekly.keys())
        ))

        # Drop the current (partial) week so it doesn't skew charts
        current_week = datetime.now().strftime("%Y-%W")
        if all_weeks and all_weeks[-1] == current_week:
            all_weeks = all_weeks[:-1]
        if avg_games_per_player and avg_games_per_player[-1]["week"] == current_week:
            avg_games_per_player = avg_games_per_player[:-1]
        new_players_weekly.pop(current_week, None)

        games_over_time = []
        players_over_time = []
        for week in all_weeks:
            bot_g = bot_weekly.get(week, 0)
            web_g = web_weekly.get(week, 0)
            games_over_time.append({
                "week": week,
                "bot": bot_g,
                "web": web_g,
                "total": bot_g + web_g,
            })
            players_over_time.append({
                "week": week,
                "combined": combined_players_weekly.get(week, 0),
            })

        new_players_per_week = [
            {"week": w, "count": new_players_weekly.get(w, 0)}
            for w in all_weeks
        ]

        return jsonify({
            "success": True,
            "games_over_time": games_over_time,
            "players_over_time": players_over_time,
            "new_players_per_week": new_players_per_week,
            "heatmap": heatmap,
            "dominance": dominance,
            "avg_games_per_player": avg_games_per_player,
            "summary": {
                "total_matches": total_bot_matches + total_web_matches,
                "total_bot_matches": total_bot_matches,
                "total_web_matches": total_web_matches,
                "total_players": total_players,
                "avg_weekly_games": avg_weekly_games,
                "total_logins": total_logins,
            },
        }), 200

    except Exception as e:
        logger.error(f"Failed to get dashboard stats: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/admin/start-event", methods=["POST"])
@require_admin
def start_event_route():
    """Start a new event/season (admin only)."""
    data = request.get_json(silent=True)
    if not data or not data.get("event_name"):
        return jsonify({"success": False, "error": "event_name is required"}), 400

    event_name = str(data["event_name"]).strip()
    if not event_name or len(event_name) > 100:
        return jsonify({"success": False, "error": "Invalid event name (1-100 characters)"}), 400

    try:
        # Import bot database utilities
        bot_db = _import_bot_database_utils()

        # Get previous event info for audit log
        previous_event = bot_db.get_active_event()

        # Start new event
        result = bot_db.start_new_event(event_name)

        # Log action
        admin_id, admin_name = _get_admin_info()
        audit = AuditRepository()
        audit.log_action(
            admin_id, admin_name, "web_start_event",
            target_name=event_name,
            previous_state={"event": previous_event["event_name"] if previous_event else None},
            new_state={"event": event_name, "event_id": result["event_id"]},
            details=f"Started new event '{event_name}' (ID: {result['event_id']})",
        )

        return jsonify({
            "success": True,
            "message": f"Event '{event_name}' started successfully",
            "event_id": result["event_id"],
            "previous_event": result.get("previous_event")
        }), 200

    except Exception as e:
        logger.error(f"Failed to start event: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/admin/end-event", methods=["POST"])
@require_admin
def end_event_route():
    """End the current event without starting a new one (admin only)."""
    try:
        # Import bot database utilities
        bot_db = _import_bot_database_utils()

        # Get active event for audit log
        active_event = bot_db.get_active_event()
        if not active_event:
            return jsonify({"success": False, "error": "No active event to end"}), 400

        # End event
        result = bot_db.end_current_event()

        # Log action
        admin_id, admin_name = _get_admin_info()
        audit = AuditRepository()
        audit.log_action(
            admin_id, admin_name, "web_end_event",
            target_name=active_event["event_name"],
            previous_state={"event": active_event["event_name"], "event_id": active_event["event_id"]},
            new_state={"event": None},
            details=f"Ended event '{active_event['event_name']}' (ID: {active_event['event_id']})",
        )

        return jsonify({
            "success": True,
            "message": f"Event '{active_event['event_name']}' ended successfully",
            "summary": result
        }), 200

    except Exception as e:
        logger.error(f"Failed to end event: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
