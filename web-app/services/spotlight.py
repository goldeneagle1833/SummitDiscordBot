"""Community Spotlight service — daily rotating feature for the homepage."""

import json
import logging
import os
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from webapp_config import MATCH_RECORDS_DB_PATH, ELO_DB_PATH, COMMUNITY_DB_PATH, OPENAI_API_KEY, AVATAR_IMAGES_DIR

logger = logging.getLogger(__name__)

# ── OpenAI client (lazy init) ─────────────────────────────────

_openai_client = None


def _get_openai_client():
    """Return a cached OpenAI client, or None if no API key is configured."""
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    if not OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
        return _openai_client
    except Exception:
        logger.error("Failed to initialize OpenAI client", exc_info=True)
        return None


_SPOTLIGHT_PROMPT = (
    "You are writing a short spotlight blurb for a competitive card game called "
    "Sorcery: Contested Realm. You will receive a player name, their avatar (the champion "
    "they battle with), the elements they wield, their season stats (total games, wins, "
    "unique opponents), and their record with their current avatar.\n\n"
    "Write 1-2 sentences (under 60 words) in this style with a little variety of flavor:\n"
    '"{name} has taken {avatar} into battle across {avatar_games} games, wielding {elements} '
    'to claim {avatar_wins} victories. With {total_games} matches and {opponents} challengers '
    'faced this season, the grind never stops."\n\n'
    "RULES:\n"
    "- 1-2 sentences, under 60 words.\n"
    "- You MUST include the player name, avatar name, element names, and the key numbers.\n"
    "- Weave the season stats (total games, wins, opponents) and avatar stats naturally.\n"
    "- Add a little personality -- vary between heroic, dramatic, or playful tone.\n"
    "- NO emojis.\n"
    "- Reference the avatar as a living champion the player has chosen."
)

_AVATAR_FALLBACK_TEMPLATES = [
    "{name} has taken {avatar} into battle across {avatar_games} games, wielding {elements} to claim {avatar_wins} victories. {total_games} matches played, {opponents} challengers faced this season.",
    "With {avatar} at their side and the power of {elements}, {name} has fought {avatar_games} battles and emerged victorious {avatar_wins} times across {total_games} season matches.",
    "{name} rides into the arena with {avatar} -- {avatar_wins} wins across {avatar_games} matches, channeling {elements}. {total_wins} victories and {opponents} unique opponents this season.",
]

# ── GPT description disk cache ────────────────────────────────

_DESC_CACHE_PATH = Path(__file__).parent.parent / ".spotlight_desc_cache.json"


def _load_desc_cache() -> dict:
    """Load cached GPT descriptions from disk. Returns {date_str: description}."""
    try:
        if _DESC_CACHE_PATH.exists():
            data = json.loads(_DESC_CACHE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_desc_cache(cache: dict) -> None:
    """Persist GPT descriptions to disk."""
    try:
        _DESC_CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
    except Exception:
        logger.error("Failed to save spotlight description cache", exc_info=True)


def _generate_avatar_description(
    player_name: str, avatar_name: str, elements: list[str],
    avatar_games: int, avatar_wins: int,
    total_games: int, total_wins: int, opponents: int,
    rng: random.Random,
) -> str:
    """Generate a fantasy-style description via GPT, with disk caching and template fallback."""
    today = date.today().isoformat()
    elements_str = " and ".join(elements) if elements else "unknown forces"

    # Check disk cache first
    desc_cache = _load_desc_cache()
    if today in desc_cache:
        return desc_cache[today]

    description = None

    client = _get_openai_client()
    if client:
        try:
            prompt_input = (
                f"Player: {player_name}\n"
                f"Avatar: {avatar_name}\n"
                f"Elements: {elements_str}\n"
                f"Games with this avatar: {avatar_games}\n"
                f"Wins with this avatar: {avatar_wins}\n"
                f"Total season games: {total_games}\n"
                f"Total season wins: {total_wins}\n"
                f"Unique opponents faced: {opponents}"
            )
            response = client.responses.create(
                model="gpt-4.1-nano",
                instructions=_SPOTLIGHT_PROMPT,
                input=prompt_input,
            )
            text = response.output_text.strip()
            if text:
                description = text
        except Exception:
            logger.error("OpenAI API error for spotlight description", exc_info=True)

    # Fallback to template
    if not description:
        template = rng.choice(_AVATAR_FALLBACK_TEMPLATES)
        description = template.format(
            name=player_name, avatar=avatar_name, elements=elements_str,
            avatar_games=avatar_games, avatar_wins=avatar_wins,
            total_games=total_games, total_wins=total_wins, opponents=opponents,
        )

    # Save to disk cache (only keep today)
    _save_desc_cache({today: description})
    return description


# ── Avatar image helper ───────────────────────────────────────


def _find_avatar_image(avatar_name: str) -> str | None:
    """Find the avatar image file path for use as a background, returns URL path or None."""
    if not avatar_name or not AVATAR_IMAGES_DIR.exists():
        return None
    try:
        files = [
            f for f in os.listdir(AVATAR_IMAGES_DIR)
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
        ]
        norm = lambda s: s.lower().replace(" ", "").replace("-", "").replace("_", "").replace("'", "")
        target = norm(avatar_name)
        # Exact match
        for f in files:
            if norm(f.rsplit(".", 1)[0]) == target:
                return f"/avatar-images/{f}"
        # Substring match
        for f in files:
            if target in norm(f.rsplit(".", 1)[0]):
                return f"/avatar-images/{f}"
        for f in files:
            if norm(f.rsplit(".", 1)[0]) in target:
                return f"/avatar-images/{f}"
    except Exception:
        pass
    return None


# ── Caching ────────────────────────────────────────────────────

_cache = {}  # {date_str: spotlight_dict}

# ── Spotlight types ────────────────────────────────────────────

SPOTLIGHT_TYPES = ["player_of_the_day", "community_channel", "community_website"]

# ── Description templates ──────────────────────────────────────

_PLAYER_FALLBACK_TEMPLATES = [
    "Meet {name} -- {wins} victories across {games} matches with {opponents} different challengers this season.",
    "Meet {name} -- {games} games, {wins} wins, and {opponents} opponents who can tell you firsthand this one means business.",
    "Meet {name} -- {wins} wins and {opponents} unique rivals faced across {games} battles. The grind never stops.",
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

        # Get most recent avatar and element stats from match deck data
        last_avatar, elements_used = _get_player_deck_stats(user_id, start_date)

        # Generate GPT description weaving all stats together
        avatar_bg_image = None
        if last_avatar:
            subtitle = _generate_avatar_description(
                player_name=display_name,
                avatar_name=last_avatar["name"],
                elements=elements_used,
                avatar_games=last_avatar["games"],
                avatar_wins=last_avatar["wins"],
                total_games=games,
                total_wins=wins,
                opponents=opponents,
                rng=rng,
            )
            avatar_bg_image = _find_avatar_image(last_avatar["name"])
        else:
            subtitle = rng.choice(_PLAYER_FALLBACK_TEMPLATES).format(
                name=display_name, wins=wins, games=games, opponents=opponents,
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
                "avatar_bg_image": avatar_bg_image,
                "elements": elements_used,
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


# ── Random Recent Event ───────────────────────────────────────

_EVENT_TEMPLATES = [
    "Won with {avatar} at {event}.",
    "{avatar} took the crown at {event}.",
    "1st place finish piloting {avatar}.",
    "Claimed victory with {avatar}.",
]

_EVENT_CACHE = {}  # {date_str: event_spotlight_dict}


def get_random_recent_event() -> dict:
    """Return a random top-8 event from the last 3 months, cached daily."""
    today = date.today().isoformat()

    if today in _EVENT_CACHE:
        return _EVENT_CACHE[today]

    try:
        from repositories.events import EventRepository

        rng = random.Random(today + "_event")
        repo = EventRepository()
        all_events = repo.get_all_events()

        # Filter to events with a date in the last 3 months
        cutoff = (date.today() - timedelta(days=90)).isoformat()
        recent = [
            e for e in all_events
            if e.get("event_date") and e["event_date"] >= cutoff
            and e.get("has_top8")
        ]

        if not recent:
            result = {"success": True, "event_spotlight": None}
            _EVENT_CACHE.clear()
            _EVENT_CACHE[today] = result
            return result

        event = rng.choice(recent)
        winner_avatar = event.get("winner_avatar")
        avatar_image = _find_avatar_image(winner_avatar) if winner_avatar else None

        if winner_avatar:
            template = rng.choice(_EVENT_TEMPLATES)
            subtitle = template.format(avatar=winner_avatar, event=event["name"])
        else:
            subtitle = f"Check out the top 8 decklists from {event['name']}."

        spotlight = {
            "type": "recent_event",
            "badge_text": "EVENT",
            "color": "purple",
            "title": event["name"],
            "subtitle": subtitle,
            "link": f"/top-8/{event['folder']}",
            "image_url": avatar_image,
            "event_date": event.get("event_date"),
            "winner_username": event.get("winner_username"),
            "winner_avatar": winner_avatar,
        }

        result = {"success": True, "event_spotlight": spotlight}
        _EVENT_CACHE.clear()
        _EVENT_CACHE[today] = result
        return result

    except Exception:
        logger.error("Failed to get random recent event", exc_info=True)
        return {"success": True, "event_spotlight": None}


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


def _extract_avatar_and_elements(deck_json: str | None) -> tuple[str | None, list[str]]:
    """Extract the main avatar name and element list from a deck JSON string."""
    if not deck_json or deck_json in ("{}", ""):
        return None, []
    try:
        deck_data = json.loads(deck_json)
        # Avatar
        avatar_name = None
        avatar_list = deck_data.get("avatar", [])
        if avatar_list:
            for av in avatar_list:
                if av and av.get("type") == "Avatar" and av.get("name"):
                    avatar_name = av.get("name")
                    break
            if not avatar_name and avatar_list[0] and avatar_list[0].get("name"):
                avatar_name = avatar_list[0].get("name")
        # Elements
        elements_set = set()
        for section in ("spellbook", "sideboard"):
            for card in deck_data.get(section, []) or []:
                card_elements = card.get("elements", "")
                if card_elements and card_elements != "None":
                    for el in card_elements.split(","):
                        el = el.strip()
                        if el in ("Earth", "Fire", "Water", "Air"):
                            elements_set.add(el)
        return avatar_name, sorted(elements_set)
    except (json.JSONDecodeError, KeyError, IndexError, TypeError, AttributeError):
        return None, []


def _get_player_deck_stats(
    user_id: str, start_date: str | None
) -> tuple[dict | None, list[str]]:
    """Get most recent avatar and its season stats for a player.

    Returns:
        (last_avatar, elements_used) where last_avatar is
        {"name": str, "wins": int, "losses": int, "games": int} or None,
        and elements_used is the sorted list of elements from that avatar's decks.
    """
    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()

        date_clause = ""
        params_base = [user_id, user_id]
        if start_date:
            date_clause = "AND timestamp >= ?"
            params_base.append(start_date)

        # Query match rows with deck data, ordered by timestamp desc
        try:
            cur.execute(
                f"""
                SELECT
                    CASE WHEN winner_id = ? THEN 1 ELSE 0 END AS did_win,
                    json_deck_data_winner,
                    json_deck_data_loser,
                    timestamp
                FROM match_records
                WHERE (winner_id = ? OR losser_id = ?)
                  AND (match_type = 'ranked' OR match_type IS NULL)
                  {date_clause}
                ORDER BY timestamp DESC
                """,
                [user_id] + params_base,
            )
            rows = cur.fetchall()
        except sqlite3.OperationalError:
            rows = []

        conn.close()

        if not rows:
            return None, []

        # Find the most recent avatar name
        last_avatar_name = None
        for row in rows:
            did_win = row[0]
            player_json = row[1] if did_win else row[2]
            avatar_name, _ = _extract_avatar_and_elements(player_json)
            if avatar_name:
                last_avatar_name = avatar_name
                break

        if not last_avatar_name:
            return None, []

        # Now compute stats for that specific avatar across all season matches
        avatar_wins = 0
        avatar_losses = 0
        avatar_elements = set()

        for row in rows:
            did_win = row[0]
            player_json = row[1] if did_win else row[2]
            avatar_name, elements = _extract_avatar_and_elements(player_json)

            if avatar_name == last_avatar_name:
                if did_win:
                    avatar_wins += 1
                else:
                    avatar_losses += 1
                avatar_elements.update(elements)

        return {
            "name": last_avatar_name,
            "wins": avatar_wins,
            "losses": avatar_losses,
            "games": avatar_wins + avatar_losses,
        }, sorted(avatar_elements)
    except Exception:
        logger.error("Failed to get player deck stats", exc_info=True)
        return None, []


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
