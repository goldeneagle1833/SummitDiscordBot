"""Order notification routing for the store.

Routing rules:
  - Admin channel ping: always, via the notifications outbox
    (the Discord bot's StoreNotificationsCog polls and delivers).
  - Buyer, logged in with Discord: bot DM via the outbox.
  - Buyer, logged in with Google (or DM unavailable): email via SMTP,
    sent inline here with failures left pending in the outbox for retry.

The outbox table in store.db is the bridge between the two processes:
the web app enqueues, the bot delivers Discord messages, and the web app
delivers email.
"""

import logging
import os
import smtplib
from email.message import EmailMessage

from repositories.store import StoreRepository

logger = logging.getLogger(__name__)

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)
STORE_NAME = os.environ.get("STORE_NAME", "Summit Store")


def _fmt_money(cents: int, currency: str = "USD") -> str:
    return f"${cents / 100:.2f}" if currency == "USD" else f"{cents / 100:.2f} {currency}"


class StoreNotificationService:
    def __init__(self, repo: StoreRepository | None = None):
        self.repo = repo or StoreRepository()

    # ------------------------------------------------------------------
    # Event entry points
    # ------------------------------------------------------------------

    def notify_order_paid(self, order: dict) -> None:
        items = order.get("items", [])
        item_lines = "\n".join(
            f"  {i['quantity']}x {i['product_name']}" for i in items
        )
        total = _fmt_money(order["total_cents"], order["currency"])

        # Admin ping (recipient resolved by the bot from its config)
        self.repo.enqueue_notification(
            order["id"], "discord_admin", "store-admins",
            f"New paid order {order['order_number']}",
            f"**{order['username']}** ({order['user_id']}) — {total}\n"
            f"{item_lines}\n"
            f"Ship to: {order['ship_city']}, {order['ship_state']}",
        )

        # In-app web notification
        self.repo.create_web_notification(
            order["user_id"], "order_paid",
            f"Order {order['order_number']} confirmed",
            f"Your order for {total} has been confirmed. We'll send tracking when it ships.",
        )

        # Buyer confirmation
        subject = f"{STORE_NAME}: order {order['order_number']} confirmed"
        body = (
            f"Thanks for your order, {order['ship_name'] or order['username']}!\n\n"
            f"Order {order['order_number']} — {total}\n{item_lines}\n\n"
            f"We'll send tracking as soon as it ships."
        )
        self._notify_buyer(order, subject, body)

    def notify_order_shipped(self, order: dict) -> None:
        carrier = order.get("tracking_carrier") or "Carrier"
        subject = f"{STORE_NAME}: order {order['order_number']} shipped!"
        body = (
            f"Good news — your order {order['order_number']} is on the way.\n\n"
            f"{carrier} tracking: {order['tracking_number']}"
        )
        self._notify_buyer(order, subject, body)

        # In-app web notification
        self.repo.create_web_notification(
            order["user_id"], "order_shipped",
            f"Order {order['order_number']} shipped!",
            f"{carrier} tracking: {order['tracking_number']}",
        )

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def _notify_buyer(self, order: dict, subject: str, body: str) -> None:
        provider = order.get("auth_provider") or "discord"
        email = order.get("email")

        if provider == "discord" and not str(order["user_id"]).startswith("google_"):
            self.repo.enqueue_notification(
                order["id"], "discord_dm", str(order["user_id"]), subject, body
            )
            # Also email if they gave one at checkout (belt and braces:
            # DMs can be closed, and the bot marks those failed).
            if email:
                nid = self.repo.enqueue_notification(
                    order["id"], "email", email, subject, body
                )
                self._try_send_email(nid, email, subject, body)
            return

        # Google-auth buyers (or anything else): email only
        if email:
            nid = self.repo.enqueue_notification(
                order["id"], "email", email, subject, body
            )
            self._try_send_email(nid, email, subject, body)
        else:
            self.repo.log_action(
                "notifications", "system", "no_buyer_channel",
                f"order={order['order_number']} provider={provider} no email",
            )
            logger.warning(
                f"No way to reach buyer for {order['order_number']}: "
                f"provider={provider}, no email on order"
            )

    # ------------------------------------------------------------------
    # Email delivery
    # ------------------------------------------------------------------

    def email_configured(self) -> bool:
        return bool(SMTP_HOST and SMTP_FROM)

    def _try_send_email(self, notification_id: int, to_addr: str,
                        subject: str, body: str) -> None:
        if not self.email_configured():
            self.repo.mark_notification(
                notification_id, success=False, error="SMTP not configured"
            )
            return
        try:
            msg = EmailMessage()
            msg["From"] = SMTP_FROM
            msg["To"] = to_addr
            msg["Subject"] = subject
            msg.set_content(body)
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
                smtp.starttls()
                if SMTP_USER:
                    smtp.login(SMTP_USER, SMTP_PASSWORD)
                smtp.send_message(msg)
            self.repo.mark_notification(notification_id, success=True)
            logger.info(f"Order email sent to {to_addr}")
        except Exception as e:
            self.repo.mark_notification(notification_id, success=False, error=str(e))
            logger.warning(f"Order email to {to_addr} failed: {e}")

    def retry_pending_emails(self) -> int:
        """Retry unsent emails; call opportunistically or from cron."""
        pending = self.repo.fetch_pending_notifications(("email",))
        for n in pending:
            self._try_send_email(n["id"], n["recipient"], n["subject"], n["body"])
        return len(pending)
