"""The Explorer Series mini-site's editable text."""


def test_defaults_until_an_admin_saves(client):
    data = client.get("/api/explorer/site-content").get_json()
    assert data["title"] == "The Explorer Series"
    assert data["sections"] == []
    assert data["show_points_guide"] is True


def test_explorer_admin_can_edit(explorer_admin_session):
    res = explorer_admin_session.post("/api/explorer/site-content", json={
        "title": "Explorer Series 2027",
        "discord_url": "https://discord.gg/example",
        "show_points_guide": False,
        "sections": [
            {"title": "Who's behind the Series", "body": "Our Council:\n- Someone"},
            {"title": "", "body": ""},
        ],
        "unknown": "dropped",
    })
    assert res.status_code == 200
    data = explorer_admin_session.get("/api/explorer/site-content").get_json()
    assert data["title"] == "Explorer Series 2027"
    assert data["discord_url"] == "https://discord.gg/example"
    assert data["show_points_guide"] is False
    assert data["sections"] == [{"title": "Who's behind the Series", "body": "Our Council:\n- Someone", "hidden": False}]
    assert "unknown" not in data
    # Fields left out keep their defaults
    assert data["intro"].startswith("A player-run annual circuit")


def test_regular_user_cannot_edit(user_session):
    res = user_session.post("/api/explorer/site-content", json={"title": "Hacked"})
    assert res.status_code in (401, 403)


def test_bad_links_are_rejected(explorer_admin_session):
    res = explorer_admin_session.post("/api/explorer/site-content", json={"discord_url": "javascript:alert(1)"})
    assert res.status_code == 400


def test_overlong_text_is_rejected(explorer_admin_session):
    res = explorer_admin_session.post("/api/explorer/site-content", json={"title": "x" * 500})
    assert res.status_code == 400
