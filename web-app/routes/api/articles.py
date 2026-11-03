"""Player articles: submit, review, and read the community blog.

Anyone logged in (Discord or Google) can submit an article.  It is held for
review; reviewers (``ARTICLE_REVIEWER_IDS``, or the admins when that is empty)
get a Discord DM from the bot, can comment, request changes, approve or
reject.  Comments and decisions are DM'd to the author when they logged in
with Discord; Google users see them on their My Articles page.

Only approved articles are public.  PDFs are stored outside the web root and
served only through ``/api/articles/<id>/pdf``.
"""

from __future__ import annotations

import logging
import uuid
from functools import wraps

from flask import Blueprint, jsonify, request, send_file, session
from werkzeug.utils import secure_filename

import webapp_config
from repositories.articles import ArticleRepository
from services import article_content as content
from utils.auth import is_admin, require_admin

logger = logging.getLogger(__name__)

articles_bp = Blueprint("articles", __name__)

# Abuse limits
SUBMISSIONS_PER_DAY = 3
WAITING_PER_AUTHOR = 3
REVIEWER_PING_COOLDOWN_MIN = 15
COMMENTS_PER_ARTICLE = 200
MAX_REQUEST_BYTES = content.PDF_MAX_BYTES + 512 * 1024


# ---------------------------------------------------------------------------
# Who is who

def _user_id() -> str | None:
    uid = session.get("user_id")
    return str(uid) if uid else None


def _added_reviewer_ids() -> list[str]:
    try:
        return [r["user_id"] for r in ArticleRepository().list_reviewers()]
    except Exception:
        logger.exception("Could not read article reviewers")
        return []


def reviewer_ids() -> list[str]:
    """Discord IDs that review articles (and get the 'new article' DM):
    ARTICLE_REVIEWER_IDS plus the reviewers added on the blog page; the
    admins with Discord IDs when neither has anyone."""
    ids: list[str] = []
    for i in list(webapp_config.ARTICLE_REVIEWER_IDS) + _added_reviewer_ids():
        if str(i).isdigit() and str(i) not in ids:
            ids.append(str(i))
    if ids:
        return ids
    return [a for a in webapp_config.ADMINS if str(a).isdigit()]


def is_article_reviewer() -> bool:
    if is_admin():
        return True
    uid = _user_id()
    return bool(uid) and (uid in webapp_config.ARTICLE_REVIEWER_IDS or uid in _added_reviewer_ids())


def require_login(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not _user_id():
            return jsonify({"error": "Log in with Discord or Google first."}), 401
        return f(*args, **kwargs)
    wrapper._auth_required = True
    return wrapper


def require_article_reviewer(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not is_article_reviewer():
            return jsonify({"error": "Article reviewer access required"}), 403
        return f(*args, **kwargs)
    wrapper._auth_required = True
    return wrapper


def _repo() -> ArticleRepository:
    return ArticleRepository()


def _avatar_url() -> str | None:
    avatar = session.get("avatar")
    if not avatar:
        return None
    if session.get("auth_provider") == "discord":
        if str(avatar).isalnum() or str(avatar).startswith("a_"):
            return f"https://cdn.discordapp.com/avatars/{_user_id()}/{avatar}.png?size=128"
        return None
    return avatar if str(avatar).startswith("https://") else None


def _article_path(article: dict) -> str:
    return f"/articles/{article['id']}-{article['slug']}"


def _can_dm_author(article: dict) -> bool:
    # Google IDs are numeric too, so go by how they logged in.
    return article.get("author_provider") == "discord" and str(article["author_id"]).isdigit()


# ---------------------------------------------------------------------------
# Notifications (queued here, delivered by the Discord bot)

def _notify_reviewers(repo, article: dict, subject: str, body: str,
                      *, exclude: str | None = None, throttle: bool = False):
    if throttle and repo.recent_notification_exists(article["id"], REVIEWER_PING_COOLDOWN_MIN):
        return
    for rid in reviewer_ids():
        if rid == exclude:
            continue
        repo.enqueue_notification(
            recipient=rid, subject=subject, body=body, audience="reviewer",
            link_path=f"/admin/articles?id={article['id']}", article_id=article["id"],
        )


def _notify_author(repo, article: dict, subject: str, body: str, link_path: str):
    if not _can_dm_author(article):
        return
    repo.enqueue_notification(
        recipient=article["author_id"], subject=subject, body=body,
        link_path=link_path, article_id=article["id"], audience="author",
    )


def _quote(text: str) -> str:
    return "\n".join("> " + line for line in (text or "").splitlines() if line.strip())


# ---------------------------------------------------------------------------
# Form handling shared by create and edit

def _read_form():
    """Validate the submitted fields.  Returns (fields, pdf_bytes, error)."""
    if request.content_length and request.content_length > MAX_REQUEST_BYTES:
        return None, None, ("That upload is too big (PDFs up to 10 MB).", 413)

    form = request.form if request.form else (request.get_json(silent=True) or {})
    title = content.clean_text(form.get("title"))
    summary = content.clean_text(form.get("summary"))
    category = content.clean_text(form.get("category"))
    body = content.clean_text(form.get("body"), multiline=True)
    tags = content.clean_tags(form.get("tags") or "")
    remove_pdf = str(form.get("remove_pdf") or "") in ("1", "true")

    pdf_bytes = None
    pdf_name = None
    upload = request.files.get("pdf") if request.files else None
    if upload and upload.filename:
        if not upload.filename.lower().endswith(".pdf"):
            return None, None, ("Only PDF files can be attached.", 400)
        pdf_bytes = upload.read(content.PDF_MAX_BYTES + 1)
        error = content.check_pdf(pdf_bytes)
        if error:
            return None, None, (error, 400)
        pdf_name = secure_filename(upload.filename)[:100] or "article.pdf"

    fields = dict(title=title, summary=summary, category=category, body=body,
                  tags=tags, remove_pdf=remove_pdf, pdf_name=pdf_name)
    return fields, pdf_bytes, None


def _store_pdf(data: bytes) -> str:
    folder = webapp_config.ARTICLE_UPLOADS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.pdf"
    (folder / name).write_bytes(data)
    return name


def _delete_pdf(stored_name: str | None):
    if not stored_name:
        return
    try:
        path = (webapp_config.ARTICLE_UPLOADS_DIR / stored_name).resolve()
        if path.parent == webapp_config.ARTICLE_UPLOADS_DIR.resolve():
            path.unlink(missing_ok=True)
    except OSError:
        logger.exception("Could not delete article PDF %s", stored_name)


def _rendered(fields: dict) -> dict:
    body = fields["body"]
    return dict(
        title=fields["title"], summary=fields["summary"], category=fields["category"],
        tags=fields["tags"], body_md=body, body_html=content.render_markdown(body),
        word_count=content.word_count(body),
        reading_minutes=content.reading_minutes(body),
        slug=content.slugify(fields["title"]),
    )


# ---------------------------------------------------------------------------
# Public reading

@articles_bp.route("", methods=["GET"])
def list_articles():
    args = request.args
    try:
        page = int(args.get("page", 1))
        days = int(args.get("days", 0) or 0)
    except ValueError:
        return jsonify({"error": "Bad page or days"}), 400
    category = args.get("category", "")
    if category and category not in content.CATEGORIES:
        category = ""
    tag = (content.clean_tags(args.get("tag", "")) or [""])[0]
    result = _repo().search_published(
        q=content.clean_text(args.get("q", ""))[:100],
        category=category, tag=tag,
        author=content.clean_text(args.get("author", ""))[:40],
        days=days, sort=args.get("sort", "newest"),
        page=page, per_page=12,
    )
    return jsonify(result)


@articles_bp.route("/facets", methods=["GET"])
def article_facets():
    data = _repo().facets()
    data["all_categories"] = content.CATEGORIES
    return jsonify(data)


@articles_bp.route("/<int:article_id>", methods=["GET"])
def get_article(article_id):
    repo = _repo()
    article = repo.get(article_id)
    uid = _user_id()
    is_author = bool(article) and uid == article["author_id"]
    reviewer = is_article_reviewer()
    if not article or (article["status"] != "approved" and not (is_author or reviewer)):
        return jsonify({"error": "Article not found"}), 404

    out = repo.public_view(article)
    out["body_html"] = article["body_html"]
    out["category"] = article["category"]
    if is_author or reviewer:
        out.update(
            status=article["status"], body_md=article["body_md"],
            submitted_at=article["submitted_at"], created_at=article["created_at"],
            pdf_original_name=article["pdf_original_name"],
            comments=repo.comments(article_id),
            can_edit=is_author, is_reviewer=reviewer, is_author=is_author,
        )

    if article["status"] == "approved" and not is_author:
        viewed = session.get("viewed_articles") or []
        if article_id not in viewed:
            repo.add_view(article_id)
            session["viewed_articles"] = (viewed + [article_id])[-50:]
    return jsonify(out)


@articles_bp.route("/<int:article_id>/pdf", methods=["GET"])
def get_article_pdf(article_id):
    article = _repo().get(article_id)
    allowed = article and (
        article["status"] == "approved"
        or _user_id() == article["author_id"]
        or is_article_reviewer()
    )
    if not allowed or not article.get("pdf_file"):
        return jsonify({"error": "PDF not found"}), 404
    path = (webapp_config.ARTICLE_UPLOADS_DIR / article["pdf_file"]).resolve()
    if path.parent != webapp_config.ARTICLE_UPLOADS_DIR.resolve() or not path.exists():
        return jsonify({"error": "PDF not found"}), 404
    resp = send_file(
        path, mimetype="application/pdf", as_attachment=False,
        download_name=f"{article['slug']}.pdf", max_age=0,
    )
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = "private, no-store" if article["status"] != "approved" else "public, max-age=3600"
    return resp


# ---------------------------------------------------------------------------
# Authors

@articles_bp.route("/preview", methods=["POST"])
@require_login
def preview_article():
    data = request.get_json(silent=True) or {}
    body = content.clean_text(data.get("body"), multiline=True)[: content.BODY_MAX]
    return jsonify({
        "html": content.render_markdown(body),
        "word_count": content.word_count(body),
        "reading_minutes": content.reading_minutes(body),
    })


@articles_bp.route("/mine", methods=["GET"])
@require_login
def my_articles():
    return jsonify({"articles": _repo().list_by_author(_user_id())})


@articles_bp.route("", methods=["POST"])
@require_login
def submit_article():
    repo = _repo()
    uid = _user_id()
    if repo.count_recent_by_author(uid) >= SUBMISSIONS_PER_DAY:
        return jsonify({"error": f"You can submit {SUBMISSIONS_PER_DAY} articles a day. Try again tomorrow."}), 429
    if repo.count_waiting_by_author(uid) >= WAITING_PER_AUTHOR:
        return jsonify({"error": "You already have articles waiting for review. Please wait for those first."}), 429

    fields, pdf_bytes, error = _read_form()
    if error:
        return jsonify({"error": error[0]}), error[1]
    error = content.validate_article(fields["title"], fields["summary"], fields["body"],
                                     fields["category"], has_pdf=pdf_bytes is not None)
    if error:
        return jsonify({"error": error}), 400

    r = _rendered(fields)
    article_id = repo.create(
        **r, author_id=uid, author_name=session.get("username") or "Player",
        author_provider=session.get("auth_provider"), author_avatar=_avatar_url(),
    )
    if pdf_bytes is not None:
        repo.set_pdf(article_id, _store_pdf(pdf_bytes), fields["pdf_name"], len(pdf_bytes))

    article = repo.get(article_id)
    repo.add_comment(article_id, uid, article["author_name"], "author", "", kind="submitted")
    pdf_note = " A PDF is attached." if pdf_bytes is not None else ""
    _notify_reviewers(
        repo, article, "New player article to review",
        f"**{article['title']}** by {article['author_name']}\n"
        f"Category: {article['category']}\n\n{article['summary']}\n\n"
        f"Automatic safety checks passed.{pdf_note}",
    )
    logger.info("Article %s submitted by %s", article_id, uid)
    return jsonify({"success": True, "id": article_id, "status": "pending"}), 201


@articles_bp.route("/<int:article_id>/edit", methods=["POST"])
@require_login
def edit_article(article_id):
    repo = _repo()
    article = repo.get(article_id)
    if not article or article["author_id"] != _user_id():
        return jsonify({"error": "Article not found"}), 404

    fields, pdf_bytes, error = _read_form()
    if error:
        return jsonify({"error": error[0]}), error[1]
    keeps_pdf = article["has_pdf"] and not fields["remove_pdf"]
    error = content.validate_article(fields["title"], fields["summary"], fields["body"],
                                     fields["category"], has_pdf=pdf_bytes is not None or keeps_pdf)
    if error:
        return jsonify({"error": error}), 400

    was_live = article["status"] == "approved"
    repo.update_content(article_id, **_rendered(fields))
    if pdf_bytes is not None or fields["remove_pdf"]:
        _delete_pdf(article.get("pdf_file"))
        if pdf_bytes is not None:
            repo.set_pdf(article_id, _store_pdf(pdf_bytes), fields["pdf_name"], len(pdf_bytes))
        else:
            repo.set_pdf(article_id, None, None, None)

    article = repo.get(article_id)
    repo.add_comment(article_id, article["author_id"], article["author_name"], "author", "", kind="submitted")
    _notify_reviewers(
        repo, article, "Player article updated",
        f"**{article['title']}** by {article['author_name']} was edited"
        f"{' (it was live, now hidden until re-approved)' if was_live else ''} "
        "and is waiting for review again.",
        throttle=True,
    )
    return jsonify({"success": True, "id": article_id, "status": "pending"})


@articles_bp.route("/<int:article_id>", methods=["DELETE"])
@require_login
def delete_article(article_id):
    repo = _repo()
    article = repo.get(article_id)
    if not article or not (article["author_id"] == _user_id() or is_article_reviewer()):
        return jsonify({"error": "Article not found"}), 404
    _delete_pdf(article.get("pdf_file"))
    repo.delete(article_id)
    logger.info("Article %s deleted by %s", article_id, _user_id())
    return jsonify({"success": True})


@articles_bp.route("/<int:article_id>/comments", methods=["POST"])
@require_login
def add_comment(article_id):
    repo = _repo()
    article = repo.get(article_id)
    uid = _user_id()
    is_author = bool(article) and article["author_id"] == uid
    reviewer = is_article_reviewer()
    if not article or not (is_author or reviewer):
        return jsonify({"error": "Article not found"}), 404
    data = request.get_json(silent=True) or {}
    body = content.clean_text(data.get("body"), multiline=True)
    if not body:
        return jsonify({"error": "Write a comment first."}), 400
    if len(body) > content.COMMENT_MAX:
        return jsonify({"error": f"Keep comments to {content.COMMENT_MAX} characters."}), 400
    if len(repo.comments(article_id)) >= COMMENTS_PER_ARTICLE:
        return jsonify({"error": "This article has too many comments."}), 429

    name = session.get("username") or "Player"
    role = "reviewer" if reviewer and not is_author else "author"
    repo.add_comment(article_id, uid, name, role, body)
    if role == "reviewer":
        _notify_author(
            repo, article, "New comment on your article",
            f"**{article['title']}**\n\n{name} wrote:\n{_quote(body)}",
            f"/articles/mine?id={article_id}",
        )
    else:
        _notify_reviewers(
            repo, article, "Author replied on a player article",
            f"{name} replied on **{article['title']}**:\n{_quote(body)}",
            exclude=uid, throttle=True,
        )
    return jsonify({"success": True, "comments": repo.comments(article_id)}), 201


# ---------------------------------------------------------------------------
# Reviewers

@articles_bp.route("/review", methods=["GET"])
@require_article_reviewer
def review_queue():
    repo = _repo()
    status = request.args.get("status", "pending")
    if status not in ("pending", "changes_requested", "approved", "rejected", "all"):
        status = "pending"
    return jsonify({
        "articles": repo.list_for_review("" if status == "all" else status),
        "counts": repo.status_counts(),
        "reviewers_configured": reviewer_ids_configured() or bool(reviewer_ids()),
    })


@articles_bp.route("/<int:article_id>/review", methods=["POST"])
@require_article_reviewer
def review_article(article_id):
    repo = _repo()
    article = repo.get(article_id)
    if not article:
        return jsonify({"error": "Article not found"}), 404
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    note = content.clean_text(data.get("comment"), multiline=True)[: content.COMMENT_MAX]
    uid = _user_id() or "api"
    name = session.get("username") or "Summit reviewer"

    if action == "approve":
        repo.set_status(article_id, "approved", uid)
        repo.add_comment(article_id, uid, name, "reviewer", note, kind="approved")
        article = repo.get(article_id)
        _notify_author(
            repo, article, "Your article is live!",
            f"**{article['title']}** is now on the Sorcerers Summit blog. Thanks for writing it!"
            + (f"\n\n{name} wrote:\n{_quote(note)}" if note else ""),
            _article_path(article),
        )
    elif action == "request_changes":
        if not note:
            return jsonify({"error": "Say what should change."}), 400
        repo.set_status(article_id, "changes_requested", uid)
        repo.add_comment(article_id, uid, name, "reviewer", note, kind="changes_requested")
        _notify_author(
            repo, article, "Changes requested on your article",
            f"**{article['title']}**\n\n{name} wrote:\n{_quote(note)}\n\n"
            "Edit it from My Articles and it goes back for review.",
            f"/articles/mine?id={article_id}",
        )
    elif action == "reject":
        if not note:
            return jsonify({"error": "Give the author a reason."}), 400
        repo.set_status(article_id, "rejected", uid)
        repo.add_comment(article_id, uid, name, "reviewer", note, kind="rejected")
        _notify_author(
            repo, article, "Your article wasn't approved",
            f"**{article['title']}**\n\n{name} wrote:\n{_quote(note)}",
            f"/articles/mine?id={article_id}",
        )
    else:
        return jsonify({"error": "Unknown action"}), 400

    logger.info("Article %s: %s by %s", article_id, action, uid)
    article = repo.get(article_id)
    return jsonify({"success": True, "status": article["status"],
                    "comments": repo.comments(article_id)})


# ---------------------------------------------------------------------------
# Reviewer list (admins only; shown at the top of /articles)

@articles_bp.route("/reviewers", methods=["GET"])
@require_admin
def list_reviewers():
    added = ArticleRepository().list_reviewers()
    added_ids = {r["user_id"] for r in added}
    from_env = [i for i in webapp_config.ARTICLE_REVIEWER_IDS if i not in added_ids]
    return jsonify({
        "reviewers": added,
        "from_server_settings": from_env,
        "admins_fallback": not reviewer_ids_configured(),
    })


def reviewer_ids_configured() -> bool:
    return bool([i for i in webapp_config.ARTICLE_REVIEWER_IDS if str(i).isdigit()] + _added_reviewer_ids())


@articles_bp.route("/reviewers", methods=["POST"])
@require_admin
def add_reviewer():
    data = request.get_json(silent=True) or {}
    user_id = content.clean_text(str(data.get("user_id") or ""))
    username = content.clean_text(str(data.get("username") or ""))[:60]
    if not (user_id.isdigit() and 15 <= len(user_id) <= 21):
        return jsonify({"error": "That isn't a Discord user ID (15 to 21 digits)."}), 400
    if not username:
        username = _known_name(user_id) or f"User {user_id[-4:]}"
    repo = ArticleRepository()
    repo.add_reviewer(user_id, username, _user_id())
    logger.info("Article reviewer %s added by %s", user_id, _user_id())
    return jsonify({"success": True, "reviewers": repo.list_reviewers()}), 201


@articles_bp.route("/reviewers/<user_id>", methods=["DELETE"])
@require_admin
def remove_reviewer(user_id):
    repo = ArticleRepository()
    if not repo.remove_reviewer(user_id):
        return jsonify({"error": "Not on the reviewer list (people set in the server settings can only be removed there)."}), 404
    logger.info("Article reviewer %s removed by %s", user_id, _user_id())
    return jsonify({"success": True, "reviewers": repo.list_reviewers()})


def _known_name(user_id: str) -> str | None:
    """Display name from the ELO standings, when the player has one."""
    try:
        import sqlite3
        conn = sqlite3.connect(webapp_config.ELO_DB_PATH)
        try:
            row = conn.execute(
                "SELECT user_display_name FROM overall_standings WHERE user_id = ?", (user_id,)
            ).fetchone()
        finally:
            conn.close()
        return row[0] if row and row[0] else None
    except Exception:
        return None
