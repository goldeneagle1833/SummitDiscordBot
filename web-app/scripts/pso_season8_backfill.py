#!/usr/bin/env python3
"""One-time Season 8 backfill from Play Sorcery Online's game lookup.

Season 8 ranked games played before Summit opened every table through PSO
(and so before replay links came back) are matched to the PSO game they came
from with POST /api/internal/summit/game-lookup. Every answer is stored in
pso_game_lookups (found, not_found and ambiguous alike) so PSO is never asked
twice and pages never call it.

Steps, all from web-app/ inside the venv:

    python scripts/pso_season8_backfill.py plan                 # no network, no writes: what would be looked up
    python scripts/pso_season8_backfill.py lookup --limit 20    # ask PSO about 20 games, store the answers
    python scripts/pso_season8_backfill.py lookup               # the rest (1 request a second)
    python scripts/pso_season8_backfill.py report               # summary of stored answers
    python scripts/pso_season8_backfill.py apply                # dry run: play/draw it would fill in
    python scripts/pso_season8_backfill.py apply --write        # fill play/draw where Summit has none

``lookup`` only writes the pso_game_lookups table. Replay links show up on
profiles straight from that table, to each player only (their own view).
``apply --write`` is the only step that touches match_records, and it only
fills winner_went_first / loser_went_first where both are empty, for games
PSO matched with both players signed in and no winner disagreement. It never
changes winners, ELO or avatars.

Match timestamps are saved in the server's local time without a zone; pass
--tz if the server is not on UTC. ``report`` shows the typical
minutesFromPlayedAt, which gives a wrong zone away.
"""

import argparse
import datetime
import json
import sqlite3
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

import webapp_config  # noqa: E402  (loads discord-bot/.env)
from repositories.pso_game_lookups import PsoGameLookupRepository  # noqa: E402

LOOKUP_URL = "https://playsorceryonline.com/api/internal/summit/game-lookup"
REQUEST_GAP_S = 1.05  # PSO allows 60 a minute
ANSWERED = ("found", "not_found", "ambiguous")


def utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def is_discord_id(value) -> bool:
    text = str(value or "")
    return text.isdigit() and 15 <= len(text) <= 21


def event_window(elo_db: str, event_id: int) -> tuple[str, str | None, str]:
    conn = sqlite3.connect(elo_db)
    try:
        row = conn.execute(
            "SELECT start_date, end_date, event_name FROM events WHERE event_id = ?", (event_id,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise SystemExit(f"No event {event_id} in {elo_db}")
    return row[0], row[1], row[2]


def season_matches(match_db: str, start: str, end: str | None) -> list[dict]:
    """Ranked season games (no brackets, no testing/casual) in the event window."""
    conn = sqlite3.connect(match_db)
    conn.row_factory = sqlite3.Row
    cols = {r[1] for r in conn.execute("PRAGMA table_info(match_records)")}
    replay = "replay_url" if "replay_url" in cols else "NULL"
    avatars = ("winner_avatar, loser_avatar" if "winner_avatar" in cols
               else "NULL AS winner_avatar, NULL AS loser_avatar")
    sql = (
        f"SELECT rowid AS match_id, winner_id, losser_id AS loser_id, timestamp,"
        f" winner_went_first, loser_went_first, {replay} AS replay_url, {avatars}"
        " FROM match_records"
        " WHERE timestamp >= ? AND (match_type IS NULL OR match_type = 'ranked')"
        " AND (source IS NULL OR source != 'Bracket')"
    )
    args = [start]
    if end:
        sql += " AND timestamp <= ?"
        args.append(end)
    try:
        return [dict(r) for r in conn.execute(sql + " ORDER BY rowid", args).fetchall()]
    finally:
        conn.close()


def needs_pso(match: dict) -> bool:
    return not match["replay_url"] or not match["winner_went_first"]


def played_at(timestamp: str, tz: ZoneInfo) -> str:
    when = datetime.datetime.fromisoformat(str(timestamp).replace(" ", "T"))
    if when.tzinfo is None:
        when = when.replace(tzinfo=tz)
    return when.astimezone(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def to_be_looked_up(matches, repo, retry_unanswered: bool) -> tuple[list[dict], Counter]:
    skip = repo.looked_up_ids(("found",) if retry_unanswered else ANSWERED)
    counts = Counter()
    todo = []
    for m in matches:
        if not needs_pso(m):
            counts["already has replay + play/draw"] += 1
        elif m["match_id"] in skip:
            counts["already looked up"] += 1
        elif not (is_discord_id(m["winner_id"]) and is_discord_id(m["loser_id"])):
            counts["not two Discord ids (skipped)"] += 1
        else:
            todo.append(m)
    counts["to look up"] = len(todo)
    return todo, counts


def row_from_answer(match: dict, sent_at: str, body: dict) -> dict:
    row = {
        "match_id": match["match_id"],
        "status": body.get("status") or "error",
        "candidates": body.get("candidates"),
        "error": None,
        "winner_id": str(match["winner_id"]),
        "loser_id": str(match["loser_id"]),
        "played_at": sent_at,
        "response_json": json.dumps(body, separators=(",", ":")),
        "looked_up_at": utcnow(),
    }
    game = body.get("game") or {}
    if row["status"] != "found" or not game:
        return row
    by_id = {str(p.get("discordId")): p for p in game.get("players") or []}
    winner = by_id.get(row["winner_id"], {})
    loser = by_id.get(row["loser_id"], {})
    went_first = winner.get("wentFirst")
    if went_first is None and loser.get("wentFirst") is not None:
        went_first = not loser["wentFirst"]
    row.update({
        "pso_game_id": game.get("id"),
        "matched_by": game.get("matchedBy"),
        "started_at": game.get("startedAt"),
        "finished_at": game.get("finishedAt"),
        "duration_seconds": game.get("durationSeconds"),
        "minutes_from_played_at": game.get("minutesFromPlayedAt"),
        "pso_source": game.get("source"),
        "pso_queue_type": game.get("queueType"),
        "pso_winner_id": str(game["winnerDiscordId"]) if game.get("winnerDiscordId") else None,
        "winner_went_first": None if went_first is None else int(bool(went_first)),
        "winner_avatar": winner.get("avatar"),
        "loser_avatar": loser.get("avatar"),
        "winner_replay_url": winner.get("replayUrl"),
        "loser_replay_url": loser.get("replayUrl"),
    })
    return row


def ask_pso(session, api_key: str, payload: dict, url: str) -> tuple[int, dict | str]:
    """POST one lookup, waiting out 429s and retrying 503s/timeouts a few times."""
    for attempt in range(6):
        try:
            resp = session.post(url, json=payload, headers={"X-API-Key": api_key}, timeout=30)
        except requests.RequestException as exc:
            if attempt == 5:
                return 0, repr(exc)
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 429:
            time.sleep(float(resp.headers.get("Retry-After") or 30))
            continue
        if resp.status_code == 503 and attempt < 5:
            time.sleep(2 ** (attempt + 1))
            continue
        try:
            return resp.status_code, resp.json()
        except ValueError:
            return resp.status_code, resp.text[:500]
    return 429, "still rate limited"


def cmd_lookup(args, todo, repo) -> int:
    api_key = (webapp_config.DRAFT_SORCERY_API_KEY or "").strip()
    if not api_key:
        print("DRAFT_SORCERY_API_KEY is not set; nothing to do", file=sys.stderr)
        return 1
    if args.limit:
        todo = todo[:args.limit]
    repo.ensure_table()
    tz = ZoneInfo(args.tz)
    session = requests.Session()
    statuses = Counter()
    for i, m in enumerate(todo, 1):
        started = time.monotonic()
        sent_at = played_at(m["timestamp"], tz)
        payload = {
            "players": [str(m["winner_id"]), str(m["loser_id"])],
            "playedAt": sent_at,
            "winnerDiscordId": str(m["winner_id"]),
            "toleranceMinutes": args.tolerance,
        }
        code, body = ask_pso(session, api_key, payload, args.url)
        if code == 401:
            print("PSO says the API key is wrong (401); stopping", file=sys.stderr)
            return 1
        if code == 200 and isinstance(body, dict) and body.get("status") in ANSWERED:
            row = row_from_answer(m, sent_at, body)
        else:
            row = {
                "match_id": m["match_id"], "status": "error",
                "error": f"HTTP {code}: {str(body)[:300]}",
                "winner_id": str(m["winner_id"]), "loser_id": str(m["loser_id"]),
                "played_at": sent_at, "looked_up_at": utcnow(),
            }
        repo.save(row)
        statuses[row["status"]] += 1
        print(f"[{i}/{len(todo)}] match {m['match_id']} {sent_at}: {row['status']}"
              + (f" ({row['error']})" if row.get("error") else ""))
        time.sleep(max(0.0, REQUEST_GAP_S - (time.monotonic() - started)))
    print("\nDone:", dict(statuses))
    return 0


def cmd_report(repo, matches) -> int:
    rows = repo.all() if repo.looked_up_ids() else []
    by_id = {m["match_id"]: m for m in matches}
    status = Counter(r["status"] for r in rows)
    found = [r for r in rows if r["status"] == "found"]
    print(f"Stored answers: {len(rows)}  {dict(status)}")
    if not found:
        return 0
    minutes = [r["minutes_from_played_at"] for r in found if r["minutes_from_played_at"] is not None]
    print(f"matchedBy: {dict(Counter(r['matched_by'] for r in found))}")
    print(f"PSO source: {dict(Counter(r['pso_source'] for r in found))}")
    print(f"PSO queueType: {dict(Counter(r['pso_queue_type'] for r in found))}")
    if minutes:
        print(f"minutesFromPlayedAt: median {statistics.median(minutes)}, max {max(minutes)}")
    print("Winner check: " + str(dict(Counter(
        "PSO has no winner" if not r["pso_winner_id"]
        else "agrees" if r["pso_winner_id"] == r["winner_id"] else "DISAGREES"
        for r in found))))
    print(f"With winner's replay: {sum(1 for r in found if r['winner_replay_url'])}, "
          f"loser's replay: {sum(1 for r in found if r['loser_replay_url'])}")
    print(f"Who went first known: {sum(1 for r in found if r['winner_went_first'] is not None)}")
    avatar = Counter()
    for r in found:
        m = by_id.get(r["match_id"]) or {}
        for side in ("winner", "loser"):
            ours, pso = m.get(f"{side}_avatar"), r[f"{side}_avatar"]
            if not pso:
                avatar["PSO has none"] += 1
            elif not ours:
                avatar["Summit has none, PSO has one"] += 1
            elif ours.strip().lower() == pso.strip().lower():
                avatar["same"] += 1
            else:
                avatar["different"] += 1
    print(f"Avatars (per player, not written anywhere): {dict(avatar)}")
    return 0


def apply_plan(repo, matches, include_one_player: bool) -> tuple[list[tuple], Counter]:
    by_id = {m["match_id"]: m for m in matches}
    counts = Counter()
    updates = []
    for r in repo.all() if repo.looked_up_ids() else []:
        if r["status"] != "found":
            continue
        m = by_id.get(r["match_id"])
        if not m:
            counts["match no longer in Season 8"] += 1
        elif m["winner_went_first"]:
            counts["Summit already has play/draw"] += 1
        elif r["winner_went_first"] is None:
            counts["PSO couldn't tell who went first"] += 1
        elif r["pso_winner_id"] and r["pso_winner_id"] != r["winner_id"]:
            counts["skipped: PSO winner disagrees"] += 1
        elif r["matched_by"] != "both_players" and not include_one_player:
            counts["skipped: one player was a guest"] += 1
        else:
            first = "y" if r["winner_went_first"] else "n"
            updates.append((first, "n" if first == "y" else "y", r["match_id"]))
            counts["play/draw to fill"] += 1
    return updates, counts


def cmd_apply(args, repo, matches, match_db: str) -> int:
    updates, counts = apply_plan(repo, matches, args.include_one_player)
    for label, n in counts.items():
        print(f"  {label}: {n}")
    if not args.write:
        print("\nDry run: nothing written. Add --write to fill play/draw.")
        return 0
    conn = sqlite3.connect(match_db)
    try:
        with conn:
            for winner_first, loser_first, match_id in updates:
                conn.execute(
                    "UPDATE match_records SET winner_went_first = ?, loser_went_first = ?"
                    " WHERE rowid = ? AND (winner_went_first IS NULL OR winner_went_first = '')",
                    (winner_first, loser_first, match_id),
                )
    finally:
        conn.close()
    stamp = utcnow()
    with sqlite3.connect(str(repo._db_path)) as lconn:
        lconn.executemany("UPDATE pso_game_lookups SET applied_at = ? WHERE match_id = ?",
                          [(stamp, u[2]) for u in updates])
    print(f"\nFilled play/draw on {len(updates)} matches.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Season 8 backfill from PSO's game lookup")
    parser.add_argument("step", choices=("plan", "lookup", "report", "apply"))
    parser.add_argument("--event-id", type=int, default=8)
    parser.add_argument("--tz", default="UTC", help="zone match timestamps were saved in (default UTC)")
    parser.add_argument("--tolerance", type=int, default=60, help="toleranceMinutes sent to PSO (max 240)")
    parser.add_argument("--limit", type=int, default=0, help="lookup: stop after this many")
    parser.add_argument("--retry-unanswered", action="store_true",
                        help="lookup: ask again about not_found / ambiguous games")
    parser.add_argument("--include-one-player", action="store_true",
                        help="apply: also use games where the opponent was a PSO guest")
    parser.add_argument("--write", action="store_true", help="apply: actually write")
    parser.add_argument("--url", default=LOOKUP_URL)
    parser.add_argument("--match-db", default=str(webapp_config.MATCH_RECORDS_DB_PATH))
    parser.add_argument("--elo-db", default=str(webapp_config.ELO_DB_PATH))
    args = parser.parse_args()

    start, end, name = event_window(args.elo_db, args.event_id)
    matches = season_matches(args.match_db, start, end)
    repo = PsoGameLookupRepository(args.match_db)
    print(f"{name} (event {args.event_id}): {start} to {end or 'now'}, {len(matches)} ranked games")

    if args.step == "report":
        return cmd_report(repo, matches)
    if args.step == "apply":
        return cmd_apply(args, repo, matches, args.match_db)

    todo, counts = to_be_looked_up(matches, repo, args.retry_unanswered)
    for label, n in counts.items():
        print(f"  {label}: {n}")
    if args.step == "plan":
        n = min(len(todo), args.limit) if args.limit else len(todo)
        print(f"\nPlan only: nothing sent or written. A lookup of {n} games takes about "
              f"{n * REQUEST_GAP_S / 60:.0f} minutes.")
        return 0
    return cmd_lookup(args, todo, repo)


if __name__ == "__main__":
    sys.exit(main())
