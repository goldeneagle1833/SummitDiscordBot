"""Players' own profile pictures: Discord default, card art, or an upload."""

import io
import sqlite3

import pytest
from PIL import Image

import routes.api.players as players_routes
import utils.profile_pictures as pictures


@pytest.fixture
def profile(match_db):
    conn = sqlite3.connect(str(match_db))
    conn.execute(
        "INSERT INTO user_profiles (user_id, provider, display_name, avatar, first_login_at, last_login_at)"
        " VALUES ('100', 'discord', 'Alpha', 'abc123', 'now', 'now')"
    )
    conn.commit()
    conn.close()


@pytest.fixture(autouse=True)
def folders(tmp_path, monkeypatch):
    uploads = tmp_path / "profile-pictures"
    uploads.mkdir()
    cards = tmp_path / "card_images"
    cards.mkdir()
    # A portrait card like the real ones (744 x 1039): red name bar, blue art, grey text box
    card = Image.new("RGB", (744, 1039), "grey")
    card.paste(Image.new("RGB", (744, 80), "red"), (0, 0))
    card.paste(Image.new("RGB", (744, 660), "blue"), (0, 80))
    card.save(cards / "bet-pudge_butcher-b-s.webp", "WEBP")
    monkeypatch.setattr(pictures, "PROFILE_PICTURE_UPLOADS_DIR", uploads)
    monkeypatch.setattr(pictures, "CARD_IMAGES_DIR", cards)
    from repositories.card_catalog import CardCatalogRepository
    monkeypatch.setattr(CardCatalogRepository, "get_all_card_names", lambda self: ["Pudge Butcher", "No Art"])
    monkeypatch.setattr(
        players_routes, "resolve_card_image",
        lambda name: "bet-pudge_butcher-b-s.webp" if name == "Pudge Butcher" else None,
    )
    return uploads


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = f"user{user_id}"


def _image(fmt="PNG", size=(800, 600), color="green", **save):
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, fmt, **save)
    return out.getvalue()


def _upload(client, data, name="me.png", **form):
    return client.post(
        "/api/player/100/profile-picture/upload",
        data={"image": (io.BytesIO(data), name), **form},
        content_type="multipart/form-data",
    )


DISCORD = "https://cdn.discordapp.com/avatars/100/abc123.png?size=256"


def test_discord_picture_is_the_default(client, profile):
    _login(client, "100")
    assert client.get("/api/player/100/profile-picture").get_json() == {
        "kind": "discord", "card": None, "url": DISCORD, "discord_url": DISCORD,
    }


def test_upload_is_squared_resized_and_shown(client, profile, folders):
    _login(client, "100")
    resp = _upload(client, _image(size=(1200, 700)))
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["kind"] == "upload"
    assert body["url"].startswith("/static/uploads/profile-pictures/100-")
    assert body["discord_url"] == DISCORD
    saved = list(folders.iterdir())
    assert len(saved) == 1
    img = Image.open(saved[0])
    assert img.format == "WEBP" and img.size == (400, 400)
    # The player search shows it too
    found = client.get("/api/players/search?q=Alp").get_json()["players"]
    assert found[0]["picture_url"] == body["url"]


def test_upload_strips_photo_metadata(client, profile, folders):
    _login(client, "100")
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # camera make
    resp = _upload(client, _image("JPEG", exif=exif.tobytes()), name="photo.jpg")
    assert resp.status_code == 200
    img = Image.open(next(folders.iterdir()))
    assert not img.getexif()


def test_crop_box_picks_the_part_shown_in_the_picker(client, profile, folders):
    _login(client, "100")
    src = Image.new("RGB", (1000, 500), "white")
    src.paste(Image.new("RGB", (500, 500), "red"), (500, 0))
    out = io.BytesIO()
    src.save(out, "PNG")
    resp = _upload(client, out.getvalue(), crop_x="0.5", crop_y="0", crop_size="1")
    assert resp.status_code == 200
    r, g, b = Image.open(next(folders.iterdir())).convert("RGB").getpixel((200, 200))
    assert r > 200 and g < 60


def test_new_picture_replaces_the_old_file(client, profile, folders):
    _login(client, "100")
    _upload(client, _image())
    _upload(client, _image(color="yellow"))
    assert len(list(folders.iterdir())) == 1
    client.put("/api/player/100/profile-picture", json={"kind": "discord"})
    assert list(folders.iterdir()) == []
    assert client.get("/api/player/100/profile-picture").get_json()["kind"] == "discord"


@pytest.mark.parametrize("data,name", [
    (b"not a picture at all", "x.png"),
    (b"%PDF-1.4 something", "doc.pdf"),
    (b"", "empty.png"),
])
def test_rejects_files_that_are_not_pictures(client, profile, folders, data, name):
    _login(client, "100")
    resp = _upload(client, data, name=name)
    assert resp.status_code == 400
    assert list(folders.iterdir()) == []


def test_rejects_pictures_over_5_mb(client, profile, folders, monkeypatch):
    monkeypatch.setattr(pictures, "MAX_UPLOAD_BYTES", 1000)
    monkeypatch.setattr(players_routes, "MAX_PICTURE_UPLOAD_BYTES", 1000)
    _login(client, "100")
    resp = _upload(client, _image(size=(400, 400)) + b"\0" * 2000)
    assert resp.status_code == 400
    assert "5 MB" in resp.get_json()["error"]


def test_card_art_is_cropped_from_the_card(client, profile, folders):
    _login(client, "100")
    resp = client.put("/api/player/100/profile-picture", json={"kind": "card", "card": "pudge butcher"})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["kind"] == "card" and body["card"] == "Pudge Butcher"
    img = Image.open(next(folders.iterdir())).convert("RGB")
    assert img.size == (400, 400)
    # Only the art: no name bar at the top, no text box at the bottom
    for y in (5, 200, 395):
        r, g, b = img.getpixel((200, y))
        assert b > 180 and r < 60, (y, (r, g, b))
    # The profile names the card, for the art credit
    profile_body = client.get("/api/player/100").get_json()
    assert profile_body["avatar_url"] == body["url"]
    assert profile_body["picture_kind"] == "card"
    assert profile_body["picture_card"] == "Pudge Butcher"


@pytest.mark.parametrize("body", [
    {"kind": "card", "card": "Not A Card"},
    {"kind": "card", "card": "No Art"},
    {"kind": "card"},
    {"kind": "something"},
])
def test_rejects_unknown_cards_and_choices(client, profile, body):
    _login(client, "100")
    assert client.put("/api/player/100/profile-picture", json=body).status_code == 400


def test_only_the_owner_or_staff_can_change_it(client, profile):
    assert client.get("/api/player/100/profile-picture").status_code == 401
    _login(client, "200")
    assert client.put("/api/player/100/profile-picture", json={"kind": "discord"}).status_code == 403
    assert _upload(client, _image()).status_code == 403


def test_moderator_can_reset_a_picture_and_it_is_logged(client, profile, folders, monkeypatch):
    _login(client, "100")
    _upload(client, _image())
    monkeypatch.setattr(players_routes, "is_moderator", lambda: True)
    logged = []
    from repositories.audit import AuditRepository
    monkeypatch.setattr(AuditRepository, "log_action", lambda self, *a, **k: logged.append((a, k)))
    _login(client, "300")
    resp = client.put("/api/player/100/profile-picture", json={"kind": "discord"})
    assert resp.status_code == 200
    assert resp.get_json()["url"] == DISCORD
    assert list(folders.iterdir()) == []
    assert logged and logged[0][0][2] == "reset_profile_picture"


def test_bad_stored_values_fall_back_to_discord():
    assert pictures.picture_url(None) is None
    assert pictures.picture_url("not json") is None
    assert pictures.picture_url('{"kind": "upload", "file": "../../etc/passwd"}') is None
    assert pictures.picture_url('{"kind": "other", "file": "a.webp"}') is None
    assert pictures.picture_url('{"kind": "upload", "file": "a.webp"}') == "/static/uploads/profile-pictures/a.webp"


def test_card_preview_shows_the_crop_without_saving(client, profile, folders):
    _login(client, "100")
    resp = client.get("/api/player/100/profile-picture/card-preview?card=Pudge%20Butcher")
    assert resp.status_code == 200
    assert resp.mimetype == "image/webp"
    assert Image.open(io.BytesIO(resp.data)).size == (400, 400)
    assert list(folders.iterdir()) == []
    assert client.get("/api/player/100/profile-picture/card-preview?card=Nope").status_code == 400
    _login(client, "200")
    assert client.get("/api/player/100/profile-picture/card-preview?card=Pudge%20Butcher").status_code == 403


def test_sites_crop_from_the_left_away_from_their_sideways_text(tmp_path, monkeypatch):
    cards = tmp_path / "cards"
    cards.mkdir()
    # Sideways site: blue art, grey text strip down the right edge
    site = Image.new("RGB", (744, 1039), "blue")
    site.paste(Image.new("RGB", (110, 1039), "grey"), (634, 0))
    site.save(cards / "site.webp", "WEBP")
    monkeypatch.setattr(pictures, "CARD_IMAGES_DIR", cards)
    img = Image.open(io.BytesIO(pictures.process_card("site.webp", is_site=True))).convert("RGB")
    for x in (5, 200, 395):
        r, g, b = img.getpixel((x, 200))
        assert b > 180 and r < 60, (x, (r, g, b))
