"""Who goes first in a new pairing, balanced from each player's history.

PSO used to roll a die in the client for who goes first. Summit now picks
the first player when it opens the table and sends it in the pairing JSON
(``firstPlayerDiscordUserId``), the way online chess balances White and
Black over a player's games:

1. Count each player's last 10 games IN THE SAME QUEUE where we know who
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
4. Streak cap (2026-11-20): 3 in a row going first -> go second next, and
   3 in a row going second -> go first next (STREAK_CAP).

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
# Only each player's most recent games count (Bruce, 2026-11-18: lifetime
# shares moved so slowly that veterans went first, or second, game after
# game; window set to 10 the same day). A short window corrects within a few games.
RECENT_GAMES = 10
# Hard streak cap (Bruce, 2026-11-20): after this many games in a row going
# first, a player goes second next (and the other way round). Only when the
# two players' caps disagree (e.g. both on 3 firsts in a row) does the
# weighted chance decide.
STREAK_CAP = 3


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
    cols = "winner_id, {loser} AS loser_id, winner_went_first, loser_went_first, timestamp"
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


def going_first_counts(user_ids, queue_type="ranked", db_name=None, recent=RECENT_GAMES):
    """{user_id: (games_went_first, games_counted)} over each player's last
    ``recent`` games in one queue where turn order is known."""
    return _counts(_recent_history(user_ids, queue_type, db_name), recent)


def _recent_history(user_ids, queue_type="ranked", db_name=None):
    """{user_id: [went_first, ...]} newest first, games with known turn order."""
    ids = [int(u) for u in user_ids]
    if not ids:
        return {}
    history = {u: [] for u in ids}  # (timestamp, went_first)
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
            for winner_id, loser_id, winner_flag, loser_flag, timestamp in rows:
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
                    if user_id in history:
                        history[user_id].append((str(timestamp or ""), went_first))
    finally:
        conn.close()
    for games in history.values():
        games.sort(key=lambda g: g[0], reverse=True)
    return {u: [first for _, first in games] for u, games in history.items()}


def _counts(history, recent=RECENT_GAMES):
    counts = {}
    for user_id, flags in history.items():
        flags = flags[:recent] if recent else flags
        counts[user_id] = (sum(1 for first in flags if first), len(flags))
    return counts


def _streaks(history):
    """{user_id: (went_first, run_length)} for each player's current run."""
    streaks = {}
    for user_id, flags in history.items():
        if not flags:
            streaks[user_id] = (None, 0)
            continue
        side, length = flags[0], 0
        for first in flags:
            if first != side:
                break
            length += 1
        streaks[user_id] = (side, length)
    return streaks


def _forced_first(user_a, user_b, streaks, cap=STREAK_CAP):
    """Who must go first because of the streak cap, or None to use the chance."""
    if not streaks or not cap:
        return None
    wants = set()
    for user, other in ((user_a, user_b), (user_b, user_a)):
        side, length = streaks.get(user, (None, 0))
        if side is not None and length >= cap:
            wants.add(other if side else user)  # long run first -> other goes first
    return wants.pop() if len(wants) == 1 else None


def _share(first, games):
    # No history counts as an even 50%, so a newcomer neither jumps the line
    # nor always waits
    return first / games if games else 0.5


def first_player_chance(share_a, share_b):
    """Chance (0-1) that player A goes first: 50% plus half the share gap."""
    return min(1.0, max(0.0, 0.5 + (share_b - share_a) / 2))


def choose_first_player(user_a, user_b, counts=None, rng=None, queue_type="ranked", streaks=None):
    """The Discord id (int) of the player who should go first.

    A player on a run of STREAK_CAP or more (first or second) is switched;
    otherwise it's a weighted draw from the last-10 shares.
    """
    user_a, user_b = int(user_a), int(user_b)
    if counts is None:
        history = _recent_history([user_a, user_b], queue_type)
        counts = _counts(history)
        if streaks is None:
            streaks = _streaks(history)
    forced = _forced_first(user_a, user_b, streaks)
    if forced is not None:
        return forced
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


# --- Turn-order choice (Bruce, 2026-11-27) ---------------------------------
# The player picked above no longer simply goes first: PSO lets them CHOOSE
# to go first or second, and reports the choice back with the result. Each
# pairing's chooser is saved when the table opens, and the choice is filled
# in when PSO reports. What actually happened (who went first) still comes
# from winner_went_first on the match record, so the balance above keeps
# working from real turn order.

CHOICES = ("first", "second")


def _choice_connection(db_name=None):
    conn = sqlite3.connect(db_name or DB_NAME)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS turn_order_choices (
            pairing_kind TEXT NOT NULL,
            pairing_id INTEGER NOT NULL,
            queue_type TEXT,
            chooser_id INTEGER,
            choice TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            reported_at TEXT,
            PRIMARY KEY (pairing_kind, pairing_id)
        )
    """)
    return conn


def _kind(queue_type):
    # Limited pairings have their own id sequence
    return "limited" if (queue_type or "").lower() == "limited" else "queue"


def save_chooser(pairing_id, queue_type, chooser_id, db_name=None):
    """Remember who was offered the choice for a pairing. Never raises."""
    try:
        conn = _choice_connection(db_name)
        try:
            conn.execute(
                """INSERT INTO turn_order_choices (pairing_kind, pairing_id, queue_type, chooser_id)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(pairing_kind, pairing_id) DO UPDATE SET
                       queue_type = excluded.queue_type, chooser_id = excluded.chooser_id""",
                (_kind(queue_type), int(pairing_id), queue_type, int(chooser_id)),
            )
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as exc:
        logger.warning("Could not save turn-order chooser for pairing %s: %r", pairing_id, exc)
        return False


def save_choice(pairing_id, queue_type, chooser_id, choice, db_name=None):
    """Record what the chooser picked ('first'/'second'), as PSO reported it."""
    choice = normalize_choice(choice)
    if choice is None:
        return False
    try:
        conn = _choice_connection(db_name)
        try:
            conn.execute(
                """INSERT INTO turn_order_choices
                       (pairing_kind, pairing_id, queue_type, chooser_id, choice, reported_at)
                   VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(pairing_kind, pairing_id) DO UPDATE SET
                       chooser_id = COALESCE(excluded.chooser_id, turn_order_choices.chooser_id),
                       choice = excluded.choice, reported_at = excluded.reported_at""",
                (_kind(queue_type), int(pairing_id), queue_type,
                 int(chooser_id) if chooser_id is not None else None, choice),
            )
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as exc:
        logger.warning("Could not save turn-order choice for pairing %s: %r", pairing_id, exc)
        return False


def get_choice(pairing_id, queue_type, db_name=None):
    """{'chooser_id', 'choice'} saved for a pairing, or None."""
    conn = _choice_connection(db_name)
    try:
        row = conn.execute(
            "SELECT chooser_id, choice FROM turn_order_choices WHERE pairing_kind = ? AND pairing_id = ?",
            (_kind(queue_type), int(pairing_id)),
        ).fetchone()
    finally:
        conn.close()
    return {"chooser_id": row[0], "choice": row[1]} if row else None


def normalize_choice(value):
    """'first'/'second' (also 'play'/'draw', True/False for "chose first"), else None."""
    if isinstance(value, bool):
        return "first" if value else "second"
    text = str(value or "").strip().lower()
    if text in ("first", "play", "go_first", "go first"):
        return "first"
    if text in ("second", "draw", "go_second", "go second"):
        return "second"
    return None


def winner_went_first_from_choice(winner_id, loser_id, chooser_id, choice):
    """True/False for whether the winner went first, from the chooser's pick.

    None when the chooser isn't one of the two players or the choice is unknown.
    """
    choice = normalize_choice(choice)
    if choice is None or chooser_id is None:
        return None
    try:
        chooser, winner, loser = int(chooser_id), int(winner_id), int(loser_id)
    except (TypeError, ValueError):
        return None
    if chooser not in (winner, loser):
        return None
    chooser_first = choice == "first"
    return chooser_first if chooser == winner else not chooser_first
