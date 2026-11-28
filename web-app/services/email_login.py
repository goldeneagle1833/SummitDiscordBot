"""Sign in with an emailed code (no Discord or Google needed).

The player types an email, Summit emails a 6-digit code, and typing the code
back signs them in. The email must already be theirs to read, so it counts as
verified, which is what the PSO account lookup matches on.

Who they sign in as:
  - a Discord or Google login that verified the same email: that account
    (so a player never ends up with two profiles);
  - otherwise a new email login, whose user id is its Summit player number
    (see services/summit_player_numbers.py), so the bot records their ranked
    games like anyone else's.

Codes last 10 minutes and allow 5 tries. One email can ask for 5 codes an
hour, one address (IP) for 20.
"""

import hashlib
import hmac
import logging
import secrets
import sqlite3
import time

import webapp_config

logger = logging.getLogger(__name__)

TABLE = "email_login_codes"
CODE_TTL_SECONDS = 10 * 60
MAX_ATTEMPTS = 5
MAX_CODES_PER_EMAIL_PER_HOUR = 5
MAX_CODES_PER_IP_PER_HOUR = 20
MAX_EMAIL_LENGTH = 254


class EmailLoginError(Exception):
    """A sign-in step that can't go ahead; ``status`` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def normalize_email(email) -> str:
    """Lower-case, trimmed email, or "" when it doesn't look like one."""
    text = str(email or "").strip().lower()
    local, _, domain = text.partition("@")
    if not local or "." not in domain or len(text) > MAX_EMAIL_LENGTH or " " in text:
        return ""
    return text


def _connect(db_path=None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path or webapp_config.MATCH_RECORDS_DB_PATH), timeout=10)
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS {TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                ip TEXT,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                used_at INTEGER
            )"""
    )
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_email ON {TABLE}(email, created_at)")
    return conn


def _hash(email: str, code: str) -> str:
    key = (webapp_config.SECRET_KEY or "summit").encode()
    return hmac.new(key, f"{email}:{code}".encode(), hashlib.sha256).hexdigest()


def _send(email: str, code: str):
    from services.meta_report import email_configured, send_email

    if not email_configured():
        raise EmailLoginError("Email sign-in isn't switched on yet. Please use Discord or Google.", 503)
    text = (
        f"Your Sorcerers Summit login code is {code}\n\n"
        "It works for 10 minutes. If you didn't ask for it, you can ignore this email."
    )
    html = (
        "<p>Your Sorcerers Summit login code is</p>"
        f"<p style=\"font-size:28px;font-weight:bold;letter-spacing:4px\">{code}</p>"
        "<p>It works for 10 minutes. If you didn't ask for it, you can ignore this email.</p>"
    )
    try:
        send_email(email, f"Your Sorcerers Summit login code: {code}", text, html)
    except Exception as e:
        logger.warning("Login code email failed: %s", e)
        raise EmailLoginError("We couldn't send the email. Please try again in a minute.", 502)


def start(email, ip: str | None = None, *, db_path=None) -> str:
    """Email a new login code. Returns the normalized email."""
    email = normalize_email(email)
    if not email:
        raise EmailLoginError("Please enter a valid email address.")
    now = int(time.time())
    conn = _connect(db_path)
    try:
        hour_ago = now - 3600
        per_email = conn.execute(
            f"SELECT COUNT(*) FROM {TABLE} WHERE email = ? AND created_at > ?", (email, hour_ago)
        ).fetchone()[0]
        per_ip = conn.execute(
            f"SELECT COUNT(*) FROM {TABLE} WHERE ip = ? AND created_at > ?", (ip or "", hour_ago)
        ).fetchone()[0] if ip else 0
        if per_email >= MAX_CODES_PER_EMAIL_PER_HOUR or per_ip >= MAX_CODES_PER_IP_PER_HOUR:
            raise EmailLoginError("Too many codes asked for. Please wait an hour and try again.", 429)

        code = f"{secrets.randbelow(1_000_000):06d}"
        _send(email, code)
        # Only the newest code works
        conn.execute(
            f"UPDATE {TABLE} SET used_at = ? WHERE email = ? AND used_at IS NULL", (now, email)
        )
        conn.execute(
            f"""INSERT INTO {TABLE} (email, code_hash, ip, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)""",
            (email, _hash(email, code), ip or "", now, now + CODE_TTL_SECONDS),
        )
        conn.commit()
    finally:
        conn.close()
    logger.info("Sent an email login code")
    return email


def check_code(email, code, *, db_path=None) -> str:
    """Use up a correct code. Returns the normalized email; raises EmailLoginError otherwise."""
    email = normalize_email(email)
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    if not email or len(code) != 6:
        raise EmailLoginError("Enter the 6-digit code from the email.")
    now = int(time.time())
    conn = _connect(db_path)
    try:
        row = conn.execute(
            f"""SELECT id, code_hash, expires_at, attempts FROM {TABLE}
                WHERE email = ? AND used_at IS NULL ORDER BY id DESC LIMIT 1""",
            (email,),
        ).fetchone()
        if not row or row[2] < now or row[3] >= MAX_ATTEMPTS:
            raise EmailLoginError("That code has expired. Ask for a new one.")
        code_id, code_hash, _expires, attempts = row
        if not hmac.compare_digest(code_hash, _hash(email, code)):
            conn.execute(f"UPDATE {TABLE} SET attempts = attempts + 1 WHERE id = ?", (code_id,))
            conn.commit()
            left = MAX_ATTEMPTS - attempts - 1
            if left <= 0:
                raise EmailLoginError("That code has expired. Ask for a new one.")
            raise EmailLoginError(f"That code isn't right. {left} {'try' if left == 1 else 'tries'} left.")
        conn.execute(f"UPDATE {TABLE} SET used_at = ? WHERE id = ?", (now, code_id))
        conn.commit()
    finally:
        conn.close()
    return email


def account_for_email(email: str, *, db_path=None) -> dict:
    """Who signs in with this (now proven) email: {user_id, provider, display_name, avatar}."""
    from repositories.user_profiles import UserProfileRepository
    from services.summit_player_numbers import _profiles_with_email, number_for_email

    profiles = _profiles_with_email(email, db_path)
    from utils.player_ids import is_summit_player_number

    def pick(match):
        return next((p for p in profiles if match(p)), None)

    existing = (
        pick(lambda p: p["provider"] not in ("google", "email") and str(p["user_id"]).isdigit()
             and not is_summit_player_number(p["user_id"]))
        or pick(lambda p: str(p["user_id"]).startswith("google_"))
        or pick(lambda p: p["provider"] == "email")
    )
    repo = UserProfileRepository(db_path) if db_path else UserProfileRepository()
    if existing:
        profile = repo.get_by_user_id(existing["user_id"]) or {}
        return {
            "user_id": str(existing["user_id"]),
            "provider": existing["provider"],
            "display_name": existing.get("custom_display_name") or existing.get("display_name") or "Player",
            "avatar": profile.get("avatar"),
            "new": False,
        }

    number = number_for_email(email, create=True, db_path=db_path)
    display_name = f"Player {str(number)[-4:]}"
    repo.upsert_profile(
        user_id=str(number),
        display_name=display_name,
        avatar=None,
        provider="email",
        email=email,
        email_verified=True,
    )
    logger.info("New email login %s", number)
    return {"user_id": str(number), "provider": "email", "display_name": display_name, "avatar": None,
            "new": True}
