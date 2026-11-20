"""Discord DMs for Top 8 event submissions.

Sent the same way as the player article DMs: a row goes into the
article_notifications queue (articles.db) with no article id, and the bot's
ArticleNotificationsCog delivers it within ~30 seconds as an embed with a
link button back to the site. Queueing never fails a submission.
"""

import logging
import os

import webapp_config

logger = logging.getLogger(__name__)

REVIEW_PATH = "/top-8?review=1"
MINE_PATH = "/top-8?submissions=mine"


def reviewer_ids() -> list[str]:
    """Who approves submissions: TOP8_SUBMISSION_REVIEWERS if set, else the admins.

    Only Discord ids (all digits) can be DMed.
    """
    raw = os.environ.get("TOP8_SUBMISSION_REVIEWERS", "")
    ids = [i.strip() for i in raw.split(",") if i.strip()] or [str(a) for a in webapp_config.ADMINS]
    out = []
    for i in ids:
        if i.isdigit() and i not in out:
            out.append(i)
    return out


def _queue(recipient: str, subject: str, body: str, link_path: str, audience: str):
    from repositories.articles import ArticleRepository
    try:
        ArticleRepository().enqueue_notification(
            recipient=recipient, subject=subject, body=body,
            link_path=link_path, article_id=None, audience=audience,
        )
    except Exception:
        logger.exception("Could not queue a Top 8 submission DM for %s", recipient)


def _event_label(sub: dict) -> str:
    return sub.get("title") or sub.get("event_name") or "an event"


def admin_message(sub: dict) -> tuple[str, str]:
    lines = [
        f"**{sub.get('submitter_name') or 'A player'}** sent in **{_event_label(sub)}** for the Top 8 page.",
        "",
        sub["event_url"],
    ]
    if sub.get("player_count") is not None:
        count = sub["player_count"]
        lines.append(f"Players: {count}" + (" (under 16, will be tagged Local)" if count < 16 else ""))
    if sub.get("event_date"):
        lines.append(f"Date: {sub['event_date']}")
    if sub.get("note"):
        lines += ["", "Their note:", "> " + sub["note"].replace("\n", "\n> ")]
    return "Top 8 event waiting for approval", "\n".join(lines)


def notify_admins(sub: dict) -> int:
    recipients = reviewer_ids()
    if not recipients:
        logger.warning("Top 8 submission %s came in but there is nobody to notify", sub.get("id"))
        return 0
    subject, body = admin_message(sub)
    for rid in recipients:
        _queue(rid, subject, body, REVIEW_PATH, "reviewer")
    return len(recipients)


def outcome_text(sub: dict) -> str:
    """What happened to a submission, in a sentence the player reads."""
    label = _event_label(sub)
    status = sub.get("status")
    result = sub.get("result") or {}
    if status == "approved":
        if result.get("badges_only"):
            return (f"{label} was approved. It had no deck lists, so the placings were "
                    "added to the players' Summit profiles instead of the Top 8 page.")
        if result.get("local"):
            return (f"{label} was approved and added to the Top 8 page, tagged Local "
                    f"because it had {result.get('player_count')} players (under 16).")
        return f"{label} was approved and added to the Top 8 page."
    if status == "rejected":
        return f"{label} was not added to the Top 8 page."
    if status == "failed":
        return f"{label} could not be imported yet. The Summit will try it again."
    return f"{label} is waiting for approval."


def notify_submitter(sub: dict):
    if not sub or sub.get("submitter_provider") != "discord" or not str(sub.get("submitter_id", "")).isdigit():
        return
    body = outcome_text(sub)
    if sub.get("review_note"):
        body += "\n\nNote from the Summit:\n> " + sub["review_note"].replace("\n", "\n> ")
    _queue(str(sub["submitter_id"]), "Your Top 8 event submission", body, MINE_PATH, "author")
