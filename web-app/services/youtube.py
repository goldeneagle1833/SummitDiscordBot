"""YouTube service for fetching latest videos from channels."""

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional
import requests

# YouTube channel configuration
YOUTUBE_CHANNELS = {
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


def fetch_latest_video(channel_key: str) -> dict | None:
    """Fetch the latest video from a YouTube channel."""
    if channel_key not in YOUTUBE_CHANNELS:
        return None

    channel = YOUTUBE_CHANNELS[channel_key]
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
    except requests.RequestException:
        return None


def get_latest_videos() -> dict:
    """Get latest videos from all configured channels with caching."""
    global _video_cache, _cache_expiry

    now = datetime.now()

    # Return cached data if still valid
    if _cache_expiry and now < _cache_expiry and _video_cache:
        return _video_cache

    # Fetch fresh data
    videos = {}
    for channel_key in YOUTUBE_CHANNELS:
        video = fetch_latest_video(channel_key)
        if video:
            videos[channel_key] = video

    # Update cache
    _video_cache = videos
    _cache_expiry = now + timedelta(minutes=CACHE_DURATION_MINUTES)

    return videos
