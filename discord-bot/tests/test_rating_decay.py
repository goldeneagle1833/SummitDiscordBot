"""Inactivity decay on Glicko-2 Avatar-mode season ratings.

An avatar entry not played for a week loses 10 points a day until it is
played again; never below 1500; provisional entries don't decay; it stops
when the season ends. Uses the real record_match / table layout.
"""

import datetime
import sqlite3

import pytest

from cogs.rating_decay import run_decay
from services import glicko2_season as g2
from services.elo_service import end_current_event, record_match, start_new_event

A, B, C = 111, 222, 333


async def _record(winner_id, loser_id, winner_avatar, loser_avatar):
    match_id, *_ = await record_match(
        reporter_id=winner_id, winner_id=winner_id, winner_global=f"P{winner_id}",
        loser_id=loser_id, loser_global=f"P{loser_id}", first_player="y", match_time=20,
        match_comment="", winner_deck_url=None, loser_deck_url=None,
        winner_went_first="y", loser_went_first="n",
        winner_avatar=winner_avatar, loser_avatar=loser_avatar,
    )
    return match_id


def _entry(user_id, avatar):
    conn = sqlite3.connect("elo.db")
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM event_avatar_standings WHERE user_id = ? AND avatar = ?", (user_id, avatar)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _shift(dt: str, days: float) -> str:
    return (g2._parse(dt) - datetime.timedelta(days=days)).isoformat()


def _backdate(days: float):
    """Move every game and 'last played' time of the season back by ``days``."""
    m = sqlite3.connect("match_records.db")
    try:
        for row_id, ts in m.execute("SELECT rowid, timestamp FROM season_match_records").fetchall():
            m.execute("UPDATE season_match_records SET timestamp = ? WHERE rowid = ?", (_shift(ts, days), row_id))
        m.commit()
    finally:
        m.close()
    e = sqlite3.connect("elo.db")
    try:
        for uid, avatar, ts in e.execute(
            "SELECT user_id, avatar, last_played_at FROM event_avatar_standings"
        ).fetchall():
            e.execute(
                "UPDATE event_avatar_standings SET last_played_at = ? WHERE user_id = ? AND avatar = ?",
                (_shift(ts, days), uid, avatar),
            )
        for uid, ts in e.execute(
            "SELECT user_id, online_event_last_at FROM overall_standings WHERE online_event_last_at IS NOT NULL"
        ).fetchall():
            e.execute("UPDATE overall_standings SET online_event_last_at = ? WHERE user_id = ?",
                      (_shift(ts, days), uid))
        e.execute("UPDATE events SET start_date = ?", (_shift(datetime.datetime.now().isoformat(), days + 1),))
        e.commit()
    finally:
        e.close()


def _rebuild(now=None):
    elo_conn, match_conn = sqlite3.connect("elo.db"), sqlite3.connect("match_records.db")
    try:
        g2.rebuild_season(elo_conn, match_conn, g2.get_event(elo_conn), now=now)
        elo_conn.commit()
        match_conn.commit()
    finally:
        elo_conn.close()
        match_conn.close()


async def _settled_seer(games=g2.PROVISIONAL_GAMES):
    """A on Seer beats B on Witch enough times to be settled (A above 1500, B below)."""
    start_new_event("Season 9", elo_mode="avatar", rating_system="glicko2")
    for _ in range(games):
        await _record(A, B, "Seer", "Witch")


# ── The rule ──


def _r(rating, last_at="2026-11-01T12:00:00", decay=0.0):
    return g2.Rating(rating, 100.0, 0.06, last_at, decay)


@pytest.mark.parametrize("days, owed", [
    (0, 0), (6.9, 0), (7, 0), (7.99, 0), (8, 10), (8.5, 10), (10, 30), (20, 130),
])
def test_ten_points_a_day_after_a_week(days, owed):
    until = _shift("2026-11-01T12:00:00", -days)
    assert g2.decay_owed(_r(1800), 8, until) == owed


def test_decay_stops_at_1500():
    until = _shift("2026-11-01T12:00:00", -30)  # 230 owed
    assert g2.decay_owed(_r(1620), 8, until) == 120
    assert g2.decay_owed(_r(1480), 8, until) == 0
    # The floor counts from the rating before any decay, not the decayed one
    assert g2.decay_owed(_r(1520, decay=100), 8, until) == 120


def test_provisional_entries_do_not_decay():
    until = _shift("2026-11-01T12:00:00", -30)
    assert g2.decay_owed(_r(1800), g2.PROVISIONAL_GAMES - 1, until) == 0


def test_decay_status_counts_down_then_shows_points():
    last = "2026-11-01T12:00:00"
    s = g2.decay_status(1700, 8, last, 0, _shift(last, -6))
    assert s == {"decay": 0, "idle_days": 6, "decay_in_days": 2}
    assert g2.decay_status(1700, 8, last, 0, _shift(last, -7))["decay_in_days"] == 1
    assert g2.decay_status(1700, 8, last, 0, _shift(last, -3))["decay_in_days"] is None
    assert g2.decay_status(1450, 8, last, 0, _shift(last, -6))["decay_in_days"] is None  # at/below floor
    assert g2.decay_status(1700, 3, last, 0, _shift(last, -6))["decay_in_days"] is None  # provisional
    assert g2.decay_status(1670, 8, last, 30, _shift(last, -10)) == {
        "decay": 30, "idle_days": 10, "decay_in_days": None,
    }


# ── The live job, matches and rebuilds ──


@pytest.mark.asyncio
async def test_job_takes_decay_off_once_and_rebuild_agrees():
    await _settled_seer()
    _backdate(10)
    seer = _entry(A, "Seer")
    start = seer["rating"]
    now = datetime.datetime.now().isoformat()

    moved = run_decay(now=now)
    seer = _entry(A, "Seer")
    assert seer["rating"] == pytest.approx(start - 30)
    assert seer["decay_points"] == 30
    assert seer["event_elo"] == round(start - 30)
    assert [(m["user_id"], m["avatar"]) for m in moved] == [(A, "Seer")]  # Witch is below 1500
    assert _entry(B, "Witch")["decay_points"] == 0

    # Running again changes nothing; a day later takes off 10 more
    assert run_decay(now=now) == []
    run_decay(now=_shift(now, -1))
    assert _entry(A, "Seer")["rating"] == pytest.approx(start - 40)

    # A full rebuild lands on the same numbers
    _rebuild(now=_shift(now, -1))
    seer = _entry(A, "Seer")
    assert seer["rating"] == pytest.approx(start - 40)
    assert seer["decay_points"] == 40


@pytest.mark.asyncio
async def test_player_ladder_and_lifetime_do_not_decay():
    await _settled_seer()
    _backdate(20)
    conn = sqlite3.connect("elo.db")
    before = conn.execute("SELECT user_id, online_event_elo, online_elo FROM overall_standings ORDER BY user_id").fetchall()
    conn.close()
    run_decay()
    _rebuild()
    conn = sqlite3.connect("elo.db")
    after = conn.execute("SELECT user_id, online_event_elo, online_elo FROM overall_standings ORDER BY user_id").fetchall()
    conn.close()
    assert after == before
    assert _entry(A, "Seer")["decay_points"] == 130


@pytest.mark.asyncio
async def test_playing_again_stops_decay_and_matches_a_rebuild():
    await _settled_seer()
    _backdate(10)
    run_decay()
    decayed = _entry(A, "Seer")["event_elo"]

    await _record(A, C, "Seer", "Druid")

    seer = _entry(A, "Seer")
    assert seer["decay_points"] == 0  # the clock restarts
    m = sqlite3.connect("match_records.db")
    m.row_factory = sqlite3.Row
    row = dict(m.execute("SELECT * FROM season_match_records ORDER BY rowid DESC LIMIT 1").fetchone())
    m.close()
    # The game is rated from the decayed number
    assert row["winner_avatar_before"] == decayed
    assert row["winner_avatar_elo_change"] == seer["event_elo"] - decayed

    live = (seer["rating"], row["winner_avatar_elo_change"], row["winner_avatar_before"], row["winner_avatar_rank"])
    _rebuild()
    m = sqlite3.connect("match_records.db")
    m.row_factory = sqlite3.Row
    row = dict(m.execute("SELECT * FROM season_match_records ORDER BY rowid DESC LIMIT 1").fetchone())
    m.close()
    seer = _entry(A, "Seer")
    assert (seer["rating"], row["winner_avatar_elo_change"], row["winner_avatar_before"],
            row["winner_avatar_rank"]) == (pytest.approx(live[0]), *live[1:])


@pytest.mark.asyncio
async def test_decay_stops_when_the_season_ends():
    await _settled_seer()
    _backdate(10)
    end_current_event()
    seer = _entry(A, "Seer")
    assert seer["decay_points"] == 30  # caught up at the end
    # Later runs and rebuilds of the ended season don't take more
    conn = sqlite3.connect("elo.db")
    event = g2.get_event(conn, seer["event_id"])
    assert g2.apply_decay(conn, event, _shift(datetime.datetime.now().isoformat(), -30)) == []
    conn.close()


@pytest.mark.asyncio
async def test_elo_avatar_seasons_do_not_decay():
    start_new_event("Classic", elo_mode="avatar")
    for _ in range(8):
        await _record(A, B, "Seer", "Witch")
    before = _entry(A, "Seer")["event_elo"]
    assert run_decay(now=_shift(datetime.datetime.now().isoformat(), -20)) == []
    assert _entry(A, "Seer")["event_elo"] == before
