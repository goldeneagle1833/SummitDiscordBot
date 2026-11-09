"""Glicko-2 seasons (Season 9 on): maths, reporting, fixes, top cut and archiving."""

import datetime
import filecmp
import math
import os
import sqlite3

import pytest

from repositories.elo_repo import (
    get_active_event,
    get_top_16_user_ids,
    set_player_event_elo,
)
from repositories.avatar_elo_repo import get_avatar_standings, set_avatar_event_elo
from services import glicko2_season as g2
from services.avatar_mode import get_event_ladder, top_cut_eligible
from services.elo_service import (
    correct_match_record,
    end_current_event,
    get_current_event_match_elo_snapshot,
    recalculate_event_elo,
    record_match,
    remove_match_record,
    remove_player,
    start_new_event,
)
from services.postseason import select_top_cut

A, B, C, D = 111, 222, 333, 444


async def _record(winner_id=A, loser_id=B, **kwargs):
    defaults = dict(
        reporter_id=winner_id, winner_id=winner_id, winner_global=f"P{winner_id}",
        loser_id=loser_id, loser_global=f"P{loser_id}", first_player="y", match_time=20,
        match_comment="", winner_deck_url=None, loser_deck_url=None,
        winner_went_first="y", loser_went_first="n",
    )
    defaults.update(kwargs)
    match_id, *_ = await record_match(**defaults)
    return match_id


def _rows(sql, params=(), db="match_records.db"):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _standings():
    return {
        r["user_id"]: r for r in _rows(
            "SELECT user_id, online_elo, online_event_elo, online_event_games, online_event_rating, "
            "online_event_rd FROM overall_standings", db="elo.db",
        )
    }


def _season_snapshot():
    """Everything a rebuild rewrites, to compare incremental vs rebuilt."""
    players = {
        uid: (r["online_event_elo"], r["online_event_games"],
              round(r["online_event_rating"] or 0, 6), round(r["online_event_rd"] or 0, 6))
        for uid, r in _standings().items()
    }
    matches = [
        (r["match_id"], r["winner_elo_change"], r["loser_elo_change"],
         r["winner_avatar_elo_change"], r["loser_avatar_elo_change"])
        for r in _rows("SELECT * FROM season_match_records ORDER BY match_id")
    ]
    avatars = sorted(
        (r["user_id"], r["avatar"], r["event_elo"], r["games_played"], round(r["rating"], 6))
        for r in _rows("SELECT * FROM event_avatar_standings", db="elo.db")
    )
    return players, matches, avatars


def _rebuild():
    elo_conn, match_conn = sqlite3.connect("elo.db"), sqlite3.connect("match_records.db")
    try:
        g2.rebuild_season(elo_conn, match_conn, g2.get_event(elo_conn))
        elo_conn.commit()
        match_conn.commit()
    finally:
        elo_conn.close()
        match_conn.close()


# ── The maths ──


def _glickman_period(mu, phi, vol, opponents, tau=0.5):
    """Glickman's worked example algorithm, several games in one period."""
    g = lambda p: 1 / math.sqrt(1 + 3 * p ** 2 / math.pi ** 2)
    E = lambda m, mj, pj: 1 / (1 + math.exp(-g(pj) * (m - mj)))
    v = 1 / sum(g(pj) ** 2 * E(mu, mj, pj) * (1 - E(mu, mj, pj)) for mj, pj, _ in opponents)
    delta = v * sum(g(pj) * (s - E(mu, mj, pj)) for mj, pj, s in opponents)
    a = math.log(vol ** 2)
    f = lambda x: (math.exp(x) * (delta ** 2 - phi ** 2 - v - math.exp(x))
                   / (2 * (phi ** 2 + v + math.exp(x)) ** 2)) - (x - a) / tau ** 2
    A_, B_ = a, None
    if delta ** 2 > phi ** 2 + v:
        B_ = math.log(delta ** 2 - phi ** 2 - v)
    else:
        k = 1
        while f(a - k * tau) < 0:
            k += 1
        B_ = a - k * tau
    fA, fB = f(A_), f(B_)
    while abs(B_ - A_) > 1e-6:
        C_ = A_ + (A_ - B_) * fA / (fB - fA)
        fC = f(C_)
        if fC * fB <= 0:
            A_, fA = B_, fB
        else:
            fA /= 2
        B_, fB = C_, fC
    new_vol = math.exp(A_ / 2)
    phi_star = math.sqrt(phi ** 2 + new_vol ** 2)
    new_phi = 1 / math.sqrt(1 / phi_star ** 2 + 1 / v)
    new_mu = mu + new_phi ** 2 * sum(g(pj) * (s - E(mu, mj, pj)) for mj, pj, s in opponents)
    return new_mu, new_phi, new_vol


def test_reference_matches_glickmans_published_example():
    S = 173.7178
    opponents = [((1400 - 1500) / S, 30 / S, 1), ((1550 - 1500) / S, 100 / S, 0),
                 ((1700 - 1500) / S, 300 / S, 0)]
    mu, phi, vol = _glickman_period(0, 200 / S, 0.06, opponents)
    assert round(mu * S + 1500, 2) == pytest.approx(1464.06, abs=0.01)
    assert round(phi * S, 2) == pytest.approx(151.52, abs=0.01)
    assert vol == pytest.approx(0.05999, abs=1e-5)


@pytest.mark.parametrize("score", [1, 0])
def test_one_game_update_matches_the_reference(score):
    S = 173.7178
    mu, phi, vol = (1600 - 1500) / S, 120 / S, 0.06
    opp = ((1450 - 1500) / S, 90 / S, score)
    expected = _glickman_period(mu, phi, vol, [opp])
    got = g2._update(mu, phi, vol, opp[0], opp[1], score)
    assert got[0] == pytest.approx(expected[0], abs=1e-6)
    assert got[1] == pytest.approx(max(expected[1], g2.RD_FLOOR / S), abs=1e-6)
    assert got[2] == pytest.approx(expected[2], abs=1e-6)


def test_rd_never_drops_below_the_floor_and_grows_back_without_games():
    t = datetime.datetime(2027, 1, 1)
    me, them = g2.Rating(), g2.Rating()
    for i in range(80):
        at = (t + datetime.timedelta(hours=i)).isoformat()
        me, them = g2.play(me, them, at) if i % 2 else g2.play(them, me, at)[::-1]
    assert me.rd >= g2.RD_FLOOR - 1e-9
    later = (t + datetime.timedelta(days=60)).isoformat()
    assert g2.rd_at(me, later) > me.rd
    assert g2.rd_at(me, (t + datetime.timedelta(days=3650)).isoformat()) == g2.START_RD


def test_new_entries_move_faster_than_settled_ones():
    t = "2027-01-01T12:00:00"
    new_w, _ = g2.play(g2.Rating(), g2.Rating(), t)
    settled = g2.Rating(1500.0, g2.RD_FLOOR, 0.06, t)
    old_w, _ = g2.play(settled, settled, t)
    assert new_w.display - 1500 > old_w.display - 1500 > 0


# ── Starting a season ──


def test_start_event_records_and_locks_the_rating_system():
    event = start_new_event("Season 9", elo_mode="avatar", rating_system="glicko2")
    assert event["rating_system"] == "glicko2"
    assert get_active_event()["rating_system"] == "glicko2"
    conn = sqlite3.connect("elo.db")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE events SET rating_system = 'elo' WHERE event_id = ?", (event["event_id"],))
    finally:
        conn.close()


def test_start_event_defaults_to_elo_and_rejects_unknown_systems():
    assert start_new_event("Classic")["rating_system"] == "elo"
    with pytest.raises(ValueError):
        start_new_event("Oops", rating_system="trueskill")


# ── Reporting ──


@pytest.mark.asyncio
async def test_report_moves_glicko2_season_and_lifetime():
    event = start_new_event("Season 9", rating_system="glicko2")
    match_id = await _record()

    row = _rows("SELECT * FROM season_match_records WHERE match_id = ?", (match_id,))[0]
    assert row["event_id"] == event["event_id"] and row["rating_system"] == "glicko2"
    assert row["event_k"] is None
    s = _standings()
    assert s[A]["online_event_elo"] == 1500 + row["winner_elo_change"]
    assert s[B]["online_event_elo"] == 1500 + row["loser_elo_change"]
    assert s[A]["online_event_rd"] < g2.START_RD
    # A new entry moves much more than Elo's K=16 opening game (+8)
    assert row["winner_elo_change"] > 50
    # Lifetime moved to Glicko-2 with the first Glicko-2 season: a fresh
    # lifetime moves exactly like a fresh season entry
    assert row["lifetime_system"] == "glicko2"
    assert s[A]["online_elo"] == 1500 + row["winner_lifetime_elo_change"]
    assert row["winner_lifetime_elo_change"] == row["winner_elo_change"]


@pytest.mark.asyncio
async def test_testing_matches_are_tagged_but_not_rated():
    event = start_new_event("Season 9", rating_system="glicko2")
    match_id = await _record(match_type="testing")
    row = _rows("SELECT * FROM season_match_records WHERE match_id = ?", (match_id,))[0]
    assert row["event_id"] == event["event_id"]
    assert (row["winner_elo_change"], row["loser_elo_change"]) == (0, 0)
    assert A not in _standings() or _standings()[A]["online_event_rating"] is None


@pytest.mark.asyncio
async def test_incremental_ratings_equal_a_full_rebuild_avatar_mode():
    start_new_event("Season 9", elo_mode="avatar", rating_system="glicko2")
    games = [(A, B, "Seer", "Witch"), (B, C, "Witch", "Druid"), (A, C, "Seer", "Druid"),
             (C, A, "Druid", "Imposter"), (A, B, "Seer", "Witch"), (D, A, "Seer", "Seer")]
    for w, l, wa, la in games:
        await _record(winner_id=w, loser_id=l, winner_avatar=wa, loser_avatar=la)
    before = _season_snapshot()
    _rebuild()
    assert _season_snapshot() == before


@pytest.mark.asyncio
async def test_zero_change_glicko2_games_still_count_as_games():
    start_new_event("Season 9", rating_system="glicko2")
    match_id = await _record()
    conn = sqlite3.connect("match_records.db")
    conn.execute("UPDATE season_match_records SET winner_elo_change = 0, loser_elo_change = 0 WHERE match_id = ?",
                 (match_id,))
    conn.commit()
    conn.close()
    ladder = {e.user_id: e.games_played for e in get_event_ladder()}
    assert ladder[A] == 1 and ladder[B] == 1


# ── Fixes rebuild the season ──


@pytest.mark.asyncio
async def test_remove_match_rebuilds_the_season_without_it():
    start_new_event("Season 9", rating_system="glicko2")
    await _record(A, B)
    bad = await _record(B, C)
    await _record(C, A)
    lifetime_before = _standings()[B]["online_elo"]
    bad_row = _rows("SELECT * FROM season_match_records WHERE match_id = ?", (bad,))[0]

    remove_match_record(bad)

    after = _season_snapshot()
    _rebuild()
    assert _season_snapshot() == after  # consistent with a clean replay
    assert len(after[1]) == 2
    # B's last game is gone, so B's lifetime is back where it was before it
    assert _standings()[B]["online_elo"] == lifetime_before - bad_row["winner_lifetime_elo_change"]


@pytest.mark.asyncio
async def test_correct_match_flips_and_rebuilds():
    start_new_event("Season 9", rating_system="glicko2")
    match_id = await _record(A, B)
    await _record(A, C)

    result = correct_match_record(match_id)

    s = _standings()
    assert s[B]["online_event_elo"] > 1500
    assert result["new_winner_elo_change"] > 0 and result["new_loser_elo_change"] < 0
    after = _season_snapshot()
    _rebuild()
    assert _season_snapshot() == after


@pytest.mark.asyncio
async def test_remove_player_rebuilds_without_their_games():
    start_new_event("Season 9", rating_system="glicko2")
    await _record(A, B)
    await _record(C, A)
    await _record(B, C)

    remove_player(A, "PA")

    s = _standings()
    assert A not in s
    assert _rows("SELECT COUNT(*) AS n FROM season_match_records")[0]["n"] == 1
    # Only B beat C is left: same numbers as a fresh season with that one game
    w, l = g2.play(g2.Rating(), g2.Rating(),
                   _rows("SELECT timestamp FROM season_match_records")[0]["timestamp"])
    assert s[B]["online_event_elo"] == w.display and s[C]["online_event_elo"] == l.display


@pytest.mark.asyncio
async def test_spot_reset_survives_a_rebuild():
    event = start_new_event("Season 9", elo_mode="avatar", rating_system="glicko2")
    await _record(A, B, winner_avatar="Seer", loser_avatar="Witch")
    set_player_event_elo(B, "PB", 1700)
    set_avatar_event_elo(event["event_id"], B, "PB", "Witch", 1650)
    assert _standings()[B]["online_event_elo"] == 1700

    recalculate_event_elo()

    assert _standings()[B]["online_event_elo"] == 1700
    witch = [e for e in get_avatar_standings(event["event_id"]) if e["avatar"] == "Witch"]
    assert witch[0]["event_elo"] == 1650


@pytest.mark.asyncio
async def test_match_elo_snapshot_uses_the_stored_glicko2_change():
    start_new_event("Season 9", rating_system="glicko2")
    await _record(A, B)
    match_id = await _record(A, B)
    snap = get_current_event_match_elo_snapshot(match_id)
    s = _standings()
    assert snap["winner"]["event_after"] == s[A]["online_event_elo"]
    assert snap["event_k"] is None


# ── Top cut minimum ──


@pytest.mark.asyncio
async def test_top_cut_needs_eight_games_in_a_glicko2_season():
    event = start_new_event("Season 9", rating_system="glicko2")
    for _ in range(8):
        await _record(A, B)
    for _ in range(3):
        await _record(C, D)  # 3-0, very likely above B but not eligible

    ladder = get_event_ladder()
    eligible = {e.user_id for e in top_cut_eligible(ladder, get_active_event())}
    assert eligible == {A, B}
    assert C not in get_top_16_user_ids()
    qualifiers = select_top_cut(ladder, {A, B, C, D}, event=get_active_event())
    assert [q.user_id for q in qualifiers] == [A, B]
    assert event["rating_system"] == "glicko2"


@pytest.mark.asyncio
async def test_elo_seasons_have_no_top_cut_minimum():
    start_new_event("Classic")
    await _record(C, D)
    ladder = get_event_ladder()
    assert len(top_cut_eligible(ladder, get_active_event())) == 2


# ── End of season ──


@pytest.mark.asyncio
async def test_glicko2_season_end_keeps_matches_and_archives_standings():
    event = start_new_event("Season 9", rating_system="glicko2")
    await _record(A, B)
    summary = end_current_event()
    assert summary["total_matches"] == 1
    assert _rows("SELECT COUNT(*) AS n FROM season_match_records")[0]["n"] == 1
    assert _rows("SELECT COUNT(*) AS n FROM match_records_archive")[0]["n"] == 0
    archived = _rows("SELECT * FROM event_standings_archive WHERE event_id = ?",
                     (event["event_id"],), db="elo.db")
    assert {r["user_id"] for r in archived} == {A, B}


@pytest.mark.asyncio
async def test_later_season_fixes_leave_an_ended_glicko2_season_alone():
    start_new_event("Season 9", rating_system="glicko2")
    old = await _record(A, B)
    start_new_event("Season 10", rating_system="glicko2")  # ends Season 9
    await _record(B, A)

    with pytest.raises(ValueError):
        remove_match_record(old)
    remove_player(A, "PA")
    assert _rows("SELECT match_id FROM season_match_records") == [{"match_id": old}]


@pytest.mark.asyncio
async def test_an_elo_season_after_glicko2_stays_in_the_season_table():
    start_new_event("Season 9", rating_system="glicko2")
    kept = await _record(A, B)
    start_new_event("Season 10")  # an Elo season after a Glicko-2 one
    newer = await _record(B, A)
    end_current_event()
    # Once the season table exists every later season stays in it, Elo or not
    assert _rows("SELECT match_id, rating_system FROM season_match_records ORDER BY match_id") == [
        {"match_id": kept, "rating_system": "glicko2"}, {"match_id": newer, "rating_system": "elo"}]
    assert _rows("SELECT COUNT(*) AS n FROM match_records_archive")[0]["n"] == 0


# ── The Season 9+ match table ──


def _match_conn():
    conn = sqlite3.connect("match_records.db")
    conn.row_factory = sqlite3.Row
    return conn


@pytest.mark.asyncio
async def test_first_glicko2_season_creates_the_season_table_and_keeps_ids_going():
    from utils.match_tables import live_matches

    start_new_event("Season 8")
    old = await _record(A, B)
    end_current_event()  # Season 8 archived: match_records is empty again
    assert live_matches() == "match_records"
    between = await _record(C, D)  # reported between seasons, no event

    start_new_event("Season 9", rating_system="glicko2")
    assert live_matches() == "season_match_records"
    first = await _record(A, B)

    assert _rows("SELECT COUNT(*) AS n FROM match_records")[0]["n"] == 0
    assert [r["match_id"] for r in _rows("SELECT match_id FROM season_match_records ORDER BY match_id")] == [
        between, first]
    assert old < between < first


@pytest.mark.asyncio
async def test_season_table_continues_above_archived_ids():
    start_new_event("Season 8")
    for _ in range(3):
        last = await _record(A, B)
    end_current_event()
    conn = _match_conn()
    conn.execute("DELETE FROM sqlite_sequence WHERE name = 'match_records'")  # lose the counter
    conn.commit()
    conn.close()

    start_new_event("Season 9", rating_system="glicko2")
    assert await _record(A, B) > last


def test_season_table_picks_up_columns_added_to_match_records():
    start_new_event("Season 9", rating_system="glicko2")
    conn = _match_conn()
    conn.execute("ALTER TABLE match_records ADD COLUMN some_new_field TEXT")
    conn.execute("CREATE INDEX idx_some_new_field ON match_records(some_new_field)")
    g2.ensure_match_schema(conn)
    conn.commit()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(season_match_records)")}
    idx = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='season_match_records'")}
    conn.close()
    assert "some_new_field" in cols and "season_idx_some_new_field" in idx


def test_an_elo_season_does_not_create_the_season_table():
    start_new_event("Season 9")
    assert not _rows("SELECT name FROM sqlite_master WHERE name = 'season_match_records'")


# ── Lifetime: frozen as Legacy ELO, then Glicko-2 ──


def _legacy():
    return {r["user_id"]: r["legacy_online_elo"] for r in _rows(
        "SELECT user_id, legacy_online_elo FROM overall_standings", db="elo.db")}


def _lifetime_snapshot():
    players = {
        r["user_id"]: (r["online_elo"], r["online_games"], round(r["online_rating"] or 0, 6))
        for r in _rows("SELECT * FROM overall_standings", db="elo.db")
    }
    matches = [
        (r["match_id"], r["winner_lifetime_elo_change"], r["loser_lifetime_elo_change"])
        for r in _rows("SELECT * FROM season_match_records ORDER BY match_id")
    ]
    return players, matches


@pytest.mark.asyncio
async def test_first_glicko2_season_freezes_lifetime_as_legacy_and_restarts_it():
    start_new_event("Season 8")
    await _record(A, B)
    await _record(A, C)
    elo_lifetime = {uid: r["online_elo"] for uid, r in _standings().items()}
    assert elo_lifetime[A] > 1500

    start_new_event("Season 9", rating_system="glicko2")

    assert _legacy() == elo_lifetime
    assert {r["online_elo"] for r in _standings().values()} == {1500}

    # Season 10 carries lifetime on and never re-freezes it
    await _record(B, A)
    after_s9 = _standings()[B]["online_elo"]
    start_new_event("Season 10", rating_system="glicko2")
    assert _legacy() == elo_lifetime
    assert _standings()[B]["online_elo"] == after_s9
    assert _rows("SELECT online_games FROM overall_standings WHERE user_id = ?", (B,), db="elo.db")[0][
        "online_games"] == 1


@pytest.mark.asyncio
async def test_lifetime_rebuild_matches_incremental_across_seasons_and_elo_seasons():
    start_new_event("Season 9", rating_system="glicko2")
    for w, l in ((A, B), (B, C), (C, A), (A, D)):
        await _record(w, l)
    start_new_event("Season 10")  # an Elo season after the switch: lifetime stays Glicko-2
    for w, l in ((D, A), (B, A), (C, D)):
        await _record(w, l)
    assert {r["lifetime_system"] for r in _rows("SELECT lifetime_system FROM season_match_records")} == {
        "glicko2"}

    before = _lifetime_snapshot()
    elo_conn, match_conn = sqlite3.connect("elo.db"), sqlite3.connect("match_records.db")
    g2.rebuild_lifetime(elo_conn, match_conn)
    elo_conn.commit()
    match_conn.commit()
    elo_conn.close()
    match_conn.close()
    assert _lifetime_snapshot() == before


@pytest.mark.asyncio
async def test_remove_match_rebuilds_lifetime_across_seasons():
    start_new_event("Season 9", rating_system="glicko2")
    bad = await _record(A, B)
    start_new_event("Season 10", rating_system="glicko2")
    await _record(B, C)
    with pytest.raises(ValueError):
        remove_match_record(bad)  # ended season: left alone
    current = await _record(C, A)
    remove_match_record(current)

    # Lifetime equals a replay of the two games that are left
    a, b = g2.play(g2.Rating(), g2.Rating(), _rows(
        "SELECT timestamp FROM season_match_records WHERE match_id = ?", (bad,))[0]["timestamp"])
    b, c = g2.play(b, g2.Rating(), _rows(
        "SELECT timestamp FROM season_match_records WHERE match_id != ?", (bad,))[0]["timestamp"])
    s = _standings()
    assert (s[A]["online_elo"], s[B]["online_elo"], s[C]["online_elo"]) == (a.display, b.display, c.display)


@pytest.mark.asyncio
async def test_ladder_stakes_scale_the_glicko2_lifetime_move():
    start_new_event("Season 9", rating_system="glicko2")
    match_id = await _record(A, B, elo_multiplier_winner=2.0, elo_multiplier_loser=0.5)
    row = _rows("SELECT * FROM season_match_records WHERE match_id = ?", (match_id,))[0]
    plain_w, plain_l = row["winner_elo_change"], row["loser_elo_change"]  # season ignores stakes
    assert abs(row["winner_lifetime_elo_change"] - 2 * plain_w) <= 1
    assert abs(row["loser_lifetime_elo_change"] - 0.5 * plain_l) <= 1
    before = _lifetime_snapshot()
    _rebuild_lifetime()
    assert _lifetime_snapshot() == before


def _rebuild_lifetime():
    elo_conn, match_conn = sqlite3.connect("elo.db"), sqlite3.connect("match_records.db")
    try:
        g2.rebuild_lifetime(elo_conn, match_conn)
        elo_conn.commit()
        match_conn.commit()
    finally:
        elo_conn.close()
        match_conn.close()


@pytest.mark.asyncio
async def test_top_cut_report_moves_glicko2_lifetime_only_and_survives_rebuilds():
    from services.elo_service import rate_top_cut_lifetime

    start_new_event("Season 9", rating_system="glicko2")
    match_id = await _record(A, B, match_type="testing")
    w_new, w_change, l_new, l_change = rate_top_cut_lifetime(match_id, A, "PA", B, "PB")
    s = _standings()
    assert s[A]["online_elo"] == w_new == 1500 + w_change and w_change > 0
    assert s[A]["online_event_rating"] is None  # season untouched
    before = _lifetime_snapshot()
    _rebuild_lifetime()
    assert _lifetime_snapshot() == before


def test_elo_lifetime_stays_elo_until_a_glicko2_season():
    start_new_event("Season 8")
    conn = sqlite3.connect("elo.db")
    try:
        assert not g2.lifetime_is_glicko2(conn)
    finally:
        conn.close()


# ── The web app's copy ──


def test_web_app_copy_is_identical():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bot = os.path.join(here, "services", "glicko2_season.py")
    web = os.path.join(os.path.dirname(here), "web-app", "services", "glicko2_season.py")
    assert filecmp.cmp(bot, web, shallow=False), "update web-app/services/glicko2_season.py too"


# ── Standing before each game (skill matrices, history) ──


def _snapshots(table="season_match_records"):
    cols = ", ".join(g2.SNAPSHOT_COLUMNS)
    return [tuple(r.values()) for r in _rows(f"SELECT match_id, {cols} FROM {table} ORDER BY match_id")]


@pytest.mark.asyncio
async def test_each_game_stores_both_ratings_and_ranks_before_it():
    start_new_event("Season 9", elo_mode="avatar", rating_system="glicko2")
    for _ in range(8):
        await _record(A, B, winner_avatar="Seer", loser_avatar="Witch")
    before = _standings()
    match_id = await _record(C, A, winner_avatar="Druid", loser_avatar="Seer")
    row = _rows("SELECT * FROM season_match_records WHERE match_id = ?", (match_id,))[0]

    assert row["loser_event_before"] == before[A]["online_event_elo"]
    assert row["loser_event_rank"] == 1          # A is the top settled player
    assert row["winner_event_before"] == 1500 and row["winner_event_rank"] is None  # C: new, unranked
    assert row["loser_avatar_before"] == before[A]["online_event_elo"]  # A only ever played Seer
    assert row["loser_avatar_rank"] == 1 and row["winner_avatar_rank"] is None
    assert row["loser_lifetime_before"] == before[A]["online_elo"]


@pytest.mark.asyncio
async def test_rebuild_rewrites_the_same_standings_before_each_game():
    start_new_event("Season 9", elo_mode="avatar", rating_system="glicko2")
    games = [(A, B, "Seer", "Witch")] * 8 + [(C, D, "Druid", "Imposter"), (B, A, "Witch", "Seer"),
                                             (A, C, "Seer", "Druid")]
    for w, l, wa, la in games:
        await _record(winner_id=w, loser_id=l, winner_avatar=wa, loser_avatar=la)
    recorded = _snapshots()
    _rebuild()
    _rebuild_lifetime()
    assert _snapshots() == recorded


@pytest.mark.asyncio
async def test_elo_seasons_store_the_standing_before_each_game_too():
    start_new_event("Season 8")
    await _record(A, B)
    match_id = await _record(A, C)
    row = _rows("SELECT * FROM match_records WHERE match_id = ?", (match_id,))[0]
    assert row["winner_event_before"] > 1500 and row["winner_event_rank"] == 1
    assert row["loser_event_before"] == 1500 and row["loser_event_rank"] is None


# ── Lifetime avatar ELO ──


def _avatar_lifetime():
    return {(r["user_id"], r["avatar"]): (r["elo"], r["games"], round(r["rating"], 6))
            for r in _rows("SELECT * FROM lifetime_avatar_standings", db="elo.db")}


@pytest.mark.asyncio
async def test_lifetime_avatar_elo_carries_across_seasons_and_rebuilds():
    start_new_event("Season 9", elo_mode="avatar", rating_system="glicko2")
    await _record(A, B, winner_avatar="Seer", loser_avatar="Witch")
    await _record(A, C, winner_avatar="Druid", loser_avatar="Witch")
    start_new_event("Season 10", elo_mode="avatar", rating_system="glicko2")
    match_id = await _record(B, A, winner_avatar="Witch", loser_avatar="Seer")

    entries = _avatar_lifetime()
    assert entries[(A, "Seer")][1] == 2 and entries[(A, "Druid")][1] == 1  # not reset by Season 10
    row = _rows("SELECT * FROM season_match_records WHERE match_id = ?", (match_id,))[0]
    assert row["loser_avatar_lifetime_after"] == entries[(A, "Seer")][0]
    assert row["winner_avatar_lifetime_games"] == 2
    # Season 10's avatar entry started fresh; the lifetime one didn't
    assert row["winner_avatar_lifetime_before"] != row["winner_avatar_before"]

    before = (_avatar_lifetime(), _snapshots())
    _rebuild_lifetime()
    assert (_avatar_lifetime(), _snapshots()) == before


@pytest.mark.asyncio
async def test_removing_a_match_rebuilds_lifetime_avatar_elo():
    start_new_event("Season 9", elo_mode="avatar", rating_system="glicko2")
    await _record(A, B, winner_avatar="Seer", loser_avatar="Witch")
    bad = await _record(A, B, winner_avatar="Seer", loser_avatar="Witch")
    remove_match_record(bad)
    assert _avatar_lifetime()[(A, "Seer")][1] == 1
