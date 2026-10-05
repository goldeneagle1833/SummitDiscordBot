"""Ending a season: the top cut and its postseason bracket.

When a season ends, the top cut is the first 24 unique ticket holders on the
season ladder (in an Avatar-mode season each player counts once, at their
best avatar). They become a draft bracket on the website, named after the
season: seeds 1-8 keep their ladder order and get the first-round byes, and
seeds 9-24 are drawn at random. The bracket stays a draft until an admin
publishes it on the site.

The site's bracket tables live in match_records.db next to the bot's own
tables, so the draft is written directly; the site builds the match tree when
the draft is published.
"""

import datetime
import logging
import random
import re
import sqlite3

from services.avatar_mode import get_event_ladder, unique_players

logger = logging.getLogger("discord_bot")

TOP_CUT_SIZE = 24
TOP_CUT_BYES = 8
# The Discord role that opens the Top Cut channel. config.TOP_CUT_ROLE_ID
# overrides it; the default is the Summit server's role, so the live config
# file (which isn't in git) needs no change.
DEFAULT_TOP_CUT_ROLE_ID = 1342136670866374706
# Where new bracket pairings are posted. config.TOP_CUT_CHANNEL_ID overrides it.
DEFAULT_TOP_CUT_CHANNEL_ID = 1365487028115996692
BRACKET_NAME_SUFFIX = "Post Season Bracket"

# <t:1794805140:F>, <t:1794805140>, or a bare unix timestamp
_DISCORD_TIMESTAMP = re.compile(r"<t:(\d{9,11})(?::[a-zA-Z])?>")
_BARE_TIMESTAMP = re.compile(r"(?<![\w:])(\d{10})(?!\w)")


class PostseasonError(Exception):
    """The postseason bracket could not be drafted."""


def extract_end_time(text: str) -> tuple[int | None, str]:
    """Pull a Discord timestamp out of command text: (unix_seconds, remaining_text).

    Accepts Discord's ``<t:1794805140:F>`` form (any style letter) or a bare
    10-digit unix time. Returns (None, text) when there isn't one.
    """
    text = text or ""
    match = _DISCORD_TIMESTAMP.search(text) or _BARE_TIMESTAMP.search(text)
    if not match:
        return None, text.strip()
    remaining = (text[: match.start()] + text[match.end():]).strip()
    return int(match.group(1)), re.sub(r"\s{2,}", " ", remaining)


def bracket_name(event_name: str) -> str:
    return f"{event_name} {BRACKET_NAME_SUFFIX}"


def select_top_cut(ladder, ticket_holder_ids, size: int = TOP_CUT_SIZE) -> list:
    """The first ``size`` unique ticket holders on the ladder, best first."""
    holders = {int(uid) for uid in ticket_holder_ids}
    return [entry for entry in unique_players(ladder) if int(entry.user_id) in holders][:size]


def seed_top_cut(qualifiers, byes: int = TOP_CUT_BYES, rng=random) -> list:
    """Seeding order: the top ``byes`` in ladder order, the rest shuffled.

    The site's bracket gives its top seeds the first-round byes, so seeds
    1-8 sit out round one and seeds 9-24 meet each other in a random draw.
    """
    top, rest = list(qualifiers[:byes]), list(qualifiers[byes:])
    rng.shuffle(rest)
    return top + rest


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug or "bracket"


def _bracket_size_for(entrant_count: int) -> int:
    size = 2
    while size < entrant_count:
        size *= 2
    return size


def create_draft_bracket(event_name: str, seeded, created_by=None, db_path: str = "match_records.db") -> dict:
    """Write the seeded top cut as a draft bracket for the website.

    ``seeded`` is the ladder entries in seeding order. Returns
    {bracket_id, slug, name, entrant_count}. Raises PostseasonError when the
    site's bracket tables don't exist or fewer than two players qualified.
    """
    if len(seeded) < 2:
        raise PostseasonError("A bracket needs at least 2 qualified ticket holders.")

    name = bracket_name(event_name)
    now = datetime.datetime.now().isoformat()
    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name IN ('brackets', 'bracket_entrants')"
            )
        }
        if tables != {"brackets", "bracket_entrants"}:
            raise PostseasonError(
                "The website's bracket tables don't exist yet (they are created when the site starts)."
            )

        base = slug = _slugify(name)
        suffix = 2
        while conn.execute("SELECT 1 FROM brackets WHERE slug = ?", (slug,)).fetchone():
            slug = f"{base}-{suffix}"
            suffix += 1

        cur = conn.execute(
            """INSERT INTO brackets (
                   slug, name, description, entrant_count, bracket_size, status,
                   seeded_from, elo_event_name, confirm_hours, created_by, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, 'draft', 'ticket_holders', ?, 48, ?, ?, ?)""",
            (
                slug, name,
                f"Top {len(seeded)} ticket holders of {event_name}. "
                f"Seeds 1-{min(TOP_CUT_BYES, len(seeded))} by ladder rank; the rest drawn at random.",
                len(seeded), _bracket_size_for(len(seeded)), event_name,
                str(created_by) if created_by else None, now, now,
            ),
        )
        bracket_id = cur.lastrowid
        conn.executemany(
            """INSERT INTO bracket_entrants
                   (bracket_id, seed, user_id, display_name, elo, games, is_ticket_holder)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            [
                (
                    bracket_id, seed, str(entry.user_id),
                    entry.display_name or f"User#{entry.user_id}",
                    entry.event_elo, entry.games_played,
                )
                for seed, entry in enumerate(seeded, start=1)
            ],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    logger.info("Drafted postseason bracket %s (%s) with %d entrants", bracket_id, slug, len(seeded))
    return {"bracket_id": bracket_id, "slug": slug, "name": name, "entrant_count": len(seeded)}


def final_ladder(event) -> list:
    """The season's ladder, read before the event is ended and archived."""
    return get_event_ladder(event)
