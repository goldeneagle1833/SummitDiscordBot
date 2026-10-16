"""Recent Decks link previews: deck-site links only."""

import services.link_previews as link_previews


def test_previews_deck_links_and_ignores_other_sites(client, monkeypatch):
    fetched = []

    def fake_fetch(url):
        fetched.append(url)
        return {"title": "Fire Aggro", "image": "https://curiosa.io/og.png"}

    monkeypatch.setattr(link_previews, "_fetch_preview", fake_fetch)
    monkeypatch.setattr(link_previews, "_cache", {})
    deck = "https://curiosa.io/decks/cmc2ylc3n001cl50461dx7nwr"
    resp = client.get("/api/link-previews/decks", query_string=[("url", deck), ("url", "https://example.com/")])
    assert resp.status_code == 200
    previews = resp.get_json()["previews"]
    assert previews == {deck: {"title": "Fire Aggro", "image": "https://curiosa.io/og.png"}}
    assert fetched == [deck]


def test_no_urls_fetches_nothing(client, monkeypatch):
    monkeypatch.setattr(link_previews, "_fetch_preview", lambda url: (_ for _ in ()).throw(AssertionError))
    assert client.get("/api/link-previews/decks").get_json() == {"previews": {}}
