"""Skill matrices and the profile history use each player's rating at the time of the game.

Seasons 1-8 sit in match_records_archive with no stored pre-game ratings; from
the first Glicko-2 season every game goes to season_match_records with each
side's standing before it (rebuild_season / rebuild_lifetime fill them in).
"""

import json
import sqlite3

import pytest

from services import glicko2_season as g2
from tests.conftest import seed_elo_data

EVENT_ID = 9
OLD_EVENT = 8
GLICKO_GAMES = 12  # per pairing; the first 8 are provisional


def _deck(avatar):
    return json.dumps({"avatar": [{"name": avatar}]})


def _start_glicko_season(elo_db):
    conn = sqlite3.connect(str(elo_db))
    conn.execute(
        "INSERT INTO events (event_id, event_name, start_date, is_active, elo_mode, rating_system) "
        "VALUES (?, 'Season 8', '2026-09-01T00:00:00', 0, 'player', 'elo')",
        (OLD_EVENT,),
    )
    conn.execute(
        "INSERT INTO events (event_id, event_name, start_date, is_active, elo_mode, rating_system) "
        "VALUES (?, 'Season 9', '2027-01-01T00:00:00', 1, 'player', 'glicko2')",
        (EVENT_ID,),
    )
    g2.freeze_lifetime(conn, "2027-01-01T00:00:00")
    conn.commit()
    conn.close()


def _make_archive(conn):
    """match_records_archive in the live layout, plus the archive's own column."""
    conn.execute("CREATE TABLE match_records_archive AS SELECT * FROM match_records WHERE 0")
    conn.execute("ALTER TABLE match_records_archive ADD COLUMN original_match_id INTEGER")


def _patch_avatars(monkeypatch, elo_db, match_db):
    """Point the avatar routes at the test databases, with every game released."""
    import routes.api.avatars as avatars
    monkeypatch.setattr(avatars, "ELO_DB_PATH", elo_db)
    monkeypatch.setattr(avatars, "MATCH_RECORDS_DB_PATH", match_db)
    # The public pages hold back recent games until their batch is released;
    # these seasons are dated after it
    monkeypatch.setattr(avatars, "released_connection", lambda path: sqlite3.connect(str(path)))
    avatars.reset_rows_cache()
    return avatars


def _insert(conn, table, winner, loser, ts, **cols):
    base = {
        "winner_id": winner, "winner_display_name": f"P{winner}",
        "losser_id": loser, "losser_display_name": f"P{loser}",
        "winner_elo_change": 16, "loser_elo_change": -16,
        "timestamp": ts, "source": "Discord", "match_type": "ranked",
        "json_deck_data_winner": _deck("Sparkmage"), "json_deck_data_loser": _deck("Geomancer"),
    }
    base.update(cols)
    names = ", ".join(base)
    marks = ", ".join("?" for _ in base)
    conn.execute(f"INSERT INTO {table} ({names}) VALUES ({marks})", tuple(base.values()))


@pytest.fixture()
def seasons(app, elo_db, match_db, monkeypatch):
    """Players 1 (1700) and 2 (1400) in Season 8; then a Glicko-2 Season 9.

    Season 8: 1 beats 2 ten times (archive, nothing stored about ratings).
    Season 9: 1 and 2 play GLICKO_GAMES games (1 wins two in three), rated
    and snapshotted by the real rebuild.
    """
    avatars = _patch_avatars(monkeypatch, elo_db, match_db)

    seed_elo_data(elo_db, [
        {"user_id": "1", "name": "P1", "online_elo": 1700},
        {"user_id": "2", "name": "P2", "online_elo": 1400},
    ])
    _start_glicko_season(elo_db)

    conn = sqlite3.connect(str(match_db))
    _make_archive(conn)
    for i in range(10):
        _insert(conn, "match_records_archive", "1", "2", f"2026-09-01T12:{i:02d}:00",
                event_id=OLD_EVENT, original_match_id=i + 1,
                winner_lifetime_elo_after=1600 + i, loser_lifetime_elo_after=1400 - i)
    g2.create_season_match_table(conn)
    for i in range(GLICKO_GAMES):
        winner, loser = ("2", "1") if i % 3 == 2 else ("1", "2")
        _insert(conn, "season_match_records", winner, loser, f"2027-01-02T10:{i:02d}:00",
                event_id=EVENT_ID, rating_system="glicko2", lifetime_system="glicko2",
                json_deck_data_winner=_deck("Sparkmage" if winner == "1" else "Geomancer"),
                json_deck_data_loser=_deck("Geomancer" if winner == "1" else "Sparkmage"))
    conn.commit()
    conn.close()

    elo_conn, match_conn = sqlite3.connect(str(elo_db)), sqlite3.connect(str(match_db))
    g2.rebuild_season(elo_conn, match_conn, g2.get_event(elo_conn))
    g2.rebuild_lifetime(elo_conn, match_conn)
    elo_conn.commit()
    match_conn.commit()
    elo_conn.close()
    match_conn.close()
    yield
    avatars.reset_rows_cache()


def _season_rows(match_db):
    conn = sqlite3.connect(str(match_db))
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM season_match_records ORDER BY timestamp")]
    conn.close()
    return rows


def _settled(rows):
    """Season 9 games where both sides' season ratings were settled before the game."""
    return [r for r in rows if r["winner_event_games"] > 8 and r["loser_event_games"] > 8]


def _bracket(elo):
    return (elo // 100) * 100


# --- Skill matrices -----------------------------------------------------------

def test_the_rebuild_stores_pre_game_standings(seasons, match_db):
    rows = _season_rows(match_db)
    assert len(rows) == GLICKO_GAMES
    assert all(r["winner_event_before"] is not None for r in rows)
    # Today's season rating is not what they had before the ninth game
    assert len(_settled(rows)) == GLICKO_GAMES - 8


def test_bracket_matrix_uses_pre_game_ratings_and_skips_provisional_games(client, seasons, match_db):
    data = client.get("/api/avatars/elo-bracket-matrix?source=discord").get_json()
    # 10 old games on today's ratings, the 4 settled Season 9 games on stored ones,
    # the 8 provisional ones left out
    assert data["games"] == 10 + GLICKO_GAMES - 8
    assert data["pre_match_games"] == GLICKO_GAMES - 8


def test_avatar_elo_matrix_buckets_by_rating_then(client, seasons, match_db):
    resp = client.get("/api/avatar/Sparkmage/elo-matrix?source=discord")
    assert resp.status_code == 200
    data = resp.get_json()

    expected = {}
    # Old games: Legacy ELO (today's rating for Seasons 1-8): 1700 vs 1400
    expected[(1700, 1400)] = {"wins": 10, "losses": 0}
    for r in _settled(_season_rows(match_db)):
        sparkmage_won = r["winner_id"] == "1"
        mine = r["winner_event_before"] if sparkmage_won else r["loser_event_before"]
        theirs = r["loser_event_before"] if sparkmage_won else r["winner_event_before"]
        cell = expected.setdefault((_bracket(mine), _bracket(theirs)), {"wins": 0, "losses": 0})
        cell["wins" if sparkmage_won else "losses"] += 1

    got = {}
    for row in data["matrix"]:
        for opp, cell in zip(data["brackets"], row["cells"]):
            if cell["total"]:
                got[(row["player_bracket"], opp)] = {"wins": cell["wins"], "losses": cell["losses"]}
    assert got == expected


def test_avatar_elo_breakdown_buckets_each_side_by_rating_then(client, seasons, match_db):
    resp = client.get("/api/avatars/elo-breakdown?source=discord")
    assert resp.status_code == 200
    data = resp.get_json()
    spark = next(a for a in data["avatars"] if a["name"] == "Sparkmage")
    by_bracket = {b: r for b, r in zip(data["brackets"], spark["bracket_rates"]) if r["total"]}

    expected = {1700: [10, 0]}
    for r in _settled(_season_rows(match_db)):
        if r["winner_id"] == "1":
            expected.setdefault(_bracket(r["winner_event_before"]), [0, 0])[0] += 1
        else:
            expected.setdefault(_bracket(r["loser_event_before"]), [0, 0])[1] += 1
    assert {b: [r["wins"], r["losses"]] for b, r in by_bracket.items()} == expected


def test_breakdown_matches_show_rating_and_rank_then(client, seasons, match_db):
    resp = client.get("/api/avatars/elo-breakdown/matches?avatar=Sparkmage&bracket=all&source=discord")
    assert resp.status_code == 200
    matches = resp.get_json()["matches"]
    old = [m for m in matches if m["timestamp"] < "2027"]
    new = [m for m in matches if m["timestamp"] >= "2027"]

    # Old games: today's (legacy) rating, no rank stored
    assert len(old) == 10
    assert all(m["player_elo"] == 1700 and m["opponent_elo"] == 1400 for m in old)
    assert all(m["player_rank_then"] is None and m["opponent_rank_then"] is None for m in old)

    # Season 9: provisional games carry no rating; settled ones the stored rating and rank
    stored = {r["timestamp"]: r for r in _season_rows(match_db)}
    assert len(new) == GLICKO_GAMES
    for m in new:
        r = stored[m["timestamp"]]
        me, them = ("winner", "loser") if m["result"] == "win" else ("loser", "winner")
        if r[f"{me}_event_games"] > 8:
            assert m["player_elo"] == r[f"{me}_event_before"]
            assert m["player_rank_then"] == r[f"{me}_event_rank"] in (1, 2)
            assert m["opponent_elo"] == r[f"{them}_event_before"]
        else:
            assert m["player_elo"] is None and m["player_rank_then"] is None

    # A bracket filter only matches settled ratings from then
    first = next(m for m in new if m["player_elo"] is not None)
    in_bracket = client.get(
        f"/api/avatars/elo-breakdown/matches?avatar=Sparkmage&bracket={_bracket(first['player_elo'])}"
    ).get_json()["matches"]
    assert in_bracket and all(_bracket(m["player_elo"]) == _bracket(first["player_elo"]) for m in in_bracket)


def test_old_rows_keep_their_brackets(client, elo_db, match_db, monkeypatch):
    """No Glicko-2 season yet: every view reads exactly as before (today's `elo`)."""
    avatars = _patch_avatars(monkeypatch, elo_db, match_db)
    conn = sqlite3.connect(str(elo_db))
    conn.execute("ALTER TABLE overall_standings ADD COLUMN elo INTEGER")  # live schema column
    conn.execute("INSERT INTO overall_standings (user_id, elo, online_elo) VALUES ('1', 1650, 1900), ('2', 1450, 1100)")
    conn.commit()
    conn.close()
    conn = sqlite3.connect(str(match_db))
    for i in range(10):
        _insert(conn, "match_records", "1", "2", f"2026-09-01T12:{i:02d}:00")
    conn.commit()
    conn.close()

    matrix = client.get("/api/avatar/Sparkmage/elo-matrix").get_json()
    assert matrix["brackets"] == [1400, 1600]
    assert matrix["matrix"][0]["total"]["wins"] == 10
    breakdown = client.get("/api/avatars/elo-breakdown").get_json()
    spark = next(a for a in breakdown["avatars"] if a["name"] == "Sparkmage")
    assert spark["bracket_rates"][breakdown["brackets"].index(1600)]["wins"] == 10
    matches = client.get("/api/avatars/elo-breakdown/matches?avatar=Geomancer&bracket=1400").get_json()["matches"]
    assert len(matches) == 10 and all(m["opponent_elo"] == 1650 for m in matches)
    bracket_matrix = client.get("/api/avatars/elo-bracket-matrix").get_json()
    assert bracket_matrix["games"] == 10 and bracket_matrix["pre_match_games"] == 0
    avatars.reset_rows_cache()


# --- Profile: win rate by opponent rating, and the ELO history chart ---------

def test_profile_brackets_use_the_opponents_rating_then(admin_session, seasons, match_db):
    data = admin_session.get("/api/player/1?event=lifetime").get_json()
    got = {b["bracket"]: (b["wins"], b["losses"]) for b in data["elo_vs_brackets"]}

    def label(elo):
        return "1199 or less" if elo < 1200 else "1700+" if elo >= 1700 else f"{_bracket(elo)}-{_bracket(elo) + 99}"

    expected = {"1400-1499": [10, 0]}  # Season 8: opponent's Legacy ELO
    for r in _season_rows(match_db):
        won = r["winner_id"] == "1"
        side = "loser" if won else "winner"
        if r[f"{side}_event_games"] <= 8:
            continue  # opponent still provisional then: no bracket
        cell = expected.setdefault(label(r[f"{side}_event_before"]), [0, 0])
        cell[0 if won else 1] += 1
    assert got == {k: tuple(v) for k, v in expected.items()}


def test_elo_history_marks_each_points_era(admin_session, seasons, match_db):
    history = admin_session.get("/api/player/1?event=lifetime").get_json()["elo_history"]
    legacy = [p for p in history if p["era"] == "legacy"]
    glicko = [p for p in history if p["era"] == "glicko2"]

    # Seasons 1-8 points are as they were: stored Elo lifetime after each game
    assert [p["elo_after"] for p in legacy] == [1600 + i for i in range(10)]
    assert all(p["elo_change"] == 16 for p in legacy)

    # Glicko-2 lifetime: first 8 games hidden, then the stored lifetime rating
    # with the lifetime change, so consecutive points add up
    rows = [r for r in _season_rows(match_db)]
    shown = rows[8:]
    assert len(glicko) == len(shown) == GLICKO_GAMES - 8
    for point, r in zip(glicko, shown):
        side = "winner" if r["winner_id"] == "1" else "loser"
        assert point["elo_after"] == r[f"{side}_lifetime_elo_after"]
        assert point["elo_change"] == r[f"{side}_lifetime_elo_change"]
    for prev, point in zip(glicko, glicko[1:]):
        assert prev["elo_after"] + point["elo_change"] == point["elo_after"]
    # Legacy points all come first: the chart can split the two eras cleanly
    assert history.index(glicko[0]) == len(legacy)


def test_past_glicko2_season_reads_the_season_table(admin_session, seasons, elo_db):
    """Season 9 ended and Season 10 runs: Season 9 is still on the profile, and not in 'current'."""
    conn = sqlite3.connect(str(elo_db))
    conn.execute("UPDATE events SET is_active = 0, end_date = '2027-02-01T00:00:00' WHERE event_id = ?",
                 (EVENT_ID,))
    conn.execute(
        "INSERT INTO events (event_id, event_name, start_date, is_active, elo_mode, rating_system) "
        "VALUES (10, 'Season 10', '2027-02-01T00:00:00', 1, 'player', 'glicko2')"
    )
    conn.commit()
    conn.close()

    past = admin_session.get(f"/api/player/1?event={EVENT_ID}").get_json()
    assert past["wins"] + past["losses"] == GLICKO_GAMES
    current = admin_session.get("/api/player/1?event=current").get_json()
    assert current["wins"] + current["losses"] == 0
    old = admin_session.get(f"/api/player/1?event={OLD_EVENT}").get_json()
    assert old["wins"] == 10


def test_avatar_season_chart_for_a_glicko2_season(elo_db, match_db, app):
    """Avatar mode on Glicko-2: provisional points dropped, game numbers kept, past season found."""
    from services.avatar_elo import get_player_avatar_elo

    seed_elo_data(elo_db, [{"user_id": "1", "name": "P1"}, {"user_id": "2", "name": "P2"}])
    conn = sqlite3.connect(str(elo_db))
    conn.execute(
        "INSERT INTO events (event_id, event_name, start_date, is_active, elo_mode, rating_system) "
        "VALUES (?, 'Season 9', '2027-01-01T00:00:00', 1, 'avatar', 'glicko2')",
        (EVENT_ID,),
    )
    g2.freeze_lifetime(conn, "2027-01-01T00:00:00")
    conn.commit()
    conn.close()
    conn = sqlite3.connect(str(match_db))
    g2.create_season_match_table(conn)
    for i in range(10):
        _insert(conn, "season_match_records", "1", "2", f"2027-01-02T10:{i:02d}:00",
                event_id=EVENT_ID, rating_system="glicko2", lifetime_system="glicko2",
                winner_avatar="Sparkmage", loser_avatar="Geomancer")
    conn.commit()
    conn.close()
    elo_conn, match_conn = sqlite3.connect(str(elo_db)), sqlite3.connect(str(match_db))
    g2.rebuild_season(elo_conn, match_conn, g2.get_event(elo_conn))
    elo_conn.commit()
    match_conn.commit()
    elo_conn.close()
    match_conn.close()

    current = get_player_avatar_elo("1", "current", elo_db_path=elo_db, match_db_path=match_db)
    points = current["history"]["Sparkmage"]
    assert [p["game"] for p in points] == [9, 10]
    assert all(isinstance(p["elo"], int) for p in points)

    # Season 9 over, Season 10 running: the past season's chart still reads its games
    conn = sqlite3.connect(str(elo_db))
    conn.execute("UPDATE events SET is_active = 0 WHERE event_id = ?", (EVENT_ID,))
    conn.execute(
        "INSERT INTO events (event_id, event_name, start_date, is_active, elo_mode, rating_system) "
        "VALUES (10, 'Season 10', '2027-02-01T00:00:00', 1, 'avatar', 'glicko2')"
    )
    conn.commit()
    conn.close()
    past = get_player_avatar_elo("1", archive_event_id=EVENT_ID, elo_db_path=elo_db, match_db_path=match_db)
    assert past["history"]["Sparkmage"] == points
    now = get_player_avatar_elo("1", "current", elo_db_path=elo_db, match_db_path=match_db)
    assert now["history"] == {}


@pytest.mark.parametrize("url", [
    "/api/avatars/elo-breakdown",
    "/api/avatars/elo-breakdown?source=all",
    "/api/avatars/elo-breakdown?source=web",
    "/api/avatars/elo-breakdown?source=Tabletop",
    "/api/avatar/Sparkmage/elo-matrix",
    "/api/avatar/Sparkmage/elo-matrix?event=current",
    "/api/avatar/Sparkmage/elo-matrix?event=9",
    "/api/avatar/Sparkmage/elo-matrix?source=web",
    "/api/avatar/Sparkmage/elo-matrix?source=Tabletop&event=season_1",
    "/api/avatars/elo-breakdown/matches?avatar=Sparkmage&bracket=1500&source=web",
])
def test_rating_views_load_for_every_source_and_event(client, seasons, url):
    """These two endpoints once returned 500 (UnboundLocalError) after a pre-game rating change."""
    assert client.get(url).status_code == 200
