"""Publishing Explorer Series application decisions to applicants.

Approving or rejecting an application is Council-internal until an Explorer
admin publishes. Publishing reveals each new decision on the applicant's
application page, drops a notification in their site bell, and queues a
Discord DM.

Both notifications go through the store's notification tables in store.db:
the bot's StoreNotificationsCog already polls that outbox for discord_dm rows
(the web app has no bot token of its own), and the nav bell already reads
web_notifications.
"""

import logging

from repositories.explorer_applications import (
    DECIDED_STATUSES,
    ExplorerApplicationRepository,
)
from repositories.store import StoreRepository
from services.explorer_notifications import PUBLIC_SITE_URL

logger = logging.getLogger(__name__)

APPLICATION_PATH = "/explorer/apply"

WEB_NOTIFICATION_TYPE = "explorer_application"


def application_url() -> str:
    return f"{PUBLIC_SITE_URL.rstrip('/')}{APPLICATION_PATH}"


def _can_dm(discord_user_id: str | None) -> bool:
    """Only real Discord accounts can be DMed; Google logins have no snowflake."""
    return bool(discord_user_id) and str(discord_user_id).isdigit()


def summarize(changes: list[dict]) -> dict:
    """What a publish would do, for the confirmation prompt."""
    approved = sum(1 for c in changes if c["status"] == "approved")
    rejected = sum(1 for c in changes if c["status"] == "rejected")
    decided = [c for c in changes if c["status"] in DECIDED_STATUSES]
    return {
        "approved": approved,
        "rejected": rejected,
        # Published decisions the Council has since reopened.
        "withdrawn": len(changes) - len(decided),
        # Admin-added candidates never applied, so there is no one to tell.
        "no_account": sum(1 for c in decided if not c.get("discord_user_id")),
        "total": len(changes),
    }


def build_message(application: dict) -> dict:
    """The subject and bodies sent for one decision."""
    first_name = application.get("first_name") or "there"
    lgs = application.get("lgs_name")
    at_lgs = f" at {lgs}" if lgs else ""
    url = application_url()

    if application["status"] == "approved":
        return {
            "subject": "Your Explorer Series application was approved",
            "dm_body": (
                f"Congratulations, {first_name}! The Explorer Series Council has approved "
                f"your application to host an Explorer Series event{at_lgs}. "
                f"We'll be in touch with next steps.\n\n"
                f"View your application: {url}"
            ),
            "web_body": (
                f"The Council approved your application to host{at_lgs}. "
                f"We'll be in touch with next steps."
            ),
        }

    return {
        "subject": "Your Explorer Series application",
        "dm_body": (
            f"Hi {first_name}, thank you for applying to host an Explorer Series event"
            f"{at_lgs}. The Council reviewed every application carefully and is not able "
            f"to accept yours this time.\n\n"
            f"View your application: {url}"
        ),
        "web_body": (
            "The Council has reviewed your application to host an Explorer Series event. "
            "Open your application to see the decision."
        ),
    }


def publish_decisions(
    repo: ExplorerApplicationRepository | None = None,
    store: StoreRepository | None = None,
) -> dict:
    """Publish every unpublished decision and notify each applicant.

    Returns the summary of what was published plus how many DMs and site
    notifications were queued.
    """
    repo = repo or ExplorerApplicationRepository()
    store = store or StoreRepository()

    changes = repo.list_unpublished()
    dms = 0
    web_notifications = 0

    for application in changes:
        status = application["status"]

        if status not in DECIDED_STATUSES:
            # Taken back to review: hide the old decision again, quietly.
            repo.mark_published(application["id"], None)
            continue

        repo.mark_published(application["id"], status)

        user_id = application.get("discord_user_id")
        if not user_id:
            continue

        message = build_message(application)
        try:
            store.create_web_notification(
                str(user_id), WEB_NOTIFICATION_TYPE, message["subject"], message["web_body"]
            )
            web_notifications += 1
            if _can_dm(user_id):
                store.enqueue_notification(
                    None, "discord_dm", str(user_id), message["subject"], message["dm_body"]
                )
                dms += 1
        except Exception:
            # The decision is published either way; a lost notification must
            # not stop everyone after this applicant hearing about theirs.
            logger.exception(
                "Could not queue notifications for Explorer application %s",
                application["id"],
            )

    result = {**summarize(changes), "dms_queued": dms, "web_notifications": web_notifications}
    logger.info("Published Explorer decisions: %s", result)
    return result
