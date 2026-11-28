"""Players' own profile pictures: an uploaded image or a crop of card art.

Every picture is re-encoded by the server into a small square WEBP, so
what gets served is always a plain image of a known size with no hidden
metadata (phone photos carry GPS in their EXIF data), whatever was sent.

A player's choice is stored on user_profiles.profile_picture as JSON:
    {"kind": "upload", "file": "<name>.webp"}
    {"kind": "card", "card": "<card name>", "file": "<name>.webp"}
No value means the Discord (or Google) picture, as before.
"""

from __future__ import annotations

import io
import json
import os
import secrets

from webapp_config import CARD_IMAGES_DIR, PROFILE_PICTURE_UPLOADS_DIR

PICTURE_SIZE = 400  # square, in pixels
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_SOURCE_PIXELS = 40_000_000  # refuse decompression bombs
URL_PREFIX = "/static/uploads/profile-pictures/"
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}

# Where the art sits on a card image, as fractions of its width/height:
# a square as wide as 80% of the card, starting below the name bar. Sites
# are printed sideways on a portrait image with their text down the right
# edge, so their square starts at the left edge and is turned upright.
CARD_ART_LEFT = 0.10
CARD_ART_TOP = 0.10
CARD_ART_WIDTH = 0.80
SITE_ART_LEFT = 0.02
SITE_ART_WIDTH = 0.76


class PictureError(ValueError):
    """A picture we can't use; the message is shown to the player."""


def parse(raw) -> dict | None:
    """The stored choice as a dict, or None for the Discord default."""
    if not raw:
        return None
    if isinstance(raw, dict):
        value = raw
    else:
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            return None
    if not isinstance(value, dict) or value.get("kind") not in ("upload", "card"):
        return None
    file = str(value.get("file") or "")
    if not file or "/" in file or "\\" in file or file.startswith("."):
        return None
    return value


def picture_url(raw) -> str | None:
    """URL of the player's own picture, or None to use Discord's."""
    value = parse(raw)
    if not value:
        return None
    return URL_PREFIX + value["file"]


def _square_webp(img) -> bytes:
    from PIL import Image

    img = img.convert("RGB")
    w, h = img.size
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    img = img.resize((PICTURE_SIZE, PICTURE_SIZE), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "WEBP", quality=85, method=6)
    return out.getvalue()


def _open(data: bytes):
    from PIL import Image, ImageOps, UnidentifiedImageError

    Image.MAX_IMAGE_PIXELS = MAX_SOURCE_PIXELS
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in ALLOWED_FORMATS:
            raise PictureError("Use a JPG, PNG, WEBP or GIF picture.")
        if img.width * img.height > MAX_SOURCE_PIXELS:
            raise PictureError("That picture is too big. Try a smaller one.")
        img.seek(0)  # animated GIF/WEBP: first frame only
        img.load()
    except PictureError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        raise PictureError("That file isn't a picture we can read. Use a JPG, PNG, WEBP or GIF.")
    # Phone photos are often stored sideways with a rotate flag
    return ImageOps.exif_transpose(img)


def process_upload(data: bytes, crop: dict | None = None) -> bytes:
    """A player's uploaded image as a square WEBP.

    crop is an optional {"x", "y", "size"} box in fractions of the image
    (x/y = top-left corner, size = side as a fraction of the shorter
    edge), from the picker's zoom and drag; else the centre square.
    """
    if not data:
        raise PictureError("Choose a picture to upload.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise PictureError(
            f"That picture is {len(data) / (1024 * 1024):.1f} MB. Pictures must be 5 MB or smaller."
        )
    img = _open(data)
    if crop:
        img = _crop_box(img, crop)
    return _square_webp(img)


def _crop_box(img, crop: dict):
    try:
        x, y, size = float(crop["x"]), float(crop["y"]), float(crop["size"])
    except (KeyError, TypeError, ValueError):
        return img
    w, h = img.size
    short = min(w, h)
    side = max(16, min(short, round(short * min(max(size, 0.05), 1.0))))
    left = round(min(max(x, 0.0), 1.0) * w)
    top = round(min(max(y, 0.0), 1.0) * h)
    left = min(max(left, 0), w - side)
    top = min(max(top, 0), h - side)
    return img.crop((left, top, left + side, top + side))


def process_card(card_file: str, is_site: bool = False) -> bytes:
    """A square crop of the art on one of the card images we already serve."""
    path = (CARD_IMAGES_DIR / card_file).resolve()
    if path.parent != CARD_IMAGES_DIR.resolve() or not path.is_file():
        raise PictureError("We don't have art for that card.")
    img = _open(path.read_bytes())
    w, h = img.size
    if is_site:
        side = round(w * SITE_ART_WIDTH)
        left = round(w * SITE_ART_LEFT)
        top = (h - side) // 2
    else:
        side = round(w * CARD_ART_WIDTH)
        left = round(w * CARD_ART_LEFT)
        top = round(h * CARD_ART_TOP)
    if w > h:  # a landscape image: just take the middle
        side = h
        left, top = (w - h) // 2, 0
    side = min(side, w - left, h - top)
    art = img.crop((left, top, left + side, top + side))
    if is_site:
        art = art.rotate(-90, expand=True)  # the sky is on the left: turn it to the top
    return _square_webp(art)


def save(player_id: str, webp: bytes) -> str:
    """Write the picture and return its file name (new name each time, so caches refresh)."""
    safe_id = "".join(c for c in str(player_id) if c.isalnum() or c == "_")[:40] or "player"
    name = f"{safe_id}-{secrets.token_hex(6)}.webp"
    (PROFILE_PICTURE_UPLOADS_DIR / name).write_bytes(webp)
    return name


def delete_file(raw) -> None:
    """Remove a picture file we saved before (best effort)."""
    value = parse(raw)
    if not value:
        return
    path = (PROFILE_PICTURE_UPLOADS_DIR / value["file"]).resolve()
    if path.parent == PROFILE_PICTURE_UPLOADS_DIR.resolve():
        try:
            os.remove(path)
        except OSError:
            pass
