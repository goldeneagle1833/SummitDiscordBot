"""Community Spotlight service — daily rotating feature for the homepage."""

import logging
import random
import sqlite3
from datetime import date

from webapp_config import MATCH_RECORDS_DB_PATH, ELO_DB_PATH, COMMUNITY_DB_PATH

logger = logging.getLogger(__name__)

# ── Caching ────────────────────────────────────────────────────

_cache = {}  # {date_str: spotlight_dict}

# ── Spotlight types ────────────────────────────────────────────

SPOTLIGHT_TYPES = ["player_of_the_day", "community_channel", "community_website"]

# ── Description templates ──────────────────────────────────────

_PLAYER_TEMPLATES = [
    "{name} has been tearing through the ladder -- {wins} victories across {games} matches with {opponents} different challengers this season.",
    "All eyes on {name} today. {wins} wins, {games} games, and {opponents} opponents who can tell you firsthand -- this one means business.",
    "The arena has spoken. {name} steps into the spotlight with {wins} wins and {opponents} unique rivals faced across {games} battles.",
    "{name} has squared off against {opponents} different opponents across {games} matches this season, claiming {wins} victories along the way.",
    "Meet {name} -- {wins} wins, {opponents} unique opponents, and {games} total battles. The grind never stops.",
]

_CHANNEL_TEMPLATES = [
    "Dive into {name}'s latest Sorcery content -- strategy breakdowns, deck techs, and community vibes from one of our creators.",
    "Looking for your next favorite Sorcery creator? {name} has you covered with fresh content on YouTube.",
    "Support the community -- check out {name}'s channel for Sorcery gameplay, guides, and more.",
    "From deck techs to match replays, {name} brings Sorcery content worth watching.",
    "Community creator spotlight: {name}. Hit subscribe and join the conversation.",
]

_WEBSITE_TEMPLATES = [
    "Sharpen your game with {name} -- {description}",
    "Bookmark this one. {name} is a go-to resource for the Sorcery community.",
    "Level up your knowledge -- {name} brings {description}",
    "Looking for tools and resources? {name} has what you need.",
    "Community resource spotlight: {name}. Worth a visit for any Sorcery player.",
]

_WEBSITE_TEMPLATES_NO_DESC = [
    "Bookmark this one. {name} is a go-to resource for the Sorcery community.",
    "Looking for tools and resources? {name} has what you need.",
    "Community resource spotlight: {name}. Worth a visit for any Sorcery player.",
]

# ── Public entry point ─────────────────────────────────────────


def get_daily_spotlight() -> dict:
    """Return today's community spotlight, cached for 24 hours."""
    today = date.today().isoformat()

    if today in _cache:
        return _cache[today]

    try:
        rng = random.Random(today)
        # Shuffle types so fallback order varies by day
        types = list(SPOTLIGHT_TYPES)
        rng.shuffle(types)

        spotlight = None
        for spotlight_type in types:
            spotlight = _HANDLERS[spotlight_type](rng)
            if spotlight is not None:
                break

        result = {"success": True, "spotlight": spotlight}
        _cache.clear()  # Only keep one day cached
        _cache[today] = result
        return result

    except Exception:
        logger.error("Failed to generate spotlight", exc_info=True)
        return {"success": True, "spotlight": None}


# ── Type handlers ──────────────────────────────────────────────


def _get_player_of_the_day(rng: random.Random) -> dict | None:
    """Pick a random active player and return their season stats."""
    try:
        # Get active event start date for season filtering
        start_date = _get_season_start_date()

        # Find eligible players with >= 3 ranked matches
        players = _get_eligible_players(start_date)
        if not players:
            return None

        player = rng.choice(players)
        user_id = player["user_id"]
        display_name = player["display_name"]
        games = player["games"]
        wins = player["wins"]
        opponents = player["unique_opponents"]

        # Build avatar URL
        avatar_info = _get_player_avatar(user_id)
        image_url = None
        if avatar_info and avatar_info.get("avatar"):
            image_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_info['avatar']}.png?size=128"

        template = rng.choice(_PLAYER_TEMPLATES)
        subtitle = template.format(
            name=display_name, wins=wins, games=games, opponents=opponents
        )

        return {
            "type": "player_of_the_day",
            "badge_text": "PLAYER OF THE DAY",
            "color": "gold",
            "title": display_name,
            "subtitle": subtitle,
            "link": f"/player/{user_id}",
            "image_url": image_url,
            "stats": {
                "games": games,
                "wins": wins,
                "unique_opponents": opponents,
            },
        }
    except Exception:
        logger.error("Failed to get player of the day", exc_info=True)
        return None


def _get_community_channel(rng: random.Random) -> dict | None:
    """Pick a random YouTube channel from the community database."""
    try:
        from repositories.community import CommunityRepository

        channels = CommunityRepository().get_youtube_channels()
        if not channels:
            return None

        channel = rng.choice(channels)
        template = rng.choice(_CHANNEL_TEMPLATES)
        subtitle = template.format(name=channel["name"])

        return {
            "type": "community_channel",
            "badge_text": "COMMUNITY",
            "color": "red",
            "title": channel["name"],
            "subtitle": subtitle,
            "link": channel["channel_url"],
            "image_url": None,
            "stats": None,
        }
    except Exception:
        logger.error("Failed to get community channel", exc_info=True)
        return None


def _get_community_website(rng: random.Random) -> dict | None:
    """Pick a random website from the community database."""
    try:
        from repositories.community import CommunityRepository

        websites = CommunityRepository().get_websites()
        if not websites:
            return None

        website = rng.choice(websites)
        description = website.get("description") or ""

        if description:
            template = rng.choice(_WEBSITE_TEMPLATES)
            subtitle = template.format(name=website["name"], description=description)
        else:
            template = rng.choice(_WEBSITE_TEMPLATES_NO_DESC)
            subtitle = template.format(name=website["name"])

        return {
            "type": "community_website",
            "badge_text": "COMMUNITY",
            "color": "blue",
            "title": website["name"],
            "subtitle": subtitle,
            "link": website["url"],
            "image_url": None,
            "stats": None,
        }
    except Exception:
        logger.error("Failed to get community website", exc_info=True)
        return None


# ── Handler registry ───────────────────────────────────────────

_HANDLERS = {
    "player_of_the_day": _get_player_of_the_day,
    "community_channel": _get_community_channel,
    "community_website": _get_community_website,
}

# ── Database helpers ───────────────────────────────────────────


def _get_season_start_date() -> str | None:
    """Get the start date of the currently active event (season)."""
    try:
        conn = sqlite3.connect(str(ELO_DB_PATH))
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
        )
        if not cur.fetchone():
            conn.close()
            return None
        cur.execute(
            "SELECT start_date FROM events WHERE is_active = 1 LIMIT 1"
        )
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        logger.error("Failed to get season start date", exc_info=True)
        return None


def _get_eligible_players(start_date: str | None) -> list[dict]:
    """Find players with >= 3 ranked matches, returning stats for each."""
    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()

        # Check if match_records table exists
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='match_records'"
        )
        if not cur.fetchone():
            conn.close()
            return []

        # Build timestamp filter
        date_clause = ""
        params = []
        if start_date:
            date_clause = "AND timestamp >= ?"
            params = [start_date]

        # Query: for each player, get games, wins, unique opponents
        # Union winners and losers into a single player perspective
        query = f"""
            WITH player_matches AS (
                SELECT winner_id AS player_id, losser_id AS opponent_id, 1 AS is_win
                FROM match_records
                WHERE (match_type = 'ranked' OR match_type IS NULL) {date_clause}
                UNION ALL
                SELECT losser_id AS player_id, winner_id AS opponent_id, 0 AS is_win
                FROM match_records
                WHERE (match_type = 'ranked' OR match_type IS NULL) {date_clause}
            )
            SELECT
                player_id,
                COUNT(*) AS games,
                SUM(is_win) AS wins,
                COUNT(DISTINCT opponent_id) AS unique_opponents
            FROM player_matches
            GROUP BY player_id
            HAVING COUNT(*) >= 3
        """
        cur.execute(query, params * 2)  # params used twice (winner + loser subquery)
        rows = cur.fetchall()
        conn.close()

        if not rows:
            return []

        # Get display names from elo.db
        names = _get_display_names([str(r[0]) for r in rows])

        return [
            {
                "user_id": str(row[0]),
                "display_name": names.get(str(row[0]), f"Player {row[0]}"),
                "games": row[1],
                "wins": row[2],
                "unique_opponents": row[3],
            }
            for row in rows
        ]
    except Exception:
        logger.error("Failed to get eligible players", exc_info=True)
        return []


def _get_display_names(user_ids: list[str]) -> dict[str, str]:
    """Look up display names from overall_standings in elo.db."""
    if not user_ids:
        return {}
    try:
        conn = sqlite3.connect(str(ELO_DB_PATH))
        cur = conn.cursor()
        placeholders = ",".join("?" for _ in user_ids)
        cur.execute(
            f"SELECT user_id, user_display_name FROM overall_standings WHERE user_id IN ({placeholders})",
            user_ids,
        )
        result = {str(row[0]): row[1] for row in cur.fetchall()}
        conn.close()
        return result
    except Exception:
        return {}


def _get_player_avatar(user_id: str) -> dict | None:
    """Look up avatar hash from user_profiles in match_records.db."""
    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='user_profiles'"
        )
        if not cur.fetchone():
            conn.close()
            return None
        cur.execute(
            "SELECT avatar FROM user_profiles WHERE user_id = ? LIMIT 1",
            (user_id,),
        )
        row = cur.fetchone()
        conn.close()
        if row:
            return {"avatar": row[0]}
        return None
    except Exception:
        return None
