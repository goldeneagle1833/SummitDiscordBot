"""Who goes first in a new pairing, balanced from each player's history.

PSO used to roll a die in the client for who goes first. Summit now picks
the first player when it opens the table and sends it in the pairing JSON
(``firstPlayerDiscordUserId``), the way online chess balances White and
Black over a player's games:

1. Count each player's past games IN THE SAME QUEUE where we know who
   went first (Bruce's choice, 2026-11-17: going first a lot in casual
   doesn't count against you in ranked). Turn order has been recorded
   since 2026-02-07. Where each queue's games live:
   - Limited: limited_match_records (+ its archive)
   - Precon: precon_match_records (not removed), plus any older precon
     games in the main tables
   - Every other queue (ranked, casual "testing", rumble, points): the main
     match tables (current, Season 1-8 archive, Glicko-2 season table),
     by match_type; a missing match_type counts as ranked.
2. Weighted chance (Bruce, 2026-11-18): each player's chance of going
   first is 50% plus half the gap between the two shares, so the player who
   has gone first less is more likely, not certain, to go first. Example:
   A went first 40% of the time, B 60% -> A goes first 60% of the time.
3. Equal shares, or neither player having any history, is 50/50.

A game counts only when its winner/loser flags agree (one went first, the
other didn't). Admin-entered Limited results save "n" for both players and
are skipped as unknown.
"""

import logging
import random
import sqlite3

logger = logging.getLogger("discord_bot")

DB_NAME = "match_records.db"
MATCH_TABLES = ("match_records", "match_records_archive", "season_match_records")
LIMITED_TABLES = ("limited_match_records", "limited_match_records_archive")


def _flag(value):
    """'y'/'Yes'/'true'/1 -> True, 'n'/'No'/'false'/0 -> False, else None."""
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("y", "yes", "true", "1"):
        return True
    if text in ("n", "no", "false", "0"):
        return False
    return None


def _queries(queue_type, marks):
    """(sql, uses_match_type_param) for each table holding this queue's games."""
    queue_type = (queue_type or "ranked").lower()
    cols = "winner_id, {loser} AS loser_id, winner_went_first, loser_went_first"
    who = "(winner_id IN ({m}) OR {loser} IN ({m}))"
    if queue_type == "limited":
        return [
            (f"SELECT {cols.format(loser='loser_id')} FROM {t} "
             f"WHERE {who.format(m=marks, loser='loser_id')}", False)
            for t in LIMITED_TABLES
        ]
    main = [
        (f"SELECT {cols.format(loser='losser_id')} FROM {t} "
         f"WHERE {who.format(m=marks, loser='losser_id')} "
         "AND COALESCE(NULLIF(match_type, ''), 'ranked') = ?", True)
        for t in MATCH_TABLES
    ]
    if queue_type == "precon":
        main.append((
            f"SELECT {cols.format(loser='loser_id')} FROM precon_match_records "
            f"WHERE {who.format(m=marks, loser='loser_id')} AND COALESCE(removed, 0) = 0",
            False,
        ))
    return main


def going_first_counts(user_ids, queue_type="ranked", db_name=None):
    """{user_id: (games_went_first, games_with_known_turn_order)} in one queue."""
    ids = [int(u) for u in user_ids]
    if not ids:
        return {}
    counts = {u: [0, 0] for u in ids}
    marks = ",".join("?" * len(ids))
    queue = (queue_type or "ranked").lower()
    conn = sqlite3.connect(db_name or DB_NAME)
    try:
        cur = conn.cursor()
        for sql, uses_type in _queries(queue, marks):
            params = ids + ids + ([queue] if uses_type else [])
            try:
                rows = cur.execute(sql, params).fetchall()
            except sqlite3.OperationalError:
                continue  # table (or a column) missing on an old database
            for winner_id, loser_id, winner_flag, loser_flag in rows:
                winner_first = _flag(winner_flag)
                loser_first = _flag(loser_flag)
                if winner_first is None:
                    continue
                if loser_first is not None and loser_first == winner_first:
                    continue  # both "went first" or both "didn't": unknown
                for user_id, went_first in ((winner_id, winner_first), (loser_id, not winner_first)):
                    try:
                        user_id = int(user_id)
                    except (TypeError, ValueError):
                        continue
                    if user_id in counts:
                        counts[user_id][1] += 1
                        if went_first:
                            counts[user_id][0] += 1
    finally:
        conn.close()
    return {u: (c[0], c[1]) for u, c in counts.items()}


def _share(first, games):
    # No history counts as an even 50%, so a newcomer neither jumps the line
    # nor always waits
    return first / games if games else 0.5


def first_player_chance(share_a, share_b):
    """Chance (0-1) that player A goes first: 50% plus half the share gap."""
    return min(1.0, max(0.0, 0.5 + (share_b - share_a) / 2))


def choose_first_player(user_a, user_b, counts=None, rng=None, queue_type="ranked"):
    """The Discord id (int) of the player who should go first (weighted draw)."""
    user_a, user_b = int(user_a), int(user_b)
    if counts is None:
        counts = going_first_counts([user_a, user_b], queue_type)
    share_a = _share(*counts.get(user_a, (0, 0)))
    share_b = _share(*counts.get(user_b, (0, 0)))
    chance_a = first_player_chance(share_a, share_b)
    return user_a if (rng or random).random() < chance_a else user_b


def pick_first_player(players, queue_type="ranked"):
    """First player's Discord id for a two-player pairing, or None on any problem.

    Never raises: a failure here must not stop the table from opening (PSO
    then rolls for turn order as before).
    """
    try:
        if len(players) != 2:
            return None
        ids = [int(p["discord_user_id"]) for p in players]
        if ids[0] == ids[1]:
            return None
        return choose_first_player(ids[0], ids[1], queue_type=queue_type)
    except Exception as exc:
        logger.warning("Could not pick who goes first: %r", exc)
        return None
