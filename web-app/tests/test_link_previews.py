"""Tests for website link previews on the Community page."""

from unittest.mock import patch, MagicMock

import pytest

from services import link_previews

PAGE = """<html><head>
<title>Fallback Title</title>
<meta property="og:title" content="Curiosa: Sorcery Decks">
<meta property="og:description" content="Build and share decks.">
<meta property="og:image" content="/img/card.png">
<meta property="og:site_name" content="Curiosa">
<meta name="theme-color" content="#d4af37">
<link rel="icon" href="/favicon.png">
</head><body><meta property="og:title" content="ignored"></body></html>"""


@pytest.fixture(autouse=True)
def clear_cache():
    link_previews._cache.clear()
    yield
    link_previews._cache.clear()


def test_parse_preview_og_tags():
    p = link_previews.parse_preview(PAGE, "https://curiosa.io/decks")
    assert p == {
        "title": "Curiosa: Sorcery Decks",
        "description": "Build and share decks.",
        "image": "https://curiosa.io/img/card.png",
        "site_name": "Curiosa",
        "icon": "https://curiosa.io/favicon.png",
        "color": "#d4af37",
    }


def test_parse_preview_falls_back_to_title_and_description():
    html = '<head><title> Plain Site </title><meta name="description" content="Hello"></head>'
    p = link_previews.parse_preview(html, "https://example.com/")
    assert p["title"] == "Plain Site"
    assert p["description"] == "Hello"
    assert p["image"] is None
    assert p["icon"] == "https://example.com/favicon.ico"


def test_parse_preview_nothing_usable():
    assert link_previews.parse_preview("<html><body>hi</body></html>", "https://x.com") is None


def test_blocks_private_hosts():
    assert link_previews._is_public_host("http://127.0.0.1/") is False
    assert link_previews._is_public_host("http://10.0.0.5/") is False
    assert link_previews._is_public_host("ftp://example.com/") is False
    assert link_previews._fetch_preview("http://localhost:5000/") is None


def _resp(status=200, body=PAGE, ctype="text/html; charset=utf-8"):
    r = MagicMock()
    r.status_code = status
    r.is_redirect = False
    r.headers = {"Content-Type": ctype}
    r.encoding = "utf-8"
    r.iter_content.return_value = [body.encode()]
    return r


def test_add_previews_fetches_once_and_caches():
    sites = [{"name": "Curiosa", "url": "https://curiosa.io/"}, {"name": "Broken", "url": "https://bad.example/"}]

    def fake_get(url, **kwargs):
        return _resp() if "curiosa" in url else _resp(status=404)

    with patch.object(link_previews, "_is_public_host", return_value=True), \
            patch.object(link_previews.requests, "get", side_effect=fake_get) as mock_get:
        link_previews.add_previews(sites)
        link_previews.add_previews([dict(s) for s in sites])
        assert mock_get.call_count == 2

    assert sites[0]["preview"]["title"] == "Curiosa: Sorcery Decks"
    assert sites[1]["preview"] is None


def test_non_html_is_skipped():
    with patch.object(link_previews, "_is_public_host", return_value=True), \
            patch.object(link_previews.requests, "get", return_value=_resp(ctype="application/pdf")):
        assert link_previews._fetch_preview("https://example.com/file.pdf") is None
