"""Discord notifications for Explorer Series host applications.

The web app has no bot token, so it cannot DM anyone itself. It hands the
recipient list and the message content to the bot's loopback API, which does
the sending.
"""

import logging
import os
import threading

import webapp_config
from repositories.explorer import ExplorerRepository

logger = logging.getLogger(__name__)

PUBLIC_SITE_URL = os.environ.get("PUBLIC_SITE_URL", "http://localhost:5173")

REVIEW_PATH = "/admin/explorer-applications"

# The bot call is a couple of Discord round trips per admin, so give it more
# room than a normal relay but still bound it.
NOTIFY_TIMEOUT_S = 20


def review_url() -> str:
    return f"{PUBLIC_SITE_URL.rstrip('/')}{REVIEW_PATH}"


def recipient_ids() -> list[str]:
    """Discord IDs to notify: everyone who can review applications.

    Mirrors is_explorer_admin() on the server — the explorer_admins table plus
    global site admins, who are a superset. Deduplicated, order preserved so
    the Council comes first.
    """
    ids: list[str] = []
    seen: set[str] = set()

    try:
        for admin in ExplorerRepository().get_explorer_admins():
            admin_id = str(admin.get("discord_user_id") or "").strip()
            if admin_id and admin_id not in seen:
                seen.add(admin_id)
                ids.append(admin_id)
    except Exception:
        logger.exception("Could not read the Explorer admin list for notifications")

    for admin_id in webapp_config.ADMINS:
        admin_id = str(admin_id).strip()
        if admin_id and admin_id not in seen:
            seen.add(admin_id)
            ids.append(admin_id)

    return ids


def build_payload(application: dict, recipients: list[str]) -> dict:
    name = " ".join(
        part for part in (application.get("first_name"), application.get("last_name")) if part
    ).strip()
    location = ", ".join(
        part for part in (application.get("city"), application.get("state")) if part
    )
    return {
        "admin_discord_ids": recipients,
        "applicant_name": name or application.get("discord_handle") or "Someone",
        "discord_handle": application.get("discord_handle") or "",
        "location": location,
        "lgs_name": application.get("lgs_name") or "",
        "review_url": review_url(),
    }


def notify_new_application(application: dict) -> dict | None:
    """DM every Explorer admin about a new application.

    Returns the bot's response, or None when there is nobody to notify or the
    bot could not be reached. Never raises — a failed notification must not
    cost an applicant their submission.
    """
    # Imported here to avoid a circular import at module load: the routes
    # package imports this service.
    from routes.api.matchmaking import relay_to_bot

    recipients = recipient_ids()
    if not recipients:
        logger.warning(
            "New Explorer application, but no Explorer admins or site admins to notify"
        )
        return None

    try:
        body, status = relay_to_bot(
            "POST",
            "/explorer-application-notify",
            build_payload(application, recipients),
            unavailable_body={"sent": 0, "reason": "bot_unavailable"},
            timeout=NOTIFY_TIMEOUT_S,
        )
    except Exception:
        logger.exception("Explorer application notification failed")
        return None

    if status >= 400:
        logger.error("Explorer notification rejected by bot (%s): %s", status, body)
    else:
        logger.info(
            "Explorer notification sent to %s of %s admins",
            body.get("sent"), len(recipients),
        )
    return body


def notify_new_application_in_background(application: dict) -> None:
    """Fire the notification off the request path.

    Each DM is a Discord round trip, and the app runs on a small number of
    sync workers — an applicant should not wait on it, or fail because of it.
    """
    def run():
        try:
            notify_new_application(application)
        except Exception:
            logger.exception("Background Explorer notification failed")

    threading.Thread(target=run, daemon=True).start()
