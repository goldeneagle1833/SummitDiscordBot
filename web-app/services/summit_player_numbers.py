"""Summit player numbers for Google logins, and resolving reported player ids.

Ranked games are recorded by the Discord bot, whose tables key players by a
64-bit INTEGER. A Google login's id (``google_<21-digit Google id>``) fits
none of them, so the first time a game is reported for a Google login it is
given a Summit player number: a random 16-digit number no Discord account
can have (see utils/player_ids.py and random_player_number). From then on the bot records the player under
that number exactly like a Discord player, and the website maps it back to
the Google account for names, pictures and "is this me" checks.

Play Sorcery Online finds the id to report with by email
(``lookup_account_by_email``), and match reports may name a player by
Discord id, Summit player number, ``google_<id>`` or verified email
(``resolve_reported_player``).
"""

import logging
import secrets
import sqlite3
import time

import webapp_config
from utils.player_ids import is_summit_player_number

logger = logging.getLogger(__name__)

TABLE = "summit_player_numbers"
GOOGLE_PREFIX = "google_"

# Per-process cache: google_<id> -> number and number -> google_<id>.
# Numbers never change once handed out, so only found pairs are cached.
_by_google: dict[str, int] = {}
_by_number: dict[int, str] = {}


def _connect(db_path=None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path or webapp_config.MATCH_RECORDS_DB_PATH), timeout=10)
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS {TABLE} (
                number INTEGER PRIMARY KEY,
                google_user_id TEXT NOT NULL UNIQUE,
                created_at INTEGER NOT NULL
            )"""
    )
    return conn


def _remember(google_user_id: str, number: int) -> int:
    _by_google[google_user_id] = number
    _by_number[number] = google_user_id
    return number


def clear_cache():
    """Forget cached pairs (tests)."""
    _by_google.clear()
    _by_number.clear()


# Rows the website keyed by a Google login's bare id (google_ stripped) that
# must follow the player to their new number so nothing they set is lost.
_BARE_ID_COLUMNS = (
    ("blocked_users", ("user_id", "blocked_user_id")),
)


def _move_bare_rows(conn: sqlite3.Connection, bare_id: str, number: int):
    """Re-key a newly numbered Google login's bare-id rows to its number."""
    for table, columns in _BARE_ID_COLUMNS:
        for column in columns:
            try:
                conn.execute(
                    f"UPDATE OR IGNORE {table} SET {column} = ? WHERE {column} = ?",
                    (str(number), bare_id),
                )
            except sqlite3.OperationalError:
                continue  # table not created yet
    conn.commit()


# New numbers are "1000" then 12 random digits from the operating system's
# secure random source, so nobody can list players by counting up from one
# number (a trillion possibilities per prefix; a guess almost never lands on
# a real player). The prefix keeps every number 16 digits, inside the
# Summit range and clear of Discord ids. The first few numbers, given out
# before this, were 1000000000000001, 0002, ... and keep working as they are.
NUMBER_PREFIX = 1000
RANDOM_DIGITS = 12


def random_player_number() -> int:
    """A fresh unguessable Summit player number (not yet checked for use)."""
    return NUMBER_PREFIX * 10**RANDOM_DIGITS + secrets.randbelow(10**RANDOM_DIGITS)


_pick_number = random_player_number  # tests swap in a predictable sequence


def _number_for_login(login_id: str, *, create: bool, db_path=None) -> int | None:
    """The Summit player number of a website-only login (made on first use when create).

    ``login_id`` is ``google_<id>`` for a Google login or ``email:<address>``
    for an email-code login (the table's google_user_id column holds either).
    """
    if login_id in _by_google:
        return _by_google[login_id]
    conn = _connect(db_path)
    try:
        row = conn.execute(
            f"SELECT number FROM {TABLE} WHERE google_user_id = ?", (login_id,)
        ).fetchone()
        # A random number that's already taken is ignored and another is
        # drawn. Two first games for the same login at once: the UNIQUE login
        # column ignores the second insert and both read the same number back.
        for _attempt in range(10):
            if row is not None or not create:
                break
            conn.execute(
                f"""INSERT OR IGNORE INTO {TABLE} (number, google_user_id, created_at)
                    VALUES (?, ?, ?)""",
                (_pick_number(), login_id, int(time.time())),
            )
            conn.commit()
            row = conn.execute(
                f"SELECT number FROM {TABLE} WHERE google_user_id = ?", (login_id,)
            ).fetchone()
            if row:
                logger.info("Gave %s Summit player number %s", login_id, row[0])
                if login_id.startswith(GOOGLE_PREFIX):
                    _move_bare_rows(conn, login_id[len(GOOGLE_PREFIX):], int(row[0]))
    finally:
        conn.close()
    return _remember(login_id, int(row[0])) if row else None


def number_for_google(google_user_id: str, *, create: bool = False, db_path=None) -> int | None:
    """The Summit player number of a ``google_<id>`` login (made on first use when create)."""
    google_user_id = str(google_user_id or "").strip()
    if not google_user_id.startswith(GOOGLE_PREFIX) or len(google_user_id) <= len(GOOGLE_PREFIX):
        return None
    return _number_for_login(google_user_id, create=create, db_path=db_path)


EMAIL_LOGIN_PREFIX = "email:"


def number_for_email(email: str, *, create: bool = False, db_path=None) -> int | None:
    """The Summit player number of an email-code login (it is also its user id)."""
    email = str(email or "").strip().lower()
    if "@" not in email:
        return None
    return _number_for_login(EMAIL_LOGIN_PREFIX + email, create=create, db_path=db_path)


def google_for_number(number, *, db_path=None) -> str | None:
    """The ``google_<id>`` login a Summit player number belongs to."""
    if not is_summit_player_number(number):
        return None
    number = int(str(number).strip())
    if number in _by_number:
        found = _by_number[number]
        return found if found.startswith(GOOGLE_PREFIX) else None
    conn = _connect(db_path)
    try:
        row = conn.execute(
            f"SELECT google_user_id FROM {TABLE} WHERE number = ?", (number,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    _remember(row[0], number)
    # Email-code logins use the number itself as their user id
    return row[0] if row[0].startswith(GOOGLE_PREFIX) else None


def number_exists(number, *, db_path=None) -> bool:
    """True for a Summit player number that was handed out (Google or email login)."""
    if not is_summit_player_number(number):
        return False
    number = int(str(number).strip())
    if number in _by_number:
        return True
    conn = _connect(db_path)
    try:
        row = conn.execute(f"SELECT google_user_id FROM {TABLE} WHERE number = ?", (number,)).fetchone()
    finally:
        conn.close()
    if row:
        _remember(row[0], number)
    return row is not None


def bot_player_id(user_id) -> str:
    """The id a player has in the bot's tables (match history, ratings).

    ``google_<id>`` becomes the login's Summit player number when it has
    one; logins that never had a game reported keep the bare Google id, as
    before. Everything else comes back unchanged.
    """
    text = str(user_id if user_id is not None else "").strip()
    if text.startswith(GOOGLE_PREFIX):
        number = number_for_google(text)
        return str(number) if number is not None else text[len(GOOGLE_PREFIX):]
    return text


def account_ids(user_id) -> set[str]:
    """Every form one player's id can take: Discord id, google_<id>, bare Google id, number."""
    text = str(user_id if user_id is not None else "").strip()
    if not text:
        return set()
    forms = {text}
    google = None
    if text.startswith(GOOGLE_PREFIX):
        google = text
    elif is_summit_player_number(text):
        google = google_for_number(text)
    elif text.isdigit() and len(text) > 20:
        google = GOOGLE_PREFIX + text  # a bare Google id
    if google:
        forms.add(google)
        forms.add(google[len(GOOGLE_PREFIX):])
        number = number_for_google(google)
        if number is not None:
            forms.add(str(number))
    return forms


def same_player(a, b) -> bool:
    """True when two ids name the same player (in any of their forms)."""
    if a is None or b is None or str(a).strip() == "" or str(b).strip() == "":
        return False
    return bool(account_ids(a) & account_ids(b))


def _profiles_with_email(email: str, db_path=None) -> list[dict]:
    conn = sqlite3.connect(str(db_path or webapp_config.MATCH_RECORDS_DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT user_id, provider, display_name, custom_display_name
               FROM user_profiles
               WHERE LOWER(TRIM(email)) = ? AND email_verified = 1""",
            (email,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []  # no profiles table yet
    finally:
        conn.close()
    return [dict(r) for r in rows]


def lookup_account_by_email(email: str, *, create: bool = True, db_path=None) -> dict | None:
    """The Summit account that signed in with this verified email, or None.

    A Discord login wins when both kinds share the email (it is the account
    that already plays ranked). A Google login gets its Summit player number
    here, so the id handed back is the one to report matches with.
    """
    email = str(email or "").strip().lower()
    if "@" not in email:
        return None
    profiles = _profiles_with_email(email, db_path)
    discord = [
        p for p in profiles
        if p["provider"] not in ("google", "email") and str(p["user_id"]).isdigit()
        and not is_summit_player_number(p["user_id"])
    ]
    google = [p for p in profiles if str(p["user_id"]).startswith(GOOGLE_PREFIX)]
    email_logins = [p for p in profiles if p["provider"] == "email" and is_summit_player_number(p["user_id"])]
    if discord:
        profile, login = discord[0], "discord"
        summit_user_id = str(profile["user_id"])
    elif google:
        profile, login = google[0], "google"
        number = number_for_google(profile["user_id"], create=create, db_path=db_path)
        if number is None:
            return None
        summit_user_id = str(number)
    elif email_logins:
        profile, login = email_logins[0], "email"
        summit_user_id = str(profile["user_id"])
    else:
        return None
    return {
        "summit_user_id": summit_user_id,
        "login": login,
        "display_name": profile.get("custom_display_name") or profile.get("display_name") or "",
    }


def _has_profile(user_id: str, db_path=None) -> bool:
    conn = sqlite3.connect(str(db_path or webapp_config.MATCH_RECORDS_DB_PATH), timeout=10)
    try:
        row = conn.execute(
            "SELECT 1 FROM user_profiles WHERE user_id = ? LIMIT 1", (user_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()
    return row is not None


class UnknownPlayer(ValueError):
    """A reported player id that names no Summit account."""


def resolve_reported_player(value, *, db_path=None) -> str:
    """The bot-table id for a player named in a match report.

    Accepts a Discord id or anything else unchanged (as before), and also:
      - a Summit player number (must have been handed out),
      - ``google_<id>`` of a Google login (given a number on first use),
      - a verified email of a Summit login.
    Raises UnknownPlayer when the value is one of those forms but matches
    nobody, so a typo never files a game under a made-up player.
    """
    text = str(value if value is not None else "").strip()
    if "@" in text:
        account = lookup_account_by_email(text, db_path=db_path)
        if not account:
            raise UnknownPlayer(f"No Summit account has signed in with the email {text}")
        return account["summit_user_id"]
    if text.startswith(GOOGLE_PREFIX):
        if not _has_profile(text, db_path):
            raise UnknownPlayer(f"No Summit account has the Google login {text}")
        return str(number_for_google(text, create=True, db_path=db_path))
    if is_summit_player_number(text):
        if not number_exists(text, db_path=db_path):
            raise UnknownPlayer(f"{text} is not a Summit player number")
        return text
    return text


def all_numbers(*, db_path=None) -> dict[str, int]:
    """Every Google login that has a Summit player number: {google_<id>: number}."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(f"SELECT google_user_id, number FROM {TABLE}").fetchall()
    finally:
        conn.close()
    for google_user_id, number in rows:
        _remember(google_user_id, int(number))
    return {
        google_user_id: int(number) for google_user_id, number in rows
        if google_user_id.startswith(GOOGLE_PREFIX)
    }


def account_id(user_id) -> str:
    """The login id behind a bot-table id: a Summit player number becomes google_<id>."""
    text = str(user_id if user_id is not None else "").strip()
    return google_for_number(text) or text
