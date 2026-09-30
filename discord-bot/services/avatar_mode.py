"""Player mode vs Avatar mode for the event ladder.

Each event is locked into one mode when it starts:

- Player mode (how the Summit always worked): one event ELO per player; deck
  links stay optional and avatars are only inferred from deck data later.
- Avatar mode: one event ELO per (player, avatar). Ranked joins need a deck
  link; the avatar is read from it when the match is made and locked to the
  pairing. Top cut is still per player: one invite each, and a player's
  lower avatar entries never take a second slot.

Everything that shows or uses "the event ladder" should read it through
get_event_ladder() so both modes share one code path.
"""

import logging
import sqlite3
from dataclasses import dataclass

from repositories.avatar_elo_repo import AVATAR_MODE, PLAYER_MODE, get_avatar_standings
from repositories.elo_repo import (
    ELO_COUNTING_MATCH_FILTER,
    get_active_event,
    get_event_participant_ids,
    get_user_event_elo,
)
from repositories.avatar_elo_repo import get_avatar_event_elo
from utils.avatars import read_deck_avatar
from utils.deck_checker import get_pso_deck_id

logger = logging.getLogger("discord_bot")

# Queue types whose games move the event ladder and so need an avatar.
AVATAR_QUEUE_TYPES = ("ranked",)

DECK_REQUIRED_MESSAGE = (
    "This season rates every avatar separately, so ranked games need a deck link. "
    "Paste your Curiosa or Sorcery Online deck link and join again."
)
DECK_UNREADABLE_MESSAGE = (
    "Couldn't read an avatar from that deck link. Check the link (and that the deck "
    "is public) and try again."
)


def event_mode(event: dict | None) -> str:
    return (event or {}).get("elo_mode") or PLAYER_MODE


def active_event_mode() -> str:
    """The running event's mode (Player mode when no event is running)."""
    return event_mode(get_active_event())


def is_avatar_mode(event: dict | None = None) -> bool:
    if event is None:
        return active_event_mode() == AVATAR_MODE
    return event_mode(event) == AVATAR_MODE


def needs_avatar(queue_type: str) -> bool:
    """Whether joining this queue right now requires a readable deck avatar."""
    return queue_type in AVATAR_QUEUE_TYPES and is_avatar_mode()


def _looks_like_deck_link(url: str) -> bool:
    lowered = (url or "").lower()
    return bool(get_pso_deck_id(url)) or "sorcerytcg.com/decks/" in lowered or "curiosa.io/decks/" in lowered


async def check_join_deck(deck_url: str | None) -> tuple[str | None, str | None]:
    """Join-time check for Avatar mode: (avatar, error_message).

    Runs before the player is queued, so a bad link fails immediately instead
    of after they've been paired.
    """
    if not deck_url:
        return None, DECK_REQUIRED_MESSAGE
    if not _looks_like_deck_link(deck_url):
        return None, DECK_UNREADABLE_MESSAGE
    avatar = await read_deck_avatar(deck_url)
    if not avatar:
        return None, DECK_UNREADABLE_MESSAGE
    return avatar, None


async def lock_match_avatar(deck_url: str | None, join_avatar: str | None) -> str | None:
    """The avatar to lock when the match is made.

    Re-reads the deck (the official read). If that fails, falls back to the
    avatar found when the player joined, so a brief outage never breaks a
    pairing that already happened.
    """
    avatar = await read_deck_avatar(deck_url) if deck_url else None
    if not avatar and join_avatar:
        logger.warning(
            "lock_match_avatar: deck re-read failed for %s; using join-time avatar %s",
            deck_url, join_avatar,
        )
    return avatar or join_avatar


def ladder_elo(user_id: int, avatar: str | None = None, event: dict | None = None) -> int:
    """The event ELO that stakes and ranks use for a player in this match."""
    event = event if event is not None else get_active_event()
    if avatar and event and is_avatar_mode(event):
        return get_avatar_event_elo(event["event_id"], user_id, avatar)
    return get_user_event_elo(user_id)


def ladder_stakes_apply(challenger_elo: int, opponent_elo: int) -> bool:
    """Ladder challenges use special stakes when the gap is 100 or more."""
    return abs(challenger_elo - opponent_elo) >= 100


def set_avatar_ladder_stakes(ladder_info: dict, challenger_avatar, opponent_id, opponent_avatar) -> None:
    """Re-decide a ladder match's stakes from the two locked avatars' ELOs.

    Avatar mode only: the queue first sizes stakes from per-player event ELO,
    before the avatars are locked; this settles them on the avatar entries.
    """
    challenger_elo = ladder_elo(ladder_info["challenger_id"], challenger_avatar)
    opponent_elo = ladder_elo(opponent_id, opponent_avatar)
    special = ladder_stakes_apply(challenger_elo, opponent_elo)
    ladder_info["elo_multiplier_winner"] = 2.0 if special else 1.0
    ladder_info["elo_multiplier_loser"] = 0.5 if special else 1.0
    ladder_info["challenger_avatar"] = challenger_avatar
    ladder_info["opponent_avatar"] = opponent_avatar


# ── The event ladder ──


@dataclass
class LadderEntry:
    user_id: int
    display_name: str | None
    event_elo: int
    games_played: int
    avatar: str | None = None  # None in Player mode

    @property
    def label(self) -> str:
        name = self.display_name or f"User#{self.user_id}"
        return f"{name} ({self.avatar})" if self.avatar else name


def _player_mode_ladder(event: dict) -> list[LadderEntry]:
    start = event["start_date"].isoformat()
    participants = get_event_participant_ids(start)
    conn = sqlite3.connect("elo.db")
    try:
        rows = conn.execute(
            "SELECT user_id, user_display_name, online_event_elo FROM overall_standings "
            "ORDER BY online_event_elo DESC"
        ).fetchall()
    finally:
        conn.close()

    conn = sqlite3.connect("match_records.db")
    try:
        games = dict(conn.execute(
            f"""SELECT player_id, COUNT(*) FROM (
                    SELECT winner_id AS player_id FROM match_records
                    WHERE timestamp >= ? AND {ELO_COUNTING_MATCH_FILTER}
                    UNION ALL
                    SELECT losser_id AS player_id FROM match_records
                    WHERE timestamp >= ? AND {ELO_COUNTING_MATCH_FILTER}
                ) GROUP BY player_id""",
            (start, start),
        ).fetchall())
    finally:
        conn.close()

    return [
        LadderEntry(uid, name, elo if elo is not None else 1500, games.get(uid, 0))
        for uid, name, elo in rows
        if uid in participants
    ]


def get_event_ladder(event: dict | None = None) -> list[LadderEntry]:
    """The running (or given) event's ladder, best first, in either mode."""
    event = event if event is not None else get_active_event()
    if not event:
        return []
    if is_avatar_mode(event):
        return [
            LadderEntry(
                row["user_id"], row["user_display_name"], row["event_elo"],
                row["games_played"], row["avatar"],
            )
            for row in get_avatar_standings(event["event_id"])
        ]
    return _player_mode_ladder(event)


def unique_players(entries):
    """Each player's best entry only, keeping ladder order.

    Top cut belongs to the player: a second qualifying avatar never takes a
    second slot, so the next unique player moves up instead. In Player mode
    every entry is already a different player and nothing is dropped.
    """
    seen = set()
    best = []
    for entry in entries:
        user_id = entry.user_id if isinstance(entry, LadderEntry) else entry["user_id"]
        if user_id in seen:
            continue
        seen.add(user_id)
        best.append(entry)
    return best
