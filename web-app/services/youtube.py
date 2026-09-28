"""YouTube service for fetching latest videos from channels."""

import json
import logging
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Optional
import requests

logger = logging.getLogger(__name__)

from repositories.community import CommunityRepository

# Hardcoded fallback channels (used when DB is empty or unavailable)
_FALLBACK_CHANNELS = {
    "goldeneagle": {
        "name": "GoldenEagle",
        "channel_id": "UCzWglR4ytbyq0aAfWrNaMHw",
        "channel_url": "https://www.youtube.com/channel/UCzWglR4ytbyq0aAfWrNaMHw",
    },
    "cj": {
        "name": "Old Fashioned Nerds",
        "channel_id": "UCRZw6WkGb5O34JCUTPCFvDQ",
        "channel_url": "https://www.youtube.com/@Oldfashionednerds",
    },
}

# YouTube serves a consent interstitial or a bot page to bare clients, so
# look like a normal browser. SOCS=CAI opts out of the EU cookie-consent wall.
_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
_REQUEST_COOKIES = {"SOCS": "CAI"}

_YT_INITIAL_DATA_RE = re.compile(r"var ytInitialData\s*=\s*(\{.*?\});\s*</script>", re.S)

# Cache for YouTube video data
_video_cache: dict = {}
_cache_expiry: Optional[datetime] = None
CACHE_DURATION_MINUTES = 30


def _load_channels() -> dict:
    """Load YouTube channels from the database, falling back to hardcoded defaults."""
    try:
        repo = CommunityRepository()
        db_channels = repo.get_youtube_channels()
        if db_channels:
            # Convert DB rows to the same dict format, keyed by lowercased name
            result = {
                ch["name"].lower().replace(" ", ""): {
                    "name": ch["name"],
                    "channel_id": ch["channel_id"],
                    "channel_url": ch["channel_url"],
                }
                for ch in db_channels
            }
            logger.info("Loaded %d YouTube channels from DB", len(result))
            return result
    except Exception as e:
        logger.warning("Failed to load YouTube channels from DB: %s", e)
    return _FALLBACK_CHANNELS


def get_youtube_rss_url(channel_id: str) -> str:
    """Get the RSS feed URL for a YouTube channel."""
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def get_youtube_channel_videos_url(channel_id: str) -> str:
    """Get the public Videos-tab URL for a YouTube channel."""
    return f"https://www.youtube.com/channel/{channel_id}/videos"


def _video_from_lockup(lockup: dict) -> dict | None:
    """Extract a video from the current YouTube ``lockupViewModel`` layout."""
    if lockup.get("contentType") not in (None, "LOCKUP_CONTENT_TYPE_VIDEO"):
        return None
    video_id = lockup.get("contentId")
    title = (
        lockup.get("metadata", {})
        .get("lockupMetadataViewModel", {})
        .get("title", {})
        .get("content")
    )
    if not video_id or not title:
        return None

    published_text = None
    rows = (
        lockup.get("metadata", {})
        .get("lockupMetadataViewModel", {})
        .get("metadata", {})
        .get("contentMetadataViewModel", {})
        .get("metadataRows", [])
    )
    for row in rows:
        for part in row.get("metadataParts", []):
            text = part.get("text", {}).get("content", "")
            if text.endswith("ago"):
                published_text = text
                break
        if published_text:
            break

    return {"video_id": video_id, "title": title, "published_text": published_text}


def _video_from_renderer(renderer: dict) -> dict | None:
    """Extract a video from the older YouTube ``videoRenderer`` layout."""
    video_id = renderer.get("videoId")
    runs = renderer.get("title", {}).get("runs") or []
    title = runs[0].get("text") if runs else renderer.get("title", {}).get("simpleText")
    if not video_id or not title:
        return None
    return {
        "video_id": video_id,
        "title": title,
        "published_text": renderer.get("publishedTimeText", {}).get("simpleText"),
    }


def _find_first_video(node) -> dict | None:
    """Depth-first search of ytInitialData for the first video entry.

    The Videos tab lists uploads newest-first, so the first hit is the
    latest video. Handles both the current and the legacy item layouts.
    """
    if isinstance(node, dict):
        if "lockupViewModel" in node:
            video = _video_from_lockup(node["lockupViewModel"])
            if video:
                return video
        if "videoRenderer" in node:
            video = _video_from_renderer(node["videoRenderer"])
            if video:
                return video
        for value in node.values():
            video = _find_first_video(value)
            if video:
                return video
    elif isinstance(node, list):
        for value in node:
            video = _find_first_video(value)
            if video:
                return video
    return None


def parse_youtube_channel_page(html: str) -> dict | None:
    """Parse a channel's Videos page and extract its latest video.

    YouTube embeds the page state as ``var ytInitialData = {...};``. This is
    the fallback for when the public RSS feed is unavailable.
    """
    match = _YT_INITIAL_DATA_RE.search(html)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except ValueError:
        return None

    channel_name = (
        data.get("metadata", {})
        .get("channelMetadataRenderer", {})
        .get("title")
    ) or "Unknown"

    # Only look inside the selected tab so we don't pick up a channel trailer
    # or a featured video from another tab's data.
    tabs = (
        data.get("contents", {})
        .get("twoColumnBrowseResultsRenderer", {})
        .get("tabs", [])
    )
    selected = [t["tabRenderer"] for t in tabs if t.get("tabRenderer", {}).get("selected")]
    video = _find_first_video(selected[0].get("content") if selected else data)
    if not video:
        return None

    video_id = video["video_id"]
    return {
        "channel_name": channel_name,
        "video_id": video_id,
        "title": video["title"],
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        "published": None,
        "published_text": video.get("published_text"),
    }


def parse_youtube_rss(xml_content: str) -> dict | None:
    """Parse YouTube RSS feed and extract latest video info."""
    try:
        root = ET.fromstring(xml_content)

        # YouTube RSS uses Atom namespace
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "yt": "http://www.youtube.com/xml/schemas/2015",
            "media": "http://search.yahoo.com/mrss/",
        }

        # Get channel title
        channel_title = root.find("atom:title", ns)
        channel_name = channel_title.text if channel_title is not None else "Unknown"

        # Get first entry (latest video)
        entry = root.find("atom:entry", ns)
        if entry is None:
            return None

        video_id = entry.find("yt:videoId", ns)
        title = entry.find("atom:title", ns)
        published = entry.find("atom:published", ns)

        # Get thumbnail from media:group
        media_group = entry.find("media:group", ns)
        thumbnail_url = None
        if media_group is not None:
            thumbnail = media_group.find("media:thumbnail", ns)
            if thumbnail is not None:
                thumbnail_url = thumbnail.get("url")

        if video_id is None or title is None:
            return None

        return {
            "channel_name": channel_name,
            "video_id": video_id.text,
            "title": title.text,
            "url": f"https://www.youtube.com/watch?v={video_id.text}",
            "thumbnail": thumbnail_url or f"https://img.youtube.com/vi/{video_id.text}/mqdefault.jpg",
            "published": published.text if published is not None else None,
        }
    except ET.ParseError:
        return None


def _fetch_from_rss(channel_key: str, channel: dict) -> dict | None:
    rss_url = get_youtube_rss_url(channel["channel_id"])
    try:
        response = requests.get(
            rss_url, headers=_REQUEST_HEADERS, cookies=_REQUEST_COOKIES, timeout=10
        )
        response.raise_for_status()
        return parse_youtube_rss(response.text)
    except requests.RequestException as e:
        logger.info("RSS unavailable for channel %s (%s): %s", channel_key, channel["channel_id"], e)
        return None


def _fetch_from_channel_page(channel_key: str, channel: dict, attempts: int = 2) -> dict | None:
    page_url = get_youtube_channel_videos_url(channel["channel_id"])
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(
                page_url, headers=_REQUEST_HEADERS, cookies=_REQUEST_COOKIES, timeout=15
            )
            response.raise_for_status()
        except requests.RequestException as e:
            logger.warning(
                "Failed to fetch channel page for %s (%s), attempt %d/%d: %s",
                channel_key, channel["channel_id"], attempt, attempts, e,
            )
            continue

        video = parse_youtube_channel_page(response.text)
        if video:
            return video
        # YouTube occasionally serves a page variant without the upload list
        # (consent wall, bot check, or an empty tab). Log enough to tell which.
        logger.warning(
            "Channel page for %s (%s) had no parseable video, attempt %d/%d "
            "(status=%s, bytes=%d, has_initial_data=%s, final_url=%s)",
            channel_key, channel["channel_id"], attempt, attempts,
            response.status_code, len(response.text),
            bool(_YT_INITIAL_DATA_RE.search(response.text)), response.url,
        )
    return None


def fetch_latest_video(channel_key: str, channels: dict) -> dict | None:
    """Fetch the latest video from a YouTube channel.

    Tries the lightweight RSS feed first. YouTube stopped serving those feeds
    (they now 404 for every channel), so fall back to parsing the channel's
    public Videos page, which still embeds the upload list.
    """
    if channel_key not in channels:
        return None

    channel = channels[channel_key]
    video_info = _fetch_from_rss(channel_key, channel)
    if video_info is None:
        video_info = _fetch_from_channel_page(channel_key, channel)
    if video_info is None:
        logger.warning("No latest video found for channel %s (%s)", channel_key, channel["channel_id"])
        return None

    video_info["channel_key"] = channel_key
    video_info["channel_display_name"] = channel["name"]
    video_info["channel_url"] = channel["channel_url"]
    return video_info


def get_latest_videos() -> dict:
    """Get latest videos from all configured channels with caching."""
    global _video_cache, _cache_expiry

    now = datetime.now()

    # Return cached data if still valid
    if _cache_expiry and now < _cache_expiry and _video_cache:
        return _video_cache

    # Load channels from DB (or fallback)
    channels = _load_channels()

    # Fetch fresh data in parallel
    videos = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(fetch_latest_video, channel_key, channels): channel_key
            for channel_key in channels
        }
        for future in as_completed(futures):
            channel_key = futures[future]
            try:
                video = future.result()
                if video:
                    videos[channel_key] = video
            except Exception as e:
                logger.warning("Unexpected error fetching channel %s: %s", channel_key, e)

    # Update cache
    _video_cache = videos
    _cache_expiry = now + timedelta(minutes=CACHE_DURATION_MINUTES)

    return videos
