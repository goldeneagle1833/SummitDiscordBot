"""API routes for the Meta Report.

Public:
  GET  /api/meta-reports                    published reports, newest first
  GET  /api/meta-reports/<slug>             one published report
  POST /api/meta-reports/subscribe          {email} -> confirmation email
  POST /api/meta-reports/email/confirm      {token}
  POST /api/meta-reports/email/unsubscribe  {token}

Admin:
  GET    /api/meta-reports/admin                   every report, subscriber counts
  GET    /api/meta-reports/admin/<slug>            one report, drafts included
  POST   /api/meta-reports/admin/build             {period: "2026-09-b"} build or refresh
  PUT    /api/meta-reports/admin/<slug>/story      {story: [{headline, detail}]}
  PUT    /api/meta-reports/admin/<slug>/notes      {counters: {avatar: why}}
  GET    /api/meta-reports/dm                      logged-in user's Discord DM toggle
  PUT    /api/meta-reports/dm                      {on: bool}
  POST   /api/meta-reports/admin/<slug>/publish    {announce: bool}
  POST   /api/meta-reports/admin/<slug>/unpublish
  DELETE /api/meta-reports/admin/<slug>            drafts only
"""

import logging
import re
import threading
import time
from datetime import timedelta

from flask import Blueprint, jsonify, request, session

from repositories.audit import AuditRepository
from repositories.meta_reports import MetaReportRepository
from services import meta_report
from utils.auth import require_admin, require_auth

logger = logging.getLogger(__name__)

meta_reports_bp = Blueprint("meta_reports", __name__)

_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,24}$")
_SLUG_RE = re.compile(r"^\d{4}-\d{2}-[ab]$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")

# Sign-ups send an email, so each client gets a few per hour.
_SIGNUP_LIMIT = 5
_SIGNUP_WINDOW_S = 3600
_signups: dict[str, list[float]] = {}
_signup_lock = threading.Lock()


def _client_key() -> str:
    return request.headers.get("CF-Connecting-IP") or request.remote_addr or "unknown"


def _allow_signup() -> bool:
    now = time.time()
    key = _client_key()
    with _signup_lock:
        if len(_signups) > 5000:
            _signups.clear()
        hits = [t for t in _signups.get(key, []) if t > now - _SIGNUP_WINDOW_S]
        if len(hits) >= _SIGNUP_LIMIT:
            _signups[key] = hits
            return False
        hits.append(now)
        _signups[key] = hits
    return True


def _admin_name() -> str:
    return session.get("username", "API")


def _audit(action: str, slug: str, details: str) -> None:
    try:
        AuditRepository().log_action(session.get("user_id", 0), _admin_name(), action,
                                     target_id=slug, details=details)
    except Exception:
        logger.exception("Meta report audit log failed")


# ---------------------------------------------------------------------- #
# Public                                                                   #
# ---------------------------------------------------------------------- #

@meta_reports_bp.route("/meta-reports")
def list_reports():
    reports = MetaReportRepository().list_reports(published_only=True)
    items = [{"slug": r["slug"], "from": r["from"], "through": r["through"],
              "label": meta_report.Period.from_slug(r["slug"]).label(),
              "publishLabel": meta_report.Period.from_slug(r["slug"]).publish_label(),
              "publishedAt": r["publishedAt"]} for r in reports]
    return jsonify({"reports": items})


@meta_reports_bp.route("/meta-reports/<slug>")
def get_report(slug):
    if not _SLUG_RE.match(slug):
        return jsonify({"error": "Report not found"}), 404
    report = MetaReportRepository().get(slug)
    if not report or report["status"] != "published":
        return jsonify({"error": "Report not found"}), 404
    return jsonify(meta_report.public_report(report))


@meta_reports_bp.route("/meta-reports/subscribe", methods=["POST"])
def subscribe():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    if not _EMAIL_RE.match(email):
        return jsonify({"error": "Enter a valid email address."}), 400
    if not _allow_signup():
        return jsonify({"error": "Too many sign-ups from here. Try again later."}), 429
    if not meta_report.email_configured():
        return jsonify({"error": "Email isn't set up on the site yet. Try again later."}), 503
    repo = MetaReportRepository()
    sub = repo.add_subscriber(email)
    if sub["confirmed_at"] and not sub["unsubscribed_at"]:
        return jsonify({"status": "subscribed"})
    if not meta_report.send_confirmation(sub):
        return jsonify({"error": "We couldn't send the confirmation email. Try again later."}), 503
    repo.mark_confirm_sent(sub["id"])
    return jsonify({"status": "confirm_sent"})


@meta_reports_bp.route("/meta-reports/email/confirm", methods=["POST"])
def confirm_email():
    token = ((request.get_json(silent=True) or {}).get("token") or "").strip()
    sub = MetaReportRepository().confirm(token) if _TOKEN_RE.match(token) else None
    if not sub:
        return jsonify({"error": "That link isn't valid anymore."}), 404
    return jsonify({"status": "subscribed"})


@meta_reports_bp.route("/meta-reports/email/unsubscribe", methods=["POST"])
def unsubscribe_email():
    token = ((request.get_json(silent=True) or {}).get("token") or "").strip()
    sub = MetaReportRepository().unsubscribe(token) if _TOKEN_RE.match(token) else None
    if not sub:
        return jsonify({"error": "That link isn't valid anymore."}), 404
    return jsonify({"status": "unsubscribed"})


# ---------------------------------------------------------------------- #
# Admin                                                                    #
# ---------------------------------------------------------------------- #

def _admin_row(repo: MetaReportRepository, r: dict) -> dict:
    period = meta_report.Period.from_slug(r["slug"])
    return {**r, "label": period.label(), "publishLabel": period.publish_label(),
            "emails": repo.email_counts(r["id"])}


def _discord_id() -> str | None:
    """The logged-in user's Discord id, or None for Google logins (they can't be DMed)."""
    user_id = str(session.get("user_id") or "")
    return user_id if user_id.isdigit() else None


@meta_reports_bp.route("/meta-reports/dm")
@require_auth
def dm_status():
    discord_id = _discord_id()
    subscribed = bool(discord_id) and MetaReportRepository().dm_subscribed(discord_id)
    return jsonify({"canDm": bool(discord_id), "subscribed": subscribed})


@meta_reports_bp.route("/meta-reports/dm", methods=["PUT"])
@require_auth
def dm_toggle():
    discord_id = _discord_id()
    if not discord_id:
        return jsonify({"error": "Log in with Discord to get report DMs."}), 400
    on = bool((request.get_json(silent=True) or {}).get("on"))
    subscribed = MetaReportRepository().set_dm(discord_id, on)
    return jsonify({"canDm": True, "subscribed": subscribed})


@meta_reports_bp.route("/meta-reports/admin")
@require_admin
def admin_list():
    repo = MetaReportRepository()
    today = meta_report.report_today()
    due = meta_report.latest_due_period(today)
    # Periods an admin can build: the newest due one and the eleven before it.
    periods, p = [], due
    for _ in range(12):
        periods.append({"slug": p.slug, "label": p.label(), "publishLabel": p.publish_label()})
        p = p.previous()
    nxt = meta_report.Period.containing(today)
    while nxt.publish_day <= today:
        nxt = meta_report.Period.containing(nxt.end + timedelta(days=1))
    return jsonify({
        "reports": [_admin_row(repo, r) for r in repo.list_reports(published_only=False)],
        "periods": periods,
        "next": {"slug": nxt.slug, "label": nxt.label(), "publishLabel": nxt.publish_label()},
        "subscribers": repo.subscriber_counts(),
        "dmSubscribers": len(repo.dm_subscriber_ids()),
        "emailConfigured": meta_report.email_configured(),
    })


@meta_reports_bp.route("/meta-reports/admin/<slug>")
@require_admin
def admin_get(slug):
    if not _SLUG_RE.match(slug):
        return jsonify({"error": "Report not found"}), 404
    repo = MetaReportRepository()
    report = repo.get(slug)
    if not report:
        return jsonify({"error": "Report not found"}), 404
    return jsonify({**_admin_row(repo, report), "report": meta_report.public_report(report)})


@meta_reports_bp.route("/meta-reports/admin/build", methods=["POST"])
@require_admin
def admin_build():
    slug = ((request.get_json(silent=True) or {}).get("period") or "").strip()
    try:
        period = meta_report.Period.from_slug(slug)
    except ValueError:
        return jsonify({"error": "Pick a report period."}), 400
    if period.publish_day > meta_report.report_today():
        return jsonify({"error": f"That period's data comes out {period.publish_label()}."}), 400
    report = meta_report.build(period)
    _audit("meta_report_build", period.slug, f"Built meta report {period.label()}")
    return jsonify({"slug": report["slug"], "status": report["status"]})


@meta_reports_bp.route("/meta-reports/admin/<slug>/story", methods=["PUT"])
@require_admin
def admin_story(slug):
    story = (request.get_json(silent=True) or {}).get("story")
    if not isinstance(story, list) or len(story) > 6:
        return jsonify({"error": "Story must be a list of up to 6 takeaways."}), 400
    clean = []
    for item in story:
        if not isinstance(item, dict):
            return jsonify({"error": "Each takeaway needs a headline."}), 400
        headline = str(item.get("headline") or "").strip()[:200]
        detail = str(item.get("detail") or "").strip()[:300]
        if headline:
            clean.append({"headline": headline, "detail": detail})
    repo = MetaReportRepository()
    if not repo.get(slug):
        return jsonify({"error": "Report not found"}), 404
    repo.update_story(slug, clean)
    _audit("meta_report_story", slug, f"Edited meta report takeaways ({len(clean)})")
    return jsonify({"story": clean})


@meta_reports_bp.route("/meta-reports/admin/<slug>/notes", methods=["PUT"])
@require_admin
def admin_notes(slug):
    counters = (request.get_json(silent=True) or {}).get("counters")
    if not isinstance(counters, dict) or len(counters) > 12:
        return jsonify({"error": "Counter notes must be a map of Avatar to text."}), 400
    clean = {str(k)[:80]: str(v or "").strip()[:300] for k, v in counters.items() if str(v or "").strip()}
    repo = MetaReportRepository()
    report = repo.get(slug)
    if not report:
        return jsonify({"error": "Report not found"}), 404
    repo.update_notes(slug, {**(report.get("notes") or {}), "counters": clean})
    _audit("meta_report_notes", slug, f"Edited meta report counter notes ({len(clean)})")
    return jsonify({"counters": clean})


@meta_reports_bp.route("/meta-reports/admin/<slug>/publish", methods=["POST"])
@require_admin
def admin_publish(slug):
    announce = bool((request.get_json(silent=True) or {}).get("announce", True))
    repo = MetaReportRepository()
    if not repo.get(slug):
        return jsonify({"error": "Report not found"}), 404
    report = meta_report.publish(slug, _admin_name(), announce=announce, repo=repo)
    _audit("meta_report_publish", slug,
           f"Published meta report {slug}" + ("" if announce else " without announcing"))
    return jsonify(_admin_row(repo, report))


@meta_reports_bp.route("/meta-reports/admin/<slug>/unpublish", methods=["POST"])
@require_admin
def admin_unpublish(slug):
    repo = MetaReportRepository()
    if not repo.get(slug):
        return jsonify({"error": "Report not found"}), 404
    report = repo.unpublish(slug)
    _audit("meta_report_unpublish", slug, f"Unpublished meta report {slug}")
    return jsonify(_admin_row(repo, report))


@meta_reports_bp.route("/meta-reports/admin/<slug>", methods=["DELETE"])
@require_admin
def admin_delete(slug):
    if not MetaReportRepository().delete_draft(slug):
        return jsonify({"error": "Only drafts can be deleted."}), 400
    _audit("meta_report_delete", slug, f"Deleted meta report draft {slug}")
    return jsonify({"deleted": slug})
