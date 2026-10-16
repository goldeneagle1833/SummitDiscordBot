"""Discord server icons for community invite links.

Looks up each invite through Discord's public invite endpoint (no bot token
needed) and builds the guild's CDN icon URL. Results are cached per worker so
the Community page doesn't hit Discord on every load.
"""

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

logger = logging.getLogger(__name__)

INVITE_API = "https://discord.com/api/v10/invites/{code}"
ICON_URL = "https://cdn.discordapp.com/icons/{guild_id}/{icon}.{ext}?size=128"

SUCCESS_TTL_SECONDS = 6 * 60 * 60
FAILURE_TTL_SECONDS = 30 * 60
REQUEST_TIMEOUT_SECONDS = 5
MAX_WORKERS = 6

_INVITE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord\.gg|discord(?:app)?\.com/invite)/([A-Za-z0-9-]+)",
    re.IGNORECASE,
)

# invite code -> (icon_url or None, expires_at)
_cache: dict[str, tuple[str | None, float]] = {}
_lock = threading.Lock()


def parse_invite_code(invite_url: str | None) -> str | None:
    """Pull the invite code out of a discord.gg / discord.com/invite link."""
    if not invite_url:
        return None
    match = _INVITE_RE.search(invite_url.strip())
    return match.group(1) if match else None


def icon_url_from_invite(data: dict) -> str | None:
    """Build the CDN icon URL from an invite API response."""
    guild = (data or {}).get("guild") or {}
    guild_id, icon = guild.get("id"), guild.get("icon")
    if not guild_id or not icon:
        return None
    ext = "gif" if icon.startswith("a_") else "png"
    return ICON_URL.format(guild_id=guild_id, icon=icon, ext=ext)


def _fetch_icon(code: str) -> str | None:
    try:
        resp = requests.get(
            INVITE_API.format(code=code),
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": "SorcerersSummit (https://sorcererssummit.com, 1.0)"},
        )
        if resp.status_code != 200:
            logger.info("Discord invite %s returned %s", code, resp.status_code)
            return None
        return icon_url_from_invite(resp.json())
    except Exception:
        logger.warning("Failed to fetch Discord invite %s", code, exc_info=True)
        return None


def get_icon_urls(invite_urls: list[str]) -> dict[str, str | None]:
    """Map each invite URL to its server icon URL (None when unknown)."""
    now = time.time()
    codes = {url: parse_invite_code(url) for url in invite_urls}

    with _lock:
        missing = {
            c for c in codes.values()
            if c and (c not in _cache or _cache[c][1] <= now)
        }

    if missing:
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(missing))) as pool:
            results = dict(zip(missing, pool.map(_fetch_icon, missing)))
        with _lock:
            for code, icon in results.items():
                ttl = SUCCESS_TTL_SECONDS if icon else FAILURE_TTL_SECONDS
                _cache[code] = (icon, now + ttl)

    with _lock:
        return {
            url: (_cache.get(code, (None, 0))[0] if code else None)
            for url, code in codes.items()
        }


def add_icons(servers: list[dict]) -> list[dict]:
    """Attach an icon_url to each Discord server dict."""
    icons = get_icon_urls([s.get("invite_url") or "" for s in servers])
    for s in servers:
        s["icon_url"] = icons.get(s.get("invite_url") or "")
    return servers
