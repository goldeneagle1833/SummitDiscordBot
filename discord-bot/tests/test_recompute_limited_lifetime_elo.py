"""Tests for scripts/recompute_limited_lifetime_elo.py."""

import importlib.util
import os
import sqlite3

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "scripts", "recompute_limited_lifetime_elo.py")
spec = importlib.util.spec_from_file_location("recompute_limited_lifetime_elo", SCRIPT)
recompute = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recompute)
update_elo = recompute.update_elo

MATCH_COLS = """reporter_id INTEGER, winner_id INTEGER, winner_display_name TEXT,
    loser_id INTEGER, loser_display_name TEXT, timestamp TEXT,
    winner_run_id INTEGER, loser_run_id INTEGER"""
RUN_COLS = """user_id INTEGER, user_display_name TEXT, status TEXT,
    created_at TEXT, completed_at TEXT"""


def _make_dbs(tmp_path, live_matches, archived_matches, live_runs=(), archived_runs=(), lifetime=None):
    m = sqlite3.connect(tmp_path / "match_records.db")
    m.execute(f"CREATE TABLE limited_match_records (match_id INTEGER PRIMARY KEY, {MATCH_COLS})")
    m.execute(f"CREATE TABLE limited_match_records_archive (original_match_id INTEGER, {MATCH_COLS})")
    m.execute(f"CREATE TABLE limited_arena_runs (run_id INTEGER PRIMARY KEY, {RUN_COLS})")
    m.execute(f"CREATE TABLE limited_arena_runs_archive (original_run_id INTEGER, {RUN_COLS})")
    m.executemany("INSERT INTO limited_match_records VALUES (?,?,?,?,?,?,?,?,?)", live_matches)
    m.executemany("INSERT INTO limited_match_records_archive VALUES (?,?,?,?,?,?,?,?,?)", archived_matches)
    m.executemany("INSERT INTO limited_arena_runs VALUES (?,?,?,?,?,?)", live_runs)
    m.executemany("INSERT INTO limited_arena_runs_archive VALUES (?,?,?,?,?,?)", archived_runs)
    m.commit()
    m.close()

    e = sqlite3.connect(tmp_path / "elo.db")
    e.execute("""CREATE TABLE limited_elo (user_id INTEGER PRIMARY KEY, user_display_name TEXT,
                 elo INTEGER NOT NULL DEFAULT 1500, lifetime_elo INTEGER NOT NULL DEFAULT 1500)""")
    for uid, name, lt in (lifetime or []):
        e.execute("INSERT INTO limited_elo VALUES (?, ?, 1500, ?)", (uid, name, lt))
    e.commit()
    e.close()


def _lifetime(tmp_path):
    e = sqlite3.connect(tmp_path / "elo.db")
    rows = dict(e.execute("SELECT user_id, lifetime_elo FROM limited_elo").fetchall())
    e.close()
    return rows


def test_replays_across_seasons_from_lifetime_ratings(tmp_path):
    # Season 1 (archived): A beats B twice. Season 2 (live): A beats B again.
    archived = [
        (1, 1, 1, "A", 2, "B", "2026-09-01T10:00:00", None, None),
        (2, 1, 1, "A", 2, "B", "2026-09-02T10:00:00", None, None),
    ]
    live = [(3, 1, 1, "A", 2, "B", "2026-10-01T10:00:00", None, None)]
    # Stored (buggy) values: lifetime moved by the season delta of +16 on the reset ladder
    _make_dbs(tmp_path, live, archived, lifetime=[(1, "A", 9999), (2, "B", 1)])

    recompute.main(["--db-dir", str(tmp_path), "--apply"])

    a, b = 1500, 1500
    for _ in range(3):
        a = update_elo(a, b, True)
        b = update_elo(b, a, False)  # bot reports are sequential
    assert _lifetime(tmp_path) == {1: a, 2: b}


def test_api_reports_are_simultaneous(tmp_path):
    _make_dbs(tmp_path, [(1, 0, 1, "A", 2, "B", "2026-10-01T10:00:00", None, None)], [])
    elo, _ = recompute.replay(*recompute.load_history(tmp_path / "match_records.db"))
    assert elo == {1: 1516, 2: 1484}


def test_forfeit_phantom_losses_only_for_unplayed_losses(tmp_path):
    # Run 7 recorded one real loss, then forfeited: one phantom loss
    live = [(1, 2, 2, "B", 1, "A", "2026-10-01T10:00:00", None, 7)]
    runs = [(7, 1, "A", "forfeited", "2026-10-01T09:00:00", "2026-10-02T10:00:00")]
    _make_dbs(tmp_path, live, [], live_runs=runs)

    elo, _ = recompute.replay(*recompute.load_history(tmp_path / "match_records.db"))
    winner_after = update_elo(1500, 1500, True)
    after_loss = update_elo(1500, winner_after, False)  # sequential bot report
    assert elo[1] == update_elo(after_loss, after_loss, False)


def test_dry_run_writes_nothing_and_unknown_players_untouched(tmp_path):
    _make_dbs(tmp_path, [(1, 1, 1, "A", 2, "B", "2026-10-01T10:00:00", None, None)], [],
              lifetime=[(1, "A", 1600), (99, "Ghost", 1700)])

    recompute.main(["--db-dir", str(tmp_path)])
    assert _lifetime(tmp_path) == {1: 1600, 99: 1700}

    recompute.main(["--db-dir", str(tmp_path), "--apply"])
    assert _lifetime(tmp_path)[99] == 1700
    assert _lifetime(tmp_path)[1] == 1516
