"""Tests for Discord server icons on the Community page."""

from unittest.mock import patch, MagicMock

import pytest

from services import discord_icons


@pytest.fixture(autouse=True)
def clear_cache():
    discord_icons._cache.clear()
    yield
    discord_icons._cache.clear()


def _resp(status, payload=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload or {}
    return r


@pytest.mark.parametrize("url,code", [
    ("https://discord.gg/abc123", "abc123"),
    ("discord.gg/Sorcery-OH", "Sorcery-OH"),
    ("https://discord.com/invite/xyz", "xyz"),
    ("https://discordapp.com/invite/xyz?event=1", "xyz"),
    ("https://example.com/abc", None),
    ("", None),
    (None, None),
])
def test_parse_invite_code(url, code):
    assert discord_icons.parse_invite_code(url) == code


def test_icon_url_static_and_animated():
    assert discord_icons.icon_url_from_invite({"guild": {"id": "1", "icon": "hash"}}) == \
        "https://cdn.discordapp.com/icons/1/hash.png?size=128"
    assert discord_icons.icon_url_from_invite({"guild": {"id": "1", "icon": "a_hash"}}) == \
        "https://cdn.discordapp.com/icons/1/a_hash.gif?size=128"
    assert discord_icons.icon_url_from_invite({"guild": {"id": "1", "icon": None}}) is None
    assert discord_icons.icon_url_from_invite({}) is None


def test_add_icons_fetches_once_and_caches():
    servers = [
        {"name": "A", "invite_url": "https://discord.gg/aaa"},
        {"name": "B", "invite_url": "https://discord.gg/bbb"},
        {"name": "C", "invite_url": "not a link"},
    ]

    def fake_get(url, **kwargs):
        if url.endswith("/aaa"):
            return _resp(200, {"guild": {"id": "10", "icon": "iconA"}})
        return _resp(404)

    with patch.object(discord_icons.requests, "get", side_effect=fake_get) as mock_get:
        discord_icons.add_icons(servers)
        assert mock_get.call_count == 2
        discord_icons.add_icons([dict(s) for s in servers])
        assert mock_get.call_count == 2  # served from cache

    assert servers[0]["icon_url"] == "https://cdn.discordapp.com/icons/10/iconA.png?size=128"
    assert servers[1]["icon_url"] is None
    assert servers[2]["icon_url"] is None


def test_network_error_returns_none():
    with patch.object(discord_icons.requests, "get", side_effect=Exception("boom")):
        out = discord_icons.add_icons([{"name": "A", "invite_url": "https://discord.gg/aaa"}])
    assert out[0]["icon_url"] is None
