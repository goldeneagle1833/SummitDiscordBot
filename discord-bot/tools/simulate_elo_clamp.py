"""
Parallel ELO Simulation Tool

Replays all match records for a date range using two formulas side-by-side:
  - "live"    : what the ELO would have been with the standard formula (no clamp)
  - "clamped" : what the ELO would have been with the K-factor clamp applied

Pulls from both match_records and match_records_archive tables.

Usage (run from repo root):
    python discord-bot/tools/simulate_elo_clamp.py --start 2025-01-01
    python discord-bot/tools/simulate_elo_clamp.py --start 2025-01-01 --end 2025-04-01
    python discord-bot/tools/simulate_elo_clamp.py --event-id 3
    python discord-bot/tools/simulate_elo_clamp.py --start 2025-01-01 --output results.csv
    python discord-bot/tools/simulate_elo_clamp.py --start 2025-01-01 --top 20
"""

import argparse
import csv
import os
import sqlite3
import sys
import datetime

# Allow importing from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Default DB directory — matches the download-databases.ps1 "latest" snapshot location
DEFAULT_DB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "pull_from_server",
    "backup",
    "latest",
)

# ---------------------------------------------------------------------------
# ELO formulas
# ---------------------------------------------------------------------------


def _update_elo_standard(
    player_elo: float, opponent_elo: float, did_win: bool, k: float = 32
) -> float:
    """Standard ELO formula with no clamp."""
    expected = 1 / (1 + 10 ** ((opponent_elo - player_elo) / 400))
    actual = 1.0 if did_win else 0.0
    return player_elo + k * (actual - expected)


def _update_elo_clamped(
    player_elo: float, opponent_elo: float, did_win: bool, k: float = 32
) -> float:
    """ELO formula with K-factor clamp for higher-rated player losses (post ramp-up only)."""
    expected = 1 / (1 + 10 ** ((opponent_elo - player_elo) / 400))
    actual = 1.0 if did_win else 0.0
    if not did_win and player_elo > opponent_elo and k == 32:
        gap = player_elo - opponent_elo
        k = k * max(0.5, 1 - (gap / 800))
    return player_elo + k * (actual - expected)


def _event_k(event_start: datetime.datetime, match_ts: datetime.datetime) -> float:
    """K-value based on days elapsed since event start (matches live logic)."""
    days = max(0, (match_ts - event_start).days)
    return min(16 + days * 2, 32)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def list_events(db_dir: str = DEFAULT_DB_DIR) -> None:
    """Print all events so the user can pick one."""
    conn = sqlite3.connect(os.path.join(db_dir, "elo.db"))
    cur = conn.cursor()
    cur.execute("SELECT event_id, event_name, start_date, end_date, is_active FROM events ORDER BY event_id")
    rows = cur.fetchall()
    conn.close()
    if not rows:
        print("No events found in elo.db.")
        return
    print(f"{'ID':>4}  {'Active':>6}  {'Start':<12}  {'End':<12}  Name")
    print("-" * 60)
    for r in rows:
        end = r[3] or "ongoing"
        active = "yes" if r[4] else "no"
        print(f"{r[0]:>4}  {active:>6}  {r[2]:<12}  {end:<12}  {r[1]}")


def load_event(event_id: int, db_dir: str = DEFAULT_DB_DIR) -> dict | None:
    """Load an event row from elo.db by ID."""
    conn = sqlite3.connect(os.path.join(db_dir, "elo.db"))
    cur = conn.cursor()
    cur.execute(
        "SELECT event_id, event_name, start_date, end_date FROM events WHERE event_id = ?",
        (event_id,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    start = datetime.datetime.fromisoformat(str(row[2]))
    end = datetime.datetime.fromisoformat(str(row[3])) if row[3] else None
    return {"event_id": row[0], "name": row[1], "start_date": start, "end_date": end}


def load_matches(
    start: datetime.datetime,
    end: datetime.datetime | None,
    db_dir: str = DEFAULT_DB_DIR,
) -> list[dict]:
    """
    Load all match records within the date range from both
    match_records and match_records_archive, ordered by timestamp ascending.
    """
    conn = sqlite3.connect(os.path.join(db_dir, "match_records.db"))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cols = "winner_id, winner_display_name, losser_id, losser_display_name, timestamp"
    params: list = [start.isoformat()]
    end_clause = ""
    if end:
        end_clause = " AND timestamp <= ?"
        params.append(end.isoformat())

    # Pull from live table
    cur.execute(
        f"SELECT {cols} FROM match_records WHERE timestamp >= ?{end_clause}",
        params,
    )
    rows = [dict(r) for r in cur.fetchall()]

    # Pull from archive table (same columns exist there)
    try:
        cur.execute(
            f"SELECT {cols} FROM match_records_archive WHERE timestamp >= ?{end_clause}",
            params,
        )
        rows += [dict(r) for r in cur.fetchall()]
    except sqlite3.OperationalError:
        pass  # archive table doesn't exist yet

    conn.close()

    # Sort combined results by timestamp
    rows.sort(key=lambda r: str(r["timestamp"]))
    return rows


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------


def simulate(
    matches: list[dict], event_start: datetime.datetime
) -> dict[str, dict]:
    """
    Replay matches with both formulas starting from ELO 1500.

    Returns a dict keyed by user_id:
        {
          user_id: {
            "display_name": str,
            "live_elo": float,
            "clamped_elo": float,
            "games": int,
            "wins": int,
          }
        }
    """
    players: dict[str, dict] = {}

    def _get(uid: str, name: str) -> dict:
        if uid not in players:
            players[uid] = {
                "display_name": name,
                "live_elo": 1500.0,
                "clamped_elo": 1500.0,
                "games": 0,
                "wins": 0,
            }
        return players[uid]

    for m in matches:
        wid = str(m["winner_id"])
        lid = str(m["losser_id"])
        w = _get(wid, m["winner_display_name"])
        l = _get(lid, m["losser_display_name"])

        try:
            ts = datetime.datetime.fromisoformat(str(m["timestamp"]))
        except (ValueError, TypeError):
            ts = event_start

        k = _event_k(event_start, ts)

        # --- Standard (live replay) ---
        w_live_new = _update_elo_standard(w["live_elo"], l["live_elo"], did_win=True, k=k)
        l_live_new = _update_elo_standard(l["live_elo"], w["live_elo"], did_win=False, k=k)

        # --- Clamped ---
        w_clamp_new = _update_elo_clamped(w["clamped_elo"], l["clamped_elo"], did_win=True, k=k)
        l_clamp_new = _update_elo_clamped(l["clamped_elo"], w["clamped_elo"], did_win=False, k=k)

        w["live_elo"] = w_live_new
        l["live_elo"] = l_live_new
        w["clamped_elo"] = w_clamp_new
        l["clamped_elo"] = l_clamp_new

        w["games"] += 1
        l["games"] += 1
        w["wins"] += 1

    return players


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def print_table(players: dict[str, dict], top: int | None = None) -> None:
    # Rank by clamped (new system) — this is the displayed order
    clamped_ranked = sorted(players.values(), key=lambda p: p["clamped_elo"], reverse=True)
    # Rank by live (old system) — used to look up old position
    live_ranked = sorted(players.values(), key=lambda p: p["live_elo"], reverse=True)
    live_rank_map = {id(p): i + 1 for i, p in enumerate(live_ranked)}

    rows = clamped_ranked[:top] if top else clamped_ranked

    header = (
        f"{'#':>3}  {'Player':<24}  {'Clamped':>7}  {'Old':>7}  "
        f"{'ELO Diff':>8}  {'Pos Chg':>7}  {'W':>4}  {'G':>4}"
    )
    print(header)
    print("-" * len(header))

    for new_rank, p in enumerate(rows, 1):
        old_rank = live_rank_map[id(p)]
        pos_change = old_rank - new_rank  # positive = moved up under new system
        elo_diff = p["clamped_elo"] - p["live_elo"]

        pos_str = f"+{pos_change}" if pos_change > 0 else str(pos_change) if pos_change < 0 else "—"
        elo_sign = "+" if elo_diff >= 0 else ""

        print(
            f"{new_rank:>3}  {p['display_name']:<24}  "
            f"{p['clamped_elo']:>7.0f}  {p['live_elo']:>7.0f}  "
            f"{elo_sign}{elo_diff:>7.0f}  {pos_str:>7}  {p['wins']:>4}  {p['games']:>4}"
        )


def write_csv(players: dict[str, dict], path: str) -> None:
    clamped_ranked = sorted(players.values(), key=lambda p: p["clamped_elo"], reverse=True)
    live_ranked = sorted(players.values(), key=lambda p: p["live_elo"], reverse=True)
    live_rank_map = {id(p): i + 1 for i, p in enumerate(live_ranked)}

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["new_rank", "display_name", "clamped_elo", "old_rank", "live_elo", "elo_diff", "pos_change", "wins", "games"],
        )
        writer.writeheader()
        for new_rank, p in enumerate(clamped_ranked, 1):
            old_rank = live_rank_map[id(p)]
            writer.writerow(
                {
                    "new_rank": new_rank,
                    "display_name": p["display_name"],
                    "clamped_elo": round(p["clamped_elo"]),
                    "old_rank": old_rank,
                    "live_elo": round(p["live_elo"]),
                    "elo_diff": round(p["clamped_elo"] - p["live_elo"]),
                    "pos_change": old_rank - new_rank,
                    "wins": p["wins"],
                    "games": p["games"],
                }
            )
    print(f"Results written to {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simulate parallel ELO (live vs clamped)"
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--event-id", type=int, default=None, help="Simulate a specific event by ID")
    group.add_argument("--start", type=str, default=None, help="Start date (YYYY-MM-DD)")

    parser.add_argument("--end", type=str, default=None, help="End date (YYYY-MM-DD), optional")
    parser.add_argument("--output", type=str, default=None, help="Write results to CSV file")
    parser.add_argument("--top", type=int, default=None, help="Show only top N players")
    parser.add_argument("--list-events", action="store_true", help="List all events and exit")
    parser.add_argument(
        "--db-dir",
        type=str,
        default=DEFAULT_DB_DIR,
        help=f"Directory containing elo.db and match_records.db (default: {DEFAULT_DB_DIR})",
    )
    args = parser.parse_args()

    db_dir = args.db_dir
    if not os.path.isdir(db_dir):
        print(f"DB directory not found: {db_dir}")
        print("Run pull_from_server/download-databases.ps1 first, or pass --db-dir <path>")
        sys.exit(1)

    if args.list_events:
        list_events(db_dir)
        sys.exit(0)

    # Resolve date range
    if args.event_id is not None:
        event = load_event(args.event_id, db_dir)
        if not event:
            print(f"Event {args.event_id} not found. Use --list-events to see available events.")
            sys.exit(1)
        start = event["start_date"]
        end = event["end_date"]
        label = f"Event: {event['name']}  (id={event['event_id']}, start={start.date()})"
    elif args.start:
        try:
            start = datetime.datetime.fromisoformat(args.start)
        except ValueError:
            print(f"Invalid --start date: {args.start}  (use YYYY-MM-DD)")
            sys.exit(1)
        end = None
        if args.end:
            try:
                end = datetime.datetime.fromisoformat(args.end)
            except ValueError:
                print(f"Invalid --end date: {args.end}  (use YYYY-MM-DD)")
                sys.exit(1)
        end_str = end.date() if end else "present"
        label = f"Date range: {start.date()} → {end_str}"
    else:
        print("Specify --start YYYY-MM-DD, --event-id N, or --list-events")
        parser.print_help()
        sys.exit(1)

    print(label)

    matches = load_matches(start, end, db_dir)
    print(f"Loaded {len(matches)} matches\n")

    if not matches:
        print("No matches found for this range.")
        sys.exit(0)

    players = simulate(matches, start)

    print_table(players, top=args.top)

    if args.output:
        write_csv(players, args.output)


if __name__ == "__main__":
    main()
