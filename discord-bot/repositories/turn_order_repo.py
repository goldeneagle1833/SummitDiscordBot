"""Who goes first in a new pairing, balanced from each player's history.

PSO used to roll a die in the client for who goes first. Summit now picks
the first player when it opens the table and sends it in the pairing JSON
(``firstPlayerDiscordUserId``), the way online chess balances White and
Black over a player's games:

1. Count each player's past games where we know who went first (every
   match table: the current one, the Season 1-8 archive and the Glicko-2
   season table). Turn order has been recorded since 2026-02-07.
2. Whoever went first in a smaller share of their games goes first.
3. A tie, or neither player having any history, is a coin flip.

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


def going_first_counts(user_ids, db_name=None):
    """{user_id: (games_went_first, games_with_known_turn_order)} for each id."""
    ids = [int(u) for u in user_ids]
    counts = {u: [0, 0] for u in ids}
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    conn = sqlite3.connect(db_name or DB_NAME)
    try:
        cur = conn.cursor()
        for table in MATCH_TABLES:
            try:
                cur.execute(
                    f"""SELECT winner_id, losser_id, winner_went_first, loser_went_first
                        FROM {table}
                        WHERE winner_id IN ({marks}) OR losser_id IN ({marks})""",
                    ids + ids,
                )
                rows = cur.fetchall()
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


def choose_first_player(user_a, user_b, counts=None, rng=None):
    """The Discord id (int) of the player who should go first."""
    user_a, user_b = int(user_a), int(user_b)
    if counts is None:
        counts = going_first_counts([user_a, user_b])
    share_a = _share(*counts.get(user_a, (0, 0)))
    share_b = _share(*counts.get(user_b, (0, 0)))
    if share_a < share_b:
        return user_a
    if share_b < share_a:
        return user_b
    return (rng or random).choice([user_a, user_b])


def pick_first_player(players):
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
        return choose_first_player(ids[0], ids[1])
    except Exception as exc:
        logger.warning("Could not pick who goes first: %r", exc)
        return None
