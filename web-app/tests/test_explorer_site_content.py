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
    assert data["sections"] == [{"title": "Who's behind the Series", "body": "Our Council:\n- Someone", "images": [], "hidden": False}]
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


def test_sections_keep_uploaded_pictures(explorer_admin_session):
    url = "/static/uploads/explorer/abc123.jpg"
    res = explorer_admin_session.post("/api/explorer/site-content", json={
        "hero_image": "/static/uploads/explorer/hero.webp",
        "sections": [{"title": "Finale photos", "body": "", "images": [url]}],
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["hero_image"] == "/static/uploads/explorer/hero.webp"
    assert data["sections"][0]["images"] == [url]


def test_outside_pictures_are_rejected(explorer_admin_session):
    res = explorer_admin_session.post("/api/explorer/site-content", json={
        "sections": [{"title": "x", "images": ["https://evil.example/x.png"]}],
    })
    assert res.status_code == 400
    res = explorer_admin_session.post("/api/explorer/site-content", json={"hero_image": "/static/uploads/explorer/../../x.png"})
    assert res.status_code == 400


def test_upload_saves_pictures(explorer_admin_session, tmp_path, monkeypatch):
    import io
    import webapp_config
    monkeypatch.setattr(webapp_config, "EXPLORER_UPLOADS_DIR", tmp_path)
    res = explorer_admin_session.post(
        "/api/explorer/upload-image",
        data={"image": [(io.BytesIO(b"\x89PNG fake"), "photo.png")]},
        content_type="multipart/form-data",
    )
    assert res.status_code == 200
    url = res.get_json()["urls"][0]
    assert url.startswith("/static/uploads/explorer/") and url.endswith(".png")
    assert (tmp_path / url.rsplit("/", 1)[1]).exists()


def test_upload_rejects_other_files(explorer_admin_session):
    import io
    res = explorer_admin_session.post(
        "/api/explorer/upload-image",
        data={"image": [(io.BytesIO(b"hi"), "notes.exe")]},
        content_type="multipart/form-data",
    )
    assert res.status_code == 400


def test_regular_user_cannot_upload(user_session):
    import io
    res = user_session.post(
        "/api/explorer/upload-image",
        data={"image": [(io.BytesIO(b"x"), "a.png")]},
        content_type="multipart/form-data",
    )
    assert res.status_code in (401, 403)
