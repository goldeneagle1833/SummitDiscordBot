"""Replay helpers for avatar-specific event standings."""

import datetime
import json
import logging
import sqlite3

from webapp_config import ELO_DB_PATH, MATCH_RECORDS_DB_PATH

logger = logging.getLogger(__name__)


def _calculate_elo(player_elo: int, opponent_elo: int, did_win: bool, k: int) -> int:
    expected = 1 / (1 + 10 ** ((opponent_elo - player_elo) / 400))
    return round(player_elo + k * ((1 if did_win else 0) - expected))


def _event_k(start_date: datetime.datetime, timestamp: str) -> int:
    match_time = datetime.datetime.fromisoformat(timestamp)
    days_elapsed = max(0, (match_time - start_date).days)
    return min(16 + (days_elapsed * 2), 32)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _online_matches(
    conn: sqlite3.Connection,
    event_id: int,
    start_date: str,
    end_date: str | None,
) -> list[tuple]:
    rows = []
    current_columns = _table_columns(conn, "match_records")
    if current_columns:
        winner_multiplier = (
            "COALESCE(winner_elo_multiplier, 1.0)"
            if "winner_elo_multiplier" in current_columns
            else "1.0"
        )
        loser_multiplier = (
            "COALESCE(loser_elo_multiplier, 1.0)"
            if "loser_elo_multiplier" in current_columns
            else "1.0"
        )
        end_filter = " AND timestamp <= ?" if end_date else ""
        params = [start_date]
        if end_date:
            params.append(end_date)
        rows.extend(
            conn.execute(
                f"""SELECT winner_id, winner_display_name, winner_avatar,
                            losser_id, losser_display_name, loser_avatar, timestamp,
                            {winner_multiplier}, {loser_multiplier}
                     FROM match_records
                     WHERE timestamp >= ?{end_filter}
                       AND winner_avatar IS NOT NULL AND loser_avatar IS NOT NULL
                       AND (match_type IS NULL OR match_type = 'ranked')""",
                params,
            ).fetchall()
        )

    archive_columns = _table_columns(conn, "match_records_archive")
    if archive_columns and "event_id" in archive_columns:
        winner_multiplier = (
            "COALESCE(winner_elo_multiplier, 1.0)"
            if "winner_elo_multiplier" in archive_columns
            else "1.0"
        )
        loser_multiplier = (
            "COALESCE(loser_elo_multiplier, 1.0)"
            if "loser_elo_multiplier" in archive_columns
            else "1.0"
        )
        rows.extend(
            conn.execute(
                f"""SELECT winner_id, winner_display_name, winner_avatar,
                          losser_id, losser_display_name, loser_avatar, timestamp,
                          {winner_multiplier}, {loser_multiplier}
                   FROM match_records_archive
                   WHERE event_id = ?
                     AND winner_avatar IS NOT NULL AND loser_avatar IS NOT NULL
                     AND (match_type IS NULL OR match_type = 'ranked')""",
                (event_id,),
            ).fetchall()
        )
    return rows


def _paper_matches(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str | None,
) -> list[tuple]:
    columns = _table_columns(conn, "match_reports_web")
    if not columns:
        return []
    winner_multiplier = (
        "COALESCE(winner_elo_multiplier, 1.0)"
        if "winner_elo_multiplier" in columns
        else "1.0"
    )
    loser_multiplier = (
        "COALESCE(loser_elo_multiplier, 1.0)"
        if "loser_elo_multiplier" in columns
        else "1.0"
    )
    end_filter = " AND timestamp <= ?" if end_date else ""
    elo_filter = ""
    if {"winner_elo_change", "loser_elo_change"}.issubset(columns):
        # Repeat matchups are recorded with zero changes and must not enter the ladder.
        elo_filter = " AND (winner_elo_change != 0 OR loser_elo_change != 0)"
    params = [start_date]
    if end_date:
        params.append(end_date)
    return conn.execute(
        f"""SELECT winner_id, winner_display_name, winner_avatar,
                   losser_id, losser_display_name, loser_avatar, timestamp,
                   {winner_multiplier}, {loser_multiplier}
            FROM match_reports_web
            WHERE timestamp >= ?{end_filter}
              AND winner_avatar IS NOT NULL AND loser_avatar IS NOT NULL
              AND (match_type IS NULL OR match_type = 'ranked')
              {elo_filter}""",
        params,
    ).fetchall()


def _spot_resets(
    conn: sqlite3.Connection,
    source: str,
    start_date: str,
    end_date: str | None,
) -> list[tuple]:
    if not _table_columns(conn, "admin_audit_log"):
        return []

    end_filter = " AND timestamp <= ?" if end_date else ""
    params = [start_date]
    if end_date:
        params.append(end_date)
    rows = conn.execute(
        f"""SELECT id, timestamp, target_id, target_name, action, new_state
            FROM admin_audit_log
            WHERE action IN ('spot_elo_reset', 'web_reset_elo')
              AND timestamp >= ?{end_filter}
            ORDER BY timestamp ASC, id ASC""",
        params,
    ).fetchall()

    resets = []
    for reset_id, timestamp, target_id, target_name, action, raw_state in rows:
        try:
            state = json.loads(raw_state or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        avatar = state.get("avatar")
        if not avatar:
            continue
        if action == "spot_elo_reset":
            if source != "online" or "event_elo" not in state:
                continue
            event_elo = state["event_elo"]
        else:
            requested_source = state.get("source", "both")
            applies = requested_source == "both" or (
                source == "online" and requested_source == "bot"
            ) or (source == "paper" and requested_source == "paper")
            if not applies or "elo" not in state:
                continue
            event_elo = state["elo"]
        resets.append(
            (
                reset_id,
                timestamp,
                str(target_id),
                target_name or f"User#{target_id}",
                avatar,
                int(event_elo),
            )
        )
    return resets


def recalculate_avatar_event_standings(event_id: int, source: str) -> int:
    """Replace one event/source ladder by replaying its ranked matches."""
    if source not in ("online", "paper"):
        raise ValueError("Avatar event source must be 'online' or 'paper'")

    elo_conn = sqlite3.connect(str(ELO_DB_PATH))
    event = elo_conn.execute(
        """SELECT start_date, end_date, avatar_specific
           FROM events WHERE event_id = ?""",
        (event_id,),
    ).fetchone()
    if not event or not event[2]:
        elo_conn.close()
        return 0

    start_date_str, end_date, _ = event
    start_date = datetime.datetime.fromisoformat(start_date_str)
    match_conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
    try:
        matches = (
            _online_matches(match_conn, event_id, start_date_str, end_date)
            if source == "online"
            else _paper_matches(match_conn, start_date_str, end_date)
        )
        spot_resets = _spot_resets(
            match_conn, source, start_date_str, end_date
        )
    finally:
        match_conn.close()

    ratings: dict[tuple[str, str], int] = {}
    names: dict[tuple[str, str], str] = {}
    operations = [
        (row[6] or "", 1, index, "match", row)
        for index, row in enumerate(matches)
    ]
    operations.extend(
        (reset[1] or "", 0, reset[0], "spot_reset", reset)
        for reset in spot_resets
    )
    operations.sort(key=lambda operation: operation[:3])

    for _, _, _, operation_kind, row in operations:
        if operation_kind == "spot_reset":
            _, _, target_id, target_name, avatar, event_elo = row
            key = (target_id, avatar)
            ratings[key] = event_elo
            names[key] = target_name
            continue

        (
            winner_id,
            winner_name,
            winner_avatar,
            loser_id,
            loser_name,
            loser_avatar,
            timestamp,
            winner_multiplier,
            loser_multiplier,
        ) = row
        winner_key = (str(winner_id), winner_avatar)
        loser_key = (str(loser_id), loser_avatar)
        winner_before = ratings.get(winner_key, 1500)
        loser_before = ratings.get(loser_key, 1500)
        k_value = _event_k(start_date, timestamp)
        winner_base = _calculate_elo(
            winner_before, loser_before, True, k_value
        )
        loser_base = _calculate_elo(
            loser_before, winner_before, False, k_value
        )
        ratings[winner_key] = winner_before + round(
            (winner_base - winner_before) * winner_multiplier
        )
        ratings[loser_key] = loser_before + round(
            (loser_base - loser_before) * loser_multiplier
        )
        names[winner_key] = winner_name
        names[loser_key] = loser_name

    try:
        elo_conn.execute(
            "DELETE FROM event_avatar_standings WHERE event_id = ? AND source = ?",
            (event_id, source),
        )
        elo_conn.executemany(
            """INSERT INTO event_avatar_standings
               (event_id, source, user_id, user_display_name, avatar_name, event_elo)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (event_id, source, user_id, names[(user_id, avatar)], avatar, elo)
                for (user_id, avatar), elo in ratings.items()
            ],
        )
        elo_conn.commit()
    except Exception:
        elo_conn.rollback()
        raise
    finally:
        elo_conn.close()

    logger.info(
        "Replayed avatar event standings: event=%s source=%s matches=%s entries=%s",
        event_id,
        source,
        len(matches),
        len(ratings),
    )
    return len(matches)


def recalculate_avatar_event_for_timestamp(source: str, timestamp: str | None) -> int:
    """Replay the avatar event containing a match timestamp, if one exists."""
    if not timestamp:
        return 0
    conn = sqlite3.connect(str(ELO_DB_PATH))
    row = conn.execute(
        """SELECT event_id FROM events
           WHERE avatar_specific = 1 AND start_date <= ?
             AND (end_date IS NULL OR end_date >= ?)
           ORDER BY start_date DESC LIMIT 1""",
        (timestamp, timestamp),
    ).fetchone()
    conn.close()
    return recalculate_avatar_event_standings(row[0], source) if row else 0


def recalculate_all_avatar_event_standings() -> int:
    """Replay both source ladders for every avatar-specific event."""
    conn = sqlite3.connect(str(ELO_DB_PATH))
    event_ids = [
        row[0]
        for row in conn.execute(
            "SELECT event_id FROM events WHERE avatar_specific = 1"
        ).fetchall()
    ]
    conn.close()
    replayed = 0
    for event_id in event_ids:
        replayed += recalculate_avatar_event_standings(event_id, "online")
        replayed += recalculate_avatar_event_standings(event_id, "paper")
    return replayed
