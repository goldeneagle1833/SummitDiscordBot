"""Recompute lifetime Limited ELO from the full match history.

Lifetime Limited ELO used to be moved by each match's *season* ELO change
instead of being calculated from the players' lifetime ratings. This script
replays every limited match (archived seasons + the live season) and every
forfeit penalty in order, calculating lifetime ELO from scratch with K=32.

Season ELO is not touched.

Usage (run from the discord-bot directory on the server):
    python scripts/recompute_limited_lifetime_elo.py            # dry run: report only
    python scripts/recompute_limited_lifetime_elo.py --apply    # write changes

--apply copies elo.db to elo.db.bak-<timestamp> before writing.

Replay rules, matching how the live code updates lifetime:
- Bot-reported matches update the winner first, then the loser against the
  winner's new rating (sequential). API-reported matches (reporter_id 0) use
  both players' pre-match ratings (simultaneous).
- Forfeited runs get phantom losses for each loss the run had not reached
  (max losses 2 minus losses recorded in matches for that run), applied at
  the run's completed_at time against the player's own lifetime rating.
- Players in limited_elo that never appear in the history are left alone.
"""

import argparse
import datetime
import os
import shutil
import sqlite3
import sys

K = 32
START = 1500
MAX_ARENA_LOSSES = 2


def update_elo(player_elo, opponent_elo, did_win, k=K):
    """Standard ELO calculation (matches elo_service.update_elo)."""
    expected = 1 / (1 + 10 ** ((opponent_elo - player_elo) / 400))
    return round(player_elo + k * ((1 if did_win else 0) - expected))


def _table_exists(cur, name):
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def load_history(match_db_path):
    """Return (matches, forfeits) as chronologically sortable event dicts."""
    conn = sqlite3.connect(match_db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    match_cols = ("reporter_id, winner_id, winner_display_name, loser_id, "
                  "loser_display_name, timestamp, winner_run_id, loser_run_id")
    matches = []
    if _table_exists(cur, "limited_match_records_archive"):
        cur.execute(f"SELECT original_match_id AS match_id, {match_cols} "
                    "FROM limited_match_records_archive")
        matches += [dict(r) for r in cur.fetchall()]
    if _table_exists(cur, "limited_match_records"):
        cur.execute(f"SELECT match_id, {match_cols} FROM limited_match_records")
        matches += [dict(r) for r in cur.fetchall()]

    run_cols = "user_id, user_display_name, status, completed_at, created_at"
    runs = []
    if _table_exists(cur, "limited_arena_runs_archive"):
        cur.execute(f"SELECT original_run_id AS run_id, {run_cols} "
                    "FROM limited_arena_runs_archive WHERE status = 'forfeited'")
        runs += [dict(r) for r in cur.fetchall()]
    if _table_exists(cur, "limited_arena_runs"):
        cur.execute(f"SELECT run_id, {run_cols} FROM limited_arena_runs "
                    "WHERE status = 'forfeited'")
        runs += [dict(r) for r in cur.fetchall()]
    conn.close()

    # A run is archived once, so de-duplicate by run_id defensively
    runs = list({r["run_id"]: r for r in runs}.values())

    losses_by_run = {}
    for m in matches:
        if m["loser_run_id"]:
            losses_by_run[m["loser_run_id"]] = losses_by_run.get(m["loser_run_id"], 0) + 1

    forfeits = []
    for r in runs:
        phantom = MAX_ARENA_LOSSES - losses_by_run.get(r["run_id"], 0)
        if phantom > 0:
            forfeits.append({**r, "phantom_losses": phantom})
    return matches, forfeits


def replay(matches, forfeits):
    """Replay history and return ({user_id: lifetime_elo}, {user_id: name})."""
    events = []
    for m in matches:
        events.append((m["timestamp"] or "", 0, m["match_id"] or 0, "match", m))
    for f in forfeits:
        when = f["completed_at"] or f["created_at"] or ""
        events.append((when, 1, f["run_id"], "forfeit", f))
    events.sort(key=lambda e: e[:3])

    elo, names = {}, {}
    for _, _, _, kind, e in events:
        if kind == "match":
            w, l = e["winner_id"], e["loser_id"]
            names[w], names[l] = e["winner_display_name"], e["loser_display_name"]
            w_before, l_before = elo.get(w, START), elo.get(l, START)
            elo[w] = update_elo(w_before, l_before, True)
            # API reports (reporter_id 0) are simultaneous; bot reports are sequential
            opponent = w_before if e["reporter_id"] == 0 else elo[w]
            elo[l] = update_elo(l_before, opponent, False)
        else:
            uid = e["user_id"]
            names[uid] = e["user_display_name"]
            before = elo.get(uid, START)
            current = before
            for _ in range(e["phantom_losses"]):
                current = update_elo(current, before, False)
            elo[uid] = current
    return elo, names


def main(argv=None):
    parser = argparse.ArgumentParser(description="Recompute lifetime Limited ELO")
    parser.add_argument("--apply", action="store_true", help="Write changes (default is a dry run)")
    parser.add_argument("--db-dir", default=".", help="Directory containing elo.db and match_records.db")
    args = parser.parse_args(argv)

    elo_path = os.path.join(args.db_dir, "elo.db")
    match_path = os.path.join(args.db_dir, "match_records.db")
    for path in (elo_path, match_path):
        if not os.path.exists(path):
            sys.exit(f"Missing database: {path}")

    matches, forfeits = load_history(match_path)
    new_elo, names = replay(matches, forfeits)
    print(f"Replayed {len(matches)} matches and {len(forfeits)} forfeited runs "
          f"for {len(new_elo)} players.\n")

    conn = sqlite3.connect(elo_path)
    cur = conn.cursor()
    cur.execute("SELECT user_id, user_display_name, lifetime_elo FROM limited_elo")
    current = {row[0]: (row[1], row[2]) for row in cur.fetchall()}

    changes = []
    for uid, value in new_elo.items():
        old = current.get(uid, (names.get(uid), None))[1]
        if old != value:
            changes.append((uid, current.get(uid, (names.get(uid),))[0] or names.get(uid), old, value))
    changes.sort(key=lambda c: -abs((c[3]) - (c[2] if c[2] is not None else START)))

    print(f"{'Player':<28}{'Current':>9}{'Corrected':>11}{'Diff':>7}")
    for _, name, old, value in changes:
        old_str = str(old) if old is not None else "-"
        diff = value - (old if old is not None else START)
        print(f"{str(name)[:27]:<28}{old_str:>9}{value:>11}{diff:>+7}")
    print(f"\n{len(changes)} of {len(new_elo)} players would change.")

    untouched = [(uid, n, lt) for uid, (n, lt) in current.items() if uid not in new_elo and lt != START]
    if untouched:
        print(f"\nNot in match history, left unchanged ({len(untouched)}):")
        for _, n, lt in untouched:
            print(f"  {n}: {lt}")

    if not args.apply:
        print("\n[DRY RUN] No changes written. Re-run with --apply to save.")
        conn.close()
        return changes

    backup = f"{elo_path}.bak-{datetime.datetime.now():%Y%m%d-%H%M%S}"
    conn.close()
    shutil.copy2(elo_path, backup)
    print(f"\nBacked up elo.db to {backup}")

    conn = sqlite3.connect(elo_path)
    cur = conn.cursor()
    for uid, name, _, value in changes:
        cur.execute("UPDATE limited_elo SET lifetime_elo = ? WHERE user_id = ?", (value, uid))
        if cur.rowcount == 0:
            cur.execute(
                "INSERT INTO limited_elo (user_id, user_display_name, elo, lifetime_elo) "
                "VALUES (?, ?, 1500, ?)",
                (uid, name, value),
            )
    conn.commit()
    conn.close()
    print(f"Updated lifetime ELO for {len(changes)} players.")
    return changes


if __name__ == "__main__":
    main()
