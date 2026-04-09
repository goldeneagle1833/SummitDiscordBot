"""Fun Stats API routes."""

import json
import logging
import sqlite3
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from webapp_config import MATCH_RECORDS_DB_PATH, ELO_DB_PATH, SEASON_FILTERS
from utils.auth import is_admin

logger = logging.getLogger(__name__)

fun_stats_bp = Blueprint("fun_stats", __name__)


# ── Filter endpoint ──────────────────────────────────────���──────────


@fun_stats_bp.route("/fun-stats/filters")
def get_fun_stats_filters():
    """Return available events and sources for fun stats filtering."""
    events = []
    sources = []

    try:
        conn = sqlite3.connect(str(ELO_DB_PATH))
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
        )
        if cur.fetchone():
            cur.execute("""
                SELECT event_id, event_name, start_date, end_date, is_active
                FROM events ORDER BY start_date DESC
            """)
            user_admin = is_admin()
            for row in cur.fetchall():
                active = bool(row[4])
                if active and not user_admin:
                    continue
                events.append({
                    "event_id": row[0],
                    "event_name": row[1],
                    "start_date": row[2],
                    "end_date": row[3],
                    "is_active": active,
                })
        conn.close()
    except sqlite3.OperationalError as e:
        logger.warning(f"Could not query events: {e}")

    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT source FROM match_records WHERE source IS NOT NULL ORDER BY source"
        )
        sources = [row[0] for row in cur.fetchall()]
        conn.close()
    except sqlite3.OperationalError as e:
        logger.warning(f"Could not query sources: {e}")

    for sf in SEASON_FILTERS:
        events.append({
            "event_id": sf["id"],
            "event_name": sf["name"],
            "start_date": sf["start_date"],
            "end_date": sf["end_date"],
            "is_active": False,
        })

    return jsonify({"events": events, "sources": sources})


# ── Filter helpers ──────────────────────────────────────────────────


def _get_event_date_range(event_id):
    """Resolve an event filter value to (start_date, end_date) or (None, None)."""
    if isinstance(event_id, str) and event_id.startswith("season_"):
        for sf in SEASON_FILTERS:
            if sf["id"] == event_id:
                return sf["start_date"], sf["end_date"]
        return None, None

    try:
        conn = sqlite3.connect(str(ELO_DB_PATH))
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
        )
        if not cur.fetchone():
            conn.close()
            return None, None

        if event_id == "current":
            cur.execute("SELECT start_date, end_date FROM events WHERE is_active = 1 LIMIT 1")
        else:
            cur.execute(
                "SELECT start_date, end_date FROM events WHERE event_id = ?",
                (int(event_id),),
            )
        row = cur.fetchone()
        conn.close()
        if row:
            return row[0], row[1]
    except (sqlite3.OperationalError, ValueError) as e:
        logger.warning(f"Could not get event date range: {e}")
    return None, None


def _collect_match_rows(event_filter, source_filter):
    """Fetch match rows based on filter, returning all columns needed by stat functions.

    Returns list of dicts with keys: winner_id, winner_display_name, losser_id,
    losser_display_name, timestamp, match_time, json_deck_data_winner,
    json_deck_data_loser, winner_elo_change, loser_elo_change,
    winner_lifetime_elo_change, loser_lifetime_elo_change,
    winner_went_first, loser_went_first.
    """
    columns = (
        "winner_id, winner_display_name, losser_id, losser_display_name, "
        "timestamp, match_time, json_deck_data_winner, json_deck_data_loser, "
        "winner_elo_change, loser_elo_change, "
        "winner_lifetime_elo_change, loser_lifetime_elo_change, "
        "winner_went_first, loser_went_first"
    )
    col_keys = [
        "winner_id", "winner_display_name", "losser_id", "losser_display_name",
        "timestamp", "match_time", "json_deck_data_winner", "json_deck_data_loser",
        "winner_elo_change", "loser_elo_change",
        "winner_lifetime_elo_change", "loser_lifetime_elo_change",
        "winner_went_first", "loser_went_first",
    ]

    rows = []
    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()

        # Detect available tables
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cur.fetchall()}
        has_archive = "match_records_archive" in tables

        # Build WHERE clauses
        where_parts = []
        params = []

        # Source filter
        if source_filter:
            where_parts.append("source = ?")
            params.append(source_filter)

        # Match type filter (exclude testing)
        where_parts.append("(match_type = 'ranked' OR match_type IS NULL)")

        if event_filter == "all":
            # Current + archive
            _query_table(cur, "match_records", columns, where_parts, params, rows, col_keys)
            if has_archive:
                _query_table(cur, "match_records_archive", columns, where_parts, params, rows, col_keys)

        elif event_filter and event_filter != "current" and not str(event_filter).startswith("season_"):
            # Specific past event from archive
            if has_archive:
                archive_where = where_parts + ["event_id = ?"]
                archive_params = params + [int(event_filter)]
                _query_table(cur, "match_records_archive", columns, archive_where, archive_params, rows, col_keys)

        elif event_filter and (event_filter == "current" or str(event_filter).startswith("season_")):
            # Date-range filter
            start_date, end_date = _get_event_date_range(event_filter)
            if start_date:
                date_where = where_parts + ["timestamp >= ?"]
                date_params = params + [start_date]
                if end_date:
                    date_where.append("timestamp <= ?")
                    date_params.append(end_date)
                _query_table(cur, "match_records", columns, date_where, date_params, rows, col_keys)
                if has_archive:
                    _query_table(cur, "match_records_archive", columns, date_where, date_params, rows, col_keys)
        else:
            # Default: current match_records only
            _query_table(cur, "match_records", columns, where_parts, params, rows, col_keys)

        conn.close()
    except Exception as e:
        logger.error(f"Error collecting match rows: {e}")

    return rows


def _query_table(cur, table, columns, where_parts, params, rows, col_keys):
    """Execute a SELECT on a table with optional WHERE clauses, appending dicts to rows.

    Handles tables missing some columns (e.g. archive) by substituting NULL.
    """
    try:
        # Detect which columns actually exist in this table
        cur.execute(f"PRAGMA table_info({table})")
        available = {r[1] for r in cur.fetchall()}

        # Build SELECT list — NULL for missing columns
        safe_cols = [col if col in available else "NULL" for col in col_keys]
        col_str = ", ".join(safe_cols)

        # Filter WHERE clauses that reference missing columns
        safe_where = []
        safe_params = []
        param_idx = 0
        for part in where_parts:
            has_param = "?" in part
            # Check if clause uses a missing column
            uses_missing = any(col not in available and col in part for col in col_keys)
            if not uses_missing:
                safe_where.append(part)
                if has_param:
                    safe_params.append(params[param_idx])
            if has_param:
                param_idx += 1

        where_clause = " AND ".join(safe_where) if safe_where else "1=1"
        cur.execute(f"SELECT {col_str} FROM {table} WHERE {where_clause}", safe_params)
        for row in cur.fetchall():
            rows.append(dict(zip(col_keys, row)))
    except sqlite3.OperationalError as e:
        logger.warning(f"Could not query {table}: {e}")


# ── Stat compute functions ──────────────────────────────────────────


def _compute_win_streaks(rows):
    """Compute top 10 win streaks from chronologically sorted match rows."""
    sorted_rows = sorted(rows, key=lambda r: r["timestamp"] or "")
    names = {}
    streaks = {}

    for r in sorted_rows:
        wid, lid = r["winner_id"], r["losser_id"]
        names[wid] = r["winner_display_name"] or str(wid)
        names[lid] = r["losser_display_name"] or str(lid)

        # Winner
        if wid not in streaks:
            streaks[wid] = {"current": 0, "best": 0, "type": ""}
        s = streaks[wid]
        if s["type"] == "W":
            s["current"] += 1
        else:
            s["current"] = 1
            s["type"] = "W"
        s["best"] = max(s["best"], s["current"])

        # Loser
        if lid not in streaks:
            streaks[lid] = {"current": 0, "best": 0, "type": ""}
        s = streaks[lid]
        if s["type"] == "L":
            s["current"] += 1
        else:
            s["current"] = 1
            s["type"] = "L"

    result = []
    for pid, s in streaks.items():
        if s["best"] >= 3:
            result.append({
                "name": names.get(pid, str(pid)),
                "best_streak": s["best"],
                "current_streak": s["current"] if s["type"] == "W" else 0,
            })
    result.sort(key=lambda x: x["best_streak"], reverse=True)
    return result[:10]


def _extract_avatar(deck_str):
    """Extract avatar name from JSON deck data string."""
    if not deck_str or deck_str in ("", "{}"):
        return None
    try:
        deck = json.loads(deck_str)
        avatar = deck.get("avatar", [{}])
        name = avatar[0].get("name", "Unknown") if avatar else "Unknown"
        return name if name and name != "Unknown" else None
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        return None


def _compute_most_diverse(rows):
    """Compute top 10 players by number of unique avatars played."""
    players = {}

    for r in rows:
        for role, deck_key, name_key in [
            (r["winner_id"], "json_deck_data_winner", "winner_display_name"),
            (r["losser_id"], "json_deck_data_loser", "losser_display_name"),
        ]:
            avatar = _extract_avatar(r[deck_key])
            if avatar:
                if role not in players:
                    players[role] = {"name": r[name_key] or str(role), "avatars": set()}
                players[role]["avatars"].add(avatar)

    result = [
        {
            "name": p["name"],
            "unique_avatars": len(p["avatars"]),
            "avatars": sorted(p["avatars"]),
        }
        for p in players.values()
        if len(p["avatars"]) > 1
    ]
    result.sort(key=lambda x: x["unique_avatars"], reverse=True)
    return result[:10]


def _compute_most_active(rows):
    """Compute top 10 most active players by total games."""
    players = {}

    for r in rows:
        wid, lid = r["winner_id"], r["losser_id"]
        if wid not in players:
            players[wid] = {"name": r["winner_display_name"] or str(wid), "wins": 0, "losses": 0}
        players[wid]["wins"] += 1

        if lid not in players:
            players[lid] = {"name": r["losser_display_name"] or str(lid), "wins": 0, "losses": 0}
        players[lid]["losses"] += 1

    result = [
        {
            "name": p["name"],
            "wins": p["wins"],
            "losses": p["losses"],
            "games": p["wins"] + p["losses"],
        }
        for p in players.values()
    ]
    result.sort(key=lambda x: x["games"], reverse=True)
    return result[:10]


def _compute_biggest_upsets(rows):
    """Compute top 5 biggest upsets by winner ELO change."""
    candidates = []
    for r in rows:
        elo = r["winner_elo_change"]
        if elo and elo > 0:
            candidates.append({
                "winner_name": r["winner_display_name"] or "Unknown",
                "elo_change": elo,
                "timestamp": r["timestamp"] or "",
            })
    candidates.sort(key=lambda x: x["elo_change"], reverse=True)
    return candidates[:5]


def _compute_nemesis_pairs(rows):
    """Compute top 5 player pairs with most encounters."""
    pairs = {}
    names = {}

    for r in rows:
        wid, lid = r["winner_id"], r["losser_id"]
        names[wid] = r["winner_display_name"] or str(wid)
        names[lid] = r["losser_display_name"] or str(lid)

        key = (min(wid, lid), max(wid, lid))
        if key not in pairs:
            pairs[key] = {"encounters": 0, "wins": {key[0]: 0, key[1]: 0}}
        pairs[key]["encounters"] += 1
        pairs[key]["wins"][wid] += 1

    result = []
    for (p1, p2), data in pairs.items():
        if data["encounters"] >= 3:
            result.append({
                "player1_name": names.get(p1, str(p1)),
                "player2_name": names.get(p2, str(p2)),
                "encounters": data["encounters"],
                "p1_wins": data["wins"][p1],
                "p2_wins": data["wins"][p2],
            })
    result.sort(key=lambda x: x["encounters"], reverse=True)
    return result[:5]


def _compute_first_player_advantage(rows):
    """Compute overall first-player win rate."""
    total = 0
    first_wins = 0

    for r in rows:
        wf = r["winner_went_first"]
        lf = r["loser_went_first"]
        if not wf and not lf:
            continue
        total += 1
        # If winner_went_first has a truthy value, the first player won
        if wf:
            first_wins += 1

    if total == 0:
        return None
    return {
        "total_matches": total,
        "first_player_wins": first_wins,
        "first_player_win_rate": round(first_wins / total * 100, 1),
    }


def _compute_match_duration(rows):
    """Compute match duration stats (average, min, max)."""
    times = [r["match_time"] for r in rows if r["match_time"] and 4 <= r["match_time"] <= 180]
    if not times:
        return None
    return {
        "average_minutes": round(sum(times) / len(times), 1),
        "fastest_minutes": min(times),
        "longest_minutes": max(times),
        "total_with_data": len(times),
    }


def _compute_most_improved(rows):
    """Compute top 5 most improved players in the last 7 days."""
    cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()
    players = {}

    for r in rows:
        ts = r["timestamp"]
        if not ts or ts < cutoff:
            continue

        wid, lid = r["winner_id"], r["losser_id"]
        w_change = r["winner_lifetime_elo_change"]
        l_change = r["loser_lifetime_elo_change"]

        if w_change is not None:
            if wid not in players:
                players[wid] = {"name": r["winner_display_name"] or str(wid), "change": 0}
            players[wid]["change"] += w_change

        if l_change is not None:
            if lid not in players:
                players[lid] = {"name": r["losser_display_name"] or str(lid), "change": 0}
            players[lid]["change"] += l_change

    result = [
        {"name": p["name"], "elo_change": p["change"]}
        for p in players.values()
        if p["change"] > 0
    ]
    result.sort(key=lambda x: x["elo_change"], reverse=True)
    return result[:5]


def _compute_ironman_streak(rows):
    """Compute top 10 players by longest consecutive days with matches."""
    players = {}

    for r in rows:
        ts = r["timestamp"]
        if not ts:
            continue
        date_str = ts[:10]  # "YYYY-MM-DD"

        for pid, name_key in [(r["winner_id"], "winner_display_name"), (r["losser_id"], "losser_display_name")]:
            if pid not in players:
                players[pid] = {"name": r[name_key] or str(pid), "dates": set()}
            players[pid]["dates"].add(date_str)

    result = []
    for pid, p in players.items():
        dates = sorted(p["dates"])
        if len(dates) < 2:
            continue
        best = 1
        current = 1
        for i in range(1, len(dates)):
            try:
                d1 = datetime.strptime(dates[i - 1], "%Y-%m-%d")
                d2 = datetime.strptime(dates[i], "%Y-%m-%d")
                if (d2 - d1).days == 1:
                    current += 1
                    best = max(best, current)
                else:
                    current = 1
            except ValueError:
                current = 1
        if best >= 2:
            result.append({"name": p["name"], "consecutive_days": best})

    result.sort(key=lambda x: x["consecutive_days"], reverse=True)
    return result[:10]


# ── Main stats endpoint ─────────────────────────────────────────────


@fun_stats_bp.route("/fun-stats")
def get_fun_stats():
    """Return all fun stats, optionally filtered by event and source."""
    try:
        event_filter = request.args.get("event", "")
        source_filter = request.args.get("source", "")

        rows = _collect_match_rows(event_filter, source_filter)

        stats = {
            "win_streaks": _compute_win_streaks(rows),
            "most_diverse": _compute_most_diverse(rows),
            "most_active": _compute_most_active(rows),
            "biggest_upsets": _compute_biggest_upsets(rows),
            "nemesis_pairs": _compute_nemesis_pairs(rows),
            "match_duration": _compute_match_duration(rows),
            "most_improved": _compute_most_improved(rows),
            "ironman_streak": _compute_ironman_streak(rows),
        }

        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        logger.error(f"Error computing fun stats: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
