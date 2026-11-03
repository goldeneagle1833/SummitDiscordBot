"""Player articles (community blog): articles, review comments and the
Discord notification queue the bot delivers.

Lives in its own articles.db (``ARTICLES_DB_PATH``).  The Discord bot reads
``article_notifications`` (see discord-bot/cogs/article_notifications.py) the
same way it reads the store's notification queue.

Statuses:
    pending            waiting for a reviewer (new or edited)
    changes_requested  a reviewer asked the author to change something
    approved           public on /articles
    rejected           not published; the reason is in the comments
"""

from __future__ import annotations

import datetime
import sqlite3
from pathlib import Path

import webapp_config

STATUSES = ("pending", "changes_requested", "approved", "rejected")

# Columns safe to show anyone (no raw body, no storage paths).
_PUBLIC_COLS = (
    "id", "slug", "title", "summary", "category", "tags", "author_id",
    "author_name", "author_provider", "author_avatar", "word_count",
    "reading_minutes", "view_count", "published_at", "updated_at",
    "pdf_size", "external_url", "external_site", "external_image",
    "header_card", "header_image",
)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _split_tags(raw: str | None) -> list[str]:
    return [t for t in (raw or "").split(",") if t]


def _join_tags(tags: list[str]) -> str:
    # Leading/trailing commas let a tag be matched exactly with LIKE '%,tag,%'
    return "," + ",".join(tags) + "," if tags else ""


class ArticleRepository:
    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or webapp_config.ARTICLES_DB_PATH)
        self._ensure_tables()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self):
        conn = self._conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    category TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '',
                    body_md TEXT NOT NULL DEFAULT '',
                    body_html TEXT NOT NULL DEFAULT '',
                    word_count INTEGER NOT NULL DEFAULT 0,
                    reading_minutes INTEGER NOT NULL DEFAULT 1,
                    author_id TEXT NOT NULL,
                    author_name TEXT NOT NULL,
                    author_provider TEXT,
                    author_avatar TEXT,
                    pdf_file TEXT,
                    pdf_original_name TEXT,
                    pdf_size INTEGER,
                    status TEXT NOT NULL DEFAULT 'pending',
                    view_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    submitted_at TEXT NOT NULL,
                    published_at TEXT,
                    reviewed_by TEXT,
                    reviewed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_articles_status
                    ON articles (status, published_at);
                CREATE INDEX IF NOT EXISTS idx_articles_author
                    ON articles (author_id);

                CREATE TABLE IF NOT EXISTS article_comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    role TEXT NOT NULL,          -- 'reviewer' | 'author'
                    kind TEXT NOT NULL DEFAULT 'comment',
                        -- comment | changes_requested | approved | rejected | submitted
                    body TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_article_comments_article
                    ON article_comments (article_id);

                CREATE TABLE IF NOT EXISTS article_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id INTEGER,
                    recipient TEXT NOT NULL,      -- Discord user ID
                    audience TEXT NOT NULL DEFAULT 'author',  -- 'reviewer' | 'author'
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    link_path TEXT,               -- site path; the bot adds the domain
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    sent_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_article_notifications_status
                    ON article_notifications (status);

                -- Reviewers the owner added on the blog page (on top of
                -- ARTICLE_REVIEWER_IDS from the environment)
                -- Public discussion under a published article. Mirrored both
                -- ways with the article's Discord forum thread by the bot
                -- (discord-bot/cogs/article_discussions.py).
                CREATE TABLE IF NOT EXISTS article_public_comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id INTEGER NOT NULL,
                    source TEXT NOT NULL,              -- 'site' | 'discord'
                    user_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    avatar TEXT,
                    body TEXT NOT NULL,
                    discord_message_id TEXT,           -- the Discord copy (or original)
                    mirror_status TEXT NOT NULL DEFAULT 'pending',  -- pending | done | failed
                    deleted INTEGER NOT NULL DEFAULT 0,
                    mirror_deleted INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    edited_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_article_public_comments_article
                    ON article_public_comments (article_id, deleted);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_article_public_comments_msg
                    ON article_public_comments (discord_message_id);

                CREATE TABLE IF NOT EXISTS article_reviewers (
                    user_id TEXT PRIMARY KEY,     -- Discord user ID
                    username TEXT NOT NULL,
                    added_by TEXT,
                    added_at TEXT NOT NULL
                );
            """)
            # Discord forum thread for the article's discussion (set by the bot)
            cols = {r[1] for r in conn.execute("PRAGMA table_info(articles)")}
            if "forum_thread_id" not in cols:
                conn.execute("ALTER TABLE articles ADD COLUMN forum_thread_id TEXT")
            if "forum_locked" not in cols:
                conn.execute("ALTER TABLE articles ADD COLUMN forum_locked INTEGER NOT NULL DEFAULT 0")
            # Link to an article hosted on another site (shown as a preview tile)
            # header_card/header_image: a Sorcery card picked as the header
            # (image is a file name served from /card-images/)
            for col in ("external_url", "external_site", "external_image",
                        "header_card", "header_image"):
                if col not in cols:
                    conn.execute(f"ALTER TABLE articles ADD COLUMN {col} TEXT")
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Row shaping

    @staticmethod
    def _public(row: sqlite3.Row) -> dict:
        d = {k: row[k] for k in _PUBLIC_COLS}
        d["tags"] = _split_tags(d["tags"])
        d["has_pdf"] = bool(row["pdf_file"])
        return d

    @staticmethod
    def _full(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["tags"] = _split_tags(d["tags"])
        d["has_pdf"] = bool(d.get("pdf_file"))
        return d

    # ------------------------------------------------------------------
    # Writes

    def create(self, *, title, summary, category, tags, body_md, body_html,
               word_count, reading_minutes, author_id, author_name,
               author_provider=None, author_avatar=None, slug="article") -> int:
        now = _now()
        conn = self._conn()
        try:
            cur = conn.execute(
                """INSERT INTO articles
                   (slug, title, summary, category, tags, body_md, body_html,
                    word_count, reading_minutes, author_id, author_name,
                    author_provider, author_avatar, status,
                    created_at, updated_at, submitted_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
                (slug, title, summary, category, _join_tags(tags), body_md,
                 body_html, word_count, reading_minutes, str(author_id),
                 author_name, author_provider, author_avatar, now, now, now),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def update_content(self, article_id: int, *, title, summary, category, tags,
                       body_md, body_html, word_count, reading_minutes,
                       slug) -> None:
        """Author edit: content changes and the article goes back to review."""
        now = _now()
        conn = self._conn()
        try:
            conn.execute(
                """UPDATE articles SET slug = ?, title = ?, summary = ?,
                       category = ?, tags = ?, body_md = ?, body_html = ?,
                       word_count = ?, reading_minutes = ?, status = 'pending',
                       updated_at = ?, submitted_at = ?
                   WHERE id = ?""",
                (slug, title, summary, category, _join_tags(tags), body_md,
                 body_html, word_count, reading_minutes, now, now, article_id),
            )
            conn.commit()
        finally:
            conn.close()

    def set_pdf(self, article_id: int, stored_name: str | None,
                original_name: str | None, size: int | None) -> None:
        conn = self._conn()
        try:
            conn.execute(
                """UPDATE articles SET pdf_file = ?, pdf_original_name = ?,
                       pdf_size = ? WHERE id = ?""",
                (stored_name, original_name, size, article_id),
            )
            conn.commit()
        finally:
            conn.close()

    def set_external(self, article_id: int, url: str | None, site: str | None = None,
                     image: str | None = None) -> None:
        """Point the article at a page on another site (None clears it)."""
        conn = self._conn()
        try:
            conn.execute(
                """UPDATE articles SET external_url = ?, external_site = ?,
                       external_image = ? WHERE id = ?""",
                (url, site if url else None, image if url else None, article_id),
            )
            conn.commit()
        finally:
            conn.close()

    def set_header_card(self, article_id: int, card: str | None,
                        image: str | None = None) -> None:
        """Use a card's art as the article's header image (None clears it)."""
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE articles SET header_card = ?, header_image = ? WHERE id = ?",
                (card, image if card else None, article_id),
            )
            conn.commit()
        finally:
            conn.close()

    def set_status(self, article_id: int, status: str, reviewer_id: str) -> None:
        if status not in STATUSES:
            raise ValueError(f"bad status {status}")
        now = _now()
        conn = self._conn()
        try:
            conn.execute(
                """UPDATE articles SET status = ?, reviewed_by = ?, reviewed_at = ?,
                       published_at = CASE WHEN ? = 'approved'
                                           THEN COALESCE(published_at, ?)
                                           ELSE published_at END
                   WHERE id = ?""",
                (status, str(reviewer_id), now, status, now, article_id),
            )
            conn.commit()
        finally:
            conn.close()

    def delete(self, article_id: int) -> bool:
        conn = self._conn()
        try:
            cur = conn.execute("DELETE FROM articles WHERE id = ?", (article_id,))
            conn.execute("DELETE FROM article_comments WHERE article_id = ?", (article_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def add_view(self, article_id: int) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE articles SET view_count = view_count + 1 WHERE id = ?",
                (article_id,),
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Reads

    def get(self, article_id: int) -> dict | None:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
            return self._full(row) if row else None
        finally:
            conn.close()

    def public_view(self, article: dict) -> dict:
        d = {k: article.get(k) for k in _PUBLIC_COLS}
        d["tags"] = article.get("tags") or []
        d["has_pdf"] = bool(article.get("pdf_file"))
        return d

    def list_by_author(self, author_id: str) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                """SELECT * FROM articles WHERE author_id = ?
                   ORDER BY updated_at DESC""",
                (str(author_id),),
            ).fetchall()
            out = []
            for r in rows:
                d = self._public(r)
                d["status"] = r["status"]
                d["submitted_at"] = r["submitted_at"]
                d["created_at"] = r["created_at"]
                out.append(d)
            return out
        finally:
            conn.close()

    def count_recent_by_author(self, author_id: str, hours: int = 24) -> int:
        since = (datetime.datetime.now(datetime.timezone.utc)
                 - datetime.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = self._conn()
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM articles WHERE author_id = ? AND created_at >= ?",
                (str(author_id), since),
            ).fetchone()[0]
        finally:
            conn.close()

    def count_waiting_by_author(self, author_id: str) -> int:
        conn = self._conn()
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM articles WHERE author_id = ? AND status = 'pending'",
                (str(author_id),),
            ).fetchone()[0]
        finally:
            conn.close()

    def search_published(self, *, q: str = "", category: str = "", tag: str = "",
                         author: str = "", days: int = 0, sort: str = "newest",
                         page: int = 1, per_page: int = 12) -> dict:
        where = ["status = 'approved'"]
        params: list = []
        for word in (q or "").split()[:8]:
            like = f"%{word.lower()}%"
            where.append(
                "(LOWER(title) LIKE ? OR LOWER(summary) LIKE ? OR LOWER(body_md) LIKE ?"
                " OR LOWER(author_name) LIKE ? OR tags LIKE ?"
                " OR LOWER(COALESCE(external_site, '')) LIKE ?)"
            )
            params += [like] * 6
        if category:
            where.append("category = ?")
            params.append(category)
        if tag:
            where.append("tags LIKE ?")
            params.append(f"%,{tag},%")
        if author:
            where.append("author_id = ?")
            params.append(str(author))
        if days and days > 0:
            since = (datetime.datetime.now(datetime.timezone.utc)
                     - datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
            where.append("published_at >= ?")
            params.append(since)
        order = {
            "oldest": "published_at ASC, id ASC",
            "popular": "view_count DESC, published_at DESC",
        }.get(sort, "published_at DESC, id DESC")
        clause = " AND ".join(where)
        page = max(1, page)
        conn = self._conn()
        try:
            total = conn.execute(f"SELECT COUNT(*) FROM articles WHERE {clause}", params).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM articles WHERE {clause} ORDER BY {order} LIMIT ? OFFSET ?",
                params + [per_page, (page - 1) * per_page],
            ).fetchall()
            return {
                "articles": [self._public(r) for r in rows],
                "total": total,
                "page": page,
                "per_page": per_page,
            }
        finally:
            conn.close()

    def facets(self) -> dict:
        """Categories, tags and authors of published articles, with counts."""
        conn = self._conn()
        try:
            cats = conn.execute(
                """SELECT category, COUNT(*) AS n FROM articles
                   WHERE status = 'approved' GROUP BY category"""
            ).fetchall()
            authors = conn.execute(
                """SELECT author_id, MAX(author_name) AS author_name, COUNT(*) AS n
                   FROM articles WHERE status = 'approved'
                   GROUP BY author_id ORDER BY n DESC, author_name"""
            ).fetchall()
            tag_counts: dict[str, int] = {}
            for (raw,) in conn.execute("SELECT tags FROM articles WHERE status = 'approved'"):
                for t in _split_tags(raw):
                    tag_counts[t] = tag_counts.get(t, 0) + 1
            tags = sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:30]
            return {
                "categories": {r["category"]: r["n"] for r in cats},
                "authors": [dict(r) for r in authors],
                "tags": [{"tag": t, "n": n} for t, n in tags],
            }
        finally:
            conn.close()

    def list_for_review(self, status: str = "") -> list[dict]:
        conn = self._conn()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM articles WHERE status = ? ORDER BY submitted_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM articles ORDER BY submitted_at DESC"
                ).fetchall()
            out = []
            for r in rows:
                d = self._public(r)
                d.update(status=r["status"], submitted_at=r["submitted_at"],
                         created_at=r["created_at"], reviewed_by=r["reviewed_by"])
                out.append(d)
            return out
        finally:
            conn.close()

    def status_counts(self) -> dict:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT status, COUNT(*) FROM articles GROUP BY status").fetchall()
            counts = {s: 0 for s in STATUSES}
            counts.update({r[0]: r[1] for r in rows})
            return counts
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Comments

    def add_comment(self, article_id: int, user_id: str, username: str,
                    role: str, body: str, kind: str = "comment") -> int:
        conn = self._conn()
        try:
            cur = conn.execute(
                """INSERT INTO article_comments
                   (article_id, user_id, username, role, kind, body, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (article_id, str(user_id), username, role, kind, body, _now()),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def comments(self, article_id: int) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                """SELECT id, article_id, username, role, kind, body, created_at
                   FROM article_comments WHERE article_id = ? ORDER BY id""",
                (article_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Notification queue (delivered by the Discord bot)

    def enqueue_notification(self, *, recipient: str, subject: str, body: str,
                             link_path: str | None = None,
                             article_id: int | None = None,
                             audience: str = "author") -> int:
        conn = self._conn()
        try:
            cur = conn.execute(
                """INSERT INTO article_notifications
                   (article_id, recipient, audience, subject, body, link_path, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (article_id, str(recipient), audience, subject[:250], body[:3500],
                 link_path, _now()),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def notifications(self, status: str | None = None) -> list[dict]:
        conn = self._conn()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM article_notifications WHERE status = ? ORDER BY id",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM article_notifications ORDER BY id").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def recent_notification_exists(self, article_id: int, minutes: int) -> bool:
        """True when a reviewer ping for this article went out recently
        (stops a burst of edits or replies from spamming reviewers)."""
        since = (datetime.datetime.now(datetime.timezone.utc)
                 - datetime.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = self._conn()
        try:
            row = conn.execute(
                """SELECT 1 FROM article_notifications
                   WHERE article_id = ? AND created_at >= ?
                     AND audience = 'reviewer' LIMIT 1""",
                (article_id, since),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Reviewers added on the site

    def list_reviewers(self) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT user_id, username, added_by, added_at FROM article_reviewers ORDER BY added_at"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def add_reviewer(self, user_id: str, username: str, added_by: str | None) -> None:
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO article_reviewers (user_id, username, added_by, added_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET username = excluded.username""",
                (str(user_id), username, added_by, _now()),
            )
            conn.commit()
        finally:
            conn.close()

    def remove_reviewer(self, user_id: str) -> bool:
        conn = self._conn()
        try:
            cur = conn.execute("DELETE FROM article_reviewers WHERE user_id = ?", (str(user_id),))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Public discussion

    def discussion(self, article_id: int) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                """SELECT id, source, user_id, username, avatar, body, created_at, edited_at
                   FROM article_public_comments
                   WHERE article_id = ? AND deleted = 0 ORDER BY created_at, id""",
                (article_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def add_public_comment(self, article_id: int, *, source: str, user_id: str,
                           username: str, avatar: str | None, body: str,
                           discord_message_id: str | None = None) -> int:
        conn = self._conn()
        try:
            cur = conn.execute(
                """INSERT INTO article_public_comments
                   (article_id, source, user_id, username, avatar, body,
                    discord_message_id, mirror_status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (article_id, source, str(user_id), username, avatar, body,
                 discord_message_id, "done" if source == "discord" else "pending", _now()),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def get_public_comment(self, comment_id: int) -> dict | None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM article_public_comments WHERE id = ?", (comment_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def delete_public_comment(self, comment_id: int) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE article_public_comments SET deleted = 1 WHERE id = ?", (comment_id,)
            )
            conn.commit()
        finally:
            conn.close()

    def count_recent_public_comments(self, user_id: str, minutes: int = 60) -> int:
        since = (datetime.datetime.now(datetime.timezone.utc)
                 - datetime.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = self._conn()
        try:
            return conn.execute(
                """SELECT COUNT(*) FROM article_public_comments
                   WHERE user_id = ? AND source = 'site' AND created_at >= ?""",
                (str(user_id), since),
            ).fetchone()[0]
        finally:
            conn.close()
