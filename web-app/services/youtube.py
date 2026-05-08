"""YouTube service for fetching latest videos from channels."""

import logging
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


def fetch_latest_video(channel_key: str, channels: dict) -> dict | None:
    """Fetch the latest video from a YouTube channel."""
    if channel_key not in channels:
        return None

    channel = channels[channel_key]
    rss_url = get_youtube_rss_url(channel["channel_id"])

    try:
        response = requests.get(rss_url, timeout=10)
        response.raise_for_status()

        video_info = parse_youtube_rss(response.text)
        if video_info:
            video_info["channel_key"] = channel_key
            video_info["channel_display_name"] = channel["name"]
            video_info["channel_url"] = channel["channel_url"]
        return video_info
    except requests.RequestException as e:
        logger.warning("Failed to fetch RSS for channel %s (%s): %s", channel_key, channel["channel_id"], e)
        return None


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
