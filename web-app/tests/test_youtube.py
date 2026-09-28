"""Tests for the YouTube latest-video service."""

import json
from unittest.mock import MagicMock, patch

import requests

from services import youtube


def _lockup_page(video_id="abc123XYZ_-", title="Latest Upload", published="3w ago",
                 channel_title="Test Channel", content_type="LOCKUP_CONTENT_TYPE_VIDEO"):
    """Build a minimal channel Videos page in YouTube's current layout."""
    lockup = {
        "lockupViewModel": {
            "contentId": video_id,
            "contentType": content_type,
            "metadata": {
                "lockupMetadataViewModel": {
                    "title": {"content": title},
                    "metadata": {
                        "contentMetadataViewModel": {
                            "metadataRows": [
                                {"metadataParts": [
                                    {"text": {"content": "3.2K"}},
                                    {"text": {"content": published}},
                                ]}
                            ]
                        }
                    },
                }
            },
        }
    }
    tab = {"tabRenderer": {"title": "Videos", "selected": True,
                           "content": {"richGridRenderer": {"contents": [
                               {"richItemRenderer": {"content": lockup}}]}}}}
    data = {
        "metadata": {"channelMetadataRenderer": {"title": channel_title}},
        "contents": {"twoColumnBrowseResultsRenderer": {"tabs": [
            {"tabRenderer": {"title": "Home", "selected": None}},
            tab,
        ]}},
    }
    return f"<html><script>var ytInitialData = {json.dumps(data)};</script></html>"


def _legacy_page(video_id="legacy00001", title="Old Layout Video"):
    data = {
        "metadata": {"channelMetadataRenderer": {"title": "Legacy Channel"}},
        "contents": {"twoColumnBrowseResultsRenderer": {"tabs": [
            {"tabRenderer": {"selected": True, "content": {"richGridRenderer": {"contents": [
                {"richItemRenderer": {"content": {"videoRenderer": {
                    "videoId": video_id,
                    "title": {"runs": [{"text": title}]},
                    "publishedTimeText": {"simpleText": "2 days ago"},
                }}}}
            ]}}}},
        ]}},
    }
    return f"<html><script>var ytInitialData = {json.dumps(data)};</script></html>"


RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/">
  <title>RSS Channel</title>
  <entry>
    <yt:videoId>rssvideo001</yt:videoId>
    <title>From RSS</title>
    <published>2026-09-01T00:00:00+00:00</published>
    <media:group><media:thumbnail url="https://i.ytimg.com/vi/rssvideo001/hqdefault.jpg"/></media:group>
  </entry>
</feed>"""

EMPTY_RSS = '<feed xmlns="http://www.w3.org/2005/Atom"><title>x</title></feed>'

CHANNELS = {
    "test": {
        "name": "Test Channel",
        "channel_id": "UCtest",
        "channel_url": "https://www.youtube.com/@test",
    }
}


def _response(status=200, text="", url="https://example"):
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    resp.url = url
    if status >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"{status} Client Error")
    else:
        resp.raise_for_status.return_value = None
    return resp


class TestParseChannelPage:
    def test_extracts_latest_video_from_current_layout(self):
        video = youtube.parse_youtube_channel_page(_lockup_page())
        assert video == {
            "channel_name": "Test Channel",
            "video_id": "abc123XYZ_-",
            "title": "Latest Upload",
            "url": "https://www.youtube.com/watch?v=abc123XYZ_-",
            "thumbnail": "https://i.ytimg.com/vi/abc123XYZ_-/hqdefault.jpg",
            "published": None,
            "published_text": "3w ago",
        }

    def test_extracts_from_legacy_video_renderer_layout(self):
        video = youtube.parse_youtube_channel_page(_legacy_page())
        assert video["video_id"] == "legacy00001"
        assert video["title"] == "Old Layout Video"
        assert video["published_text"] == "2 days ago"
        assert video["channel_name"] == "Legacy Channel"

    def test_returns_none_without_initial_data(self):
        assert youtube.parse_youtube_channel_page("<html><body>consent wall</body></html>") is None

    def test_returns_none_for_malformed_json(self):
        html = "<script>var ytInitialData = {not json};</script>"
        assert youtube.parse_youtube_channel_page(html) is None

    def test_returns_none_when_no_videos_listed(self):
        data = {"contents": {"twoColumnBrowseResultsRenderer": {"tabs": [
            {"tabRenderer": {"selected": True, "content": {"richGridRenderer": {"contents": []}}}}]}}}
        html = f"<script>var ytInitialData = {json.dumps(data)};</script>"
        assert youtube.parse_youtube_channel_page(html) is None

    def test_skips_non_video_lockups(self):
        """A playlist or shelf lockup must not be mistaken for the latest video."""
        html = _lockup_page(content_type="LOCKUP_CONTENT_TYPE_PLAYLIST")
        assert youtube.parse_youtube_channel_page(html) is None


class TestFetchLatestVideo:
    def test_uses_rss_when_available(self):
        with patch.object(youtube.requests, "get", return_value=_response(200, RSS_XML)) as get:
            video = youtube.fetch_latest_video("test", CHANNELS)
        assert get.call_count == 1
        assert video["video_id"] == "rssvideo001"
        assert video["channel_display_name"] == "Test Channel"
        assert video["channel_url"] == "https://www.youtube.com/@test"
        assert video["channel_key"] == "test"

    def test_falls_back_to_channel_page_when_rss_404s(self):
        responses = [_response(404), _response(200, _lockup_page())]
        with patch.object(youtube.requests, "get", side_effect=responses) as get:
            video = youtube.fetch_latest_video("test", CHANNELS)
        assert get.call_count == 2
        assert get.call_args_list[0].args[0] == youtube.get_youtube_rss_url("UCtest")
        assert get.call_args_list[1].args[0] == youtube.get_youtube_channel_videos_url("UCtest")
        assert video["video_id"] == "abc123XYZ_-"
        assert video["channel_display_name"] == "Test Channel"

    def test_falls_back_when_rss_has_no_entries(self):
        responses = [_response(200, EMPTY_RSS), _response(200, _lockup_page())]
        with patch.object(youtube.requests, "get", side_effect=responses):
            video = youtube.fetch_latest_video("test", CHANNELS)
        assert video["video_id"] == "abc123XYZ_-"

    def test_retries_page_once_when_first_copy_is_unparseable(self):
        responses = [_response(404), _response(200, "<html>bot check</html>"), _response(200, _lockup_page())]
        with patch.object(youtube.requests, "get", side_effect=responses) as get:
            video = youtube.fetch_latest_video("test", CHANNELS)
        assert get.call_count == 3
        assert video["video_id"] == "abc123XYZ_-"

    def test_returns_none_when_everything_fails(self):
        responses = [_response(404), _response(503), requests.ConnectionError("down")]
        with patch.object(youtube.requests, "get", side_effect=responses):
            assert youtube.fetch_latest_video("test", CHANNELS) is None

    def test_unknown_channel_makes_no_requests(self):
        with patch.object(youtube.requests, "get") as get:
            assert youtube.fetch_latest_video("nope", CHANNELS) is None
        get.assert_not_called()


class TestGetLatestVideos:
    def test_aggregates_and_caches(self):
        youtube._video_cache = {}
        youtube._cache_expiry = None
        try:
            with patch.object(youtube, "_load_channels", return_value=CHANNELS), \
                 patch.object(youtube, "fetch_latest_video", return_value={"video_id": "v1"}) as fetch:
                first = youtube.get_latest_videos()
                second = youtube.get_latest_videos()
            assert first == {"test": {"video_id": "v1"}}
            assert second is first
            assert fetch.call_count == 1
        finally:
            youtube._video_cache = {}
            youtube._cache_expiry = None
