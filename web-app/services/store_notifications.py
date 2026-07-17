"""Order notification routing for the store.

Routing rules:
  - Admin channel ping: always, via the notifications outbox
    (the Discord bot's StoreNotificationsCog polls and delivers).
  - Buyer, logged in with Discord: bot DM via the outbox.
  - Email receipt: ALWAYS sent when the buyer has an email address.
    The order confirmation email is a full HTML receipt.

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
PUBLIC_SITE_URL = os.environ.get("PUBLIC_SITE_URL", "http://localhost:5173")


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
            f"Ship to: {order.get('ship_city', '')}, {order.get('ship_state', '')}",
        )

        # In-app web notification
        self.repo.create_web_notification(
            order["user_id"], "order_paid",
            f"Order {order['order_number']} confirmed",
            f"Your order for {total} has been confirmed. We'll send tracking when it ships.",
        )

        # Discord DM for Discord users
        provider = order.get("auth_provider") or "discord"
        if provider == "discord" and not str(order["user_id"]).startswith("google_"):
            dm_body = (
                f"Thanks for your order, {order.get('ship_name') or order['username']}!\n\n"
                f"Order {order['order_number']} — {total}\n{item_lines}\n\n"
                f"We'll send tracking as soon as it ships."
            )
            self.repo.enqueue_notification(
                order["id"], "discord_dm", str(order["user_id"]),
                f"{STORE_NAME}: order {order['order_number']} confirmed",
                dm_body,
            )

        # Email receipt — always send when we have an email
        email = order.get("email")
        if email:
            subject = f"{STORE_NAME}: Receipt for order {order['order_number']}"
            html = _build_receipt_html(order)
            plain = _build_receipt_plain(order)
            nid = self.repo.enqueue_notification(
                order["id"], "email", email, subject, plain
            )
            self._try_send_email(nid, email, subject, plain, html=html)
        else:
            self.repo.log_action(
                "notifications", "system", "no_email_for_receipt",
                f"order={order['order_number']} provider={provider}",
            )
            logger.warning(
                f"No email for receipt on {order['order_number']}: provider={provider}"
            )

    def notify_order_shipped(self, order: dict) -> None:
        tracking = order.get("tracking_number")
        carrier = order.get("tracking_carrier") or "Carrier"
        subject = f"{STORE_NAME}: order {order['order_number']} shipped!"
        if tracking:
            body = (
                f"Good news — your order {order['order_number']} is on the way.\n\n"
                f"{carrier} tracking: {tracking}"
            )
            notif_body = f"{carrier} tracking: {tracking}"
        else:
            body = (
                f"Good news — your order {order['order_number']} is on the way."
            )
            notif_body = "Your order is on its way!"
        self._notify_buyer(order, subject, body)

        # In-app web notification
        self.repo.create_web_notification(
            order["user_id"], "order_shipped",
            f"Order {order['order_number']} shipped!",
            notif_body,
        )

    # ------------------------------------------------------------------
    # Routing (for non-receipt notifications like shipping)
    # ------------------------------------------------------------------

    def _notify_buyer(self, order: dict, subject: str, body: str) -> None:
        provider = order.get("auth_provider") or "discord"
        email = order.get("email")

        if provider == "discord" and not str(order["user_id"]).startswith("google_"):
            self.repo.enqueue_notification(
                order["id"], "discord_dm", str(order["user_id"]), subject, body
            )

        # Always email when available
        if email:
            nid = self.repo.enqueue_notification(
                order["id"], "email", email, subject, body
            )
            self._try_send_email(nid, email, subject, body)
        elif provider != "discord":
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
                        subject: str, body: str, html: str | None = None) -> None:
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
            if html:
                msg.add_alternative(html, subtype="html")
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


# ======================================================================
# Receipt templates
# ======================================================================

def _build_receipt_plain(order: dict) -> str:
    """Plain-text fallback for the receipt email."""
    items = order.get("items", [])
    currency = order.get("currency", "USD")
    lines = [
        f"{STORE_NAME} — Order Receipt",
        f"Order: {order['order_number']}",
        "",
        "Items:",
    ]
    for item in items:
        line_total = item["unit_price_cents"] * item["quantity"]
        lines.append(
            f"  {item['quantity']}x {item['product_name']}  "
            f"{_fmt_money(item['unit_price_cents'], currency)} each  "
            f"= {_fmt_money(line_total, currency)}"
        )
    lines.append("")
    lines.append(f"Subtotal:  {_fmt_money(order.get('subtotal_cents', 0), currency)}")
    if order.get("shipping_cents"):
        lines.append(f"Shipping:  {_fmt_money(order['shipping_cents'], currency)}")
    if order.get("tax_cents"):
        lines.append(f"Tax:       {_fmt_money(order['tax_cents'], currency)}")
    lines.append(f"Total:     {_fmt_money(order['total_cents'], currency)}")
    lines.append("")

    # Shipping address
    if order.get("ship_name") or order.get("ship_line1"):
        lines.append("Shipping to:")
        if order.get("ship_name"):
            lines.append(f"  {order['ship_name']}")
        if order.get("ship_line1"):
            lines.append(f"  {order['ship_line1']}")
        if order.get("ship_line2"):
            lines.append(f"  {order['ship_line2']}")
        city_state = ", ".join(
            filter(None, [order.get("ship_city"), order.get("ship_state")])
        )
        if city_state or order.get("ship_postal"):
            lines.append(f"  {city_state} {order.get('ship_postal', '')}".strip())
        if order.get("ship_country") and order["ship_country"] != "US":
            lines.append(f"  {order['ship_country']}")
        lines.append("")

    lines.append("We'll send tracking as soon as your order ships.")
    lines.append("")
    lines.append(f"View your orders: {PUBLIC_SITE_URL.rstrip('/')}/store/orders")
    return "\n".join(lines)


def _build_receipt_html(order: dict) -> str:
    """HTML receipt email with order details."""
    items = order.get("items", [])
    currency = order.get("currency", "USD")
    site = PUBLIC_SITE_URL.rstrip("/")

    # Build item rows
    item_rows = ""
    for item in items:
        line_total = item["unit_price_cents"] * item["quantity"]
        img_cell = ""
        if item.get("image_url"):
            img_src = item["image_url"]
            if img_src.startswith("/"):
                img_src = f"{site}{img_src}"
            img_cell = (
                f'<td style="padding:12px 12px 12px 0;width:60px;vertical-align:top">'
                f'<img src="{img_src}" alt="" width="60" height="60" '
                f'style="border-radius:6px;object-fit:cover;display:block" />'
                f'</td>'
            )
        else:
            img_cell = (
                '<td style="padding:12px 12px 12px 0;width:60px;vertical-align:top">'
                '<div style="width:60px;height:60px;border-radius:6px;'
                'background:#2a2a2e;border:1px solid #3a3a3e"></div>'
                '</td>'
            )
        item_rows += f"""
        <tr>
          {img_cell}
          <td style="padding:12px 0;vertical-align:top">
            <div style="font-weight:600;color:#e0e0e0">{item['product_name']}</div>
            <div style="font-size:13px;color:#999;margin-top:2px">
              {_fmt_money(item['unit_price_cents'], currency)} x {item['quantity']}
            </div>
          </td>
          <td style="padding:12px 0 12px 12px;text-align:right;vertical-align:top;
                      font-weight:600;color:#e0e0e0;white-space:nowrap">
            {_fmt_money(line_total, currency)}
          </td>
        </tr>"""

    # Build totals
    totals_rows = f"""
    <tr>
      <td style="padding:6px 0;color:#999">Subtotal</td>
      <td style="padding:6px 0;text-align:right;color:#e0e0e0">
        {_fmt_money(order.get('subtotal_cents', 0), currency)}
      </td>
    </tr>"""
    if order.get("shipping_cents"):
        totals_rows += f"""
    <tr>
      <td style="padding:6px 0;color:#999">Shipping</td>
      <td style="padding:6px 0;text-align:right;color:#e0e0e0">
        {_fmt_money(order['shipping_cents'], currency)}
      </td>
    </tr>"""
    else:
        totals_rows += """
    <tr>
      <td style="padding:6px 0;color:#999">Shipping</td>
      <td style="padding:6px 0;text-align:right;color:#70c77e">Free</td>
    </tr>"""
    if order.get("tax_cents"):
        totals_rows += f"""
    <tr>
      <td style="padding:6px 0;color:#999">Tax</td>
      <td style="padding:6px 0;text-align:right;color:#e0e0e0">
        {_fmt_money(order['tax_cents'], currency)}
      </td>
    </tr>"""

    # Shipping address block
    shipping_html = ""
    if order.get("ship_name") or order.get("ship_line1"):
        addr_lines = []
        if order.get("ship_name"):
            addr_lines.append(f"<strong>{order['ship_name']}</strong>")
        if order.get("ship_line1"):
            addr_lines.append(order["ship_line1"])
        if order.get("ship_line2"):
            addr_lines.append(order["ship_line2"])
        city_state = ", ".join(
            filter(None, [order.get("ship_city"), order.get("ship_state")])
        )
        if city_state or order.get("ship_postal"):
            addr_lines.append(f"{city_state} {order.get('ship_postal', '')}".strip())
        if order.get("ship_country") and order["ship_country"] != "US":
            addr_lines.append(order["ship_country"])
        addr_body = "<br>".join(addr_lines)
        shipping_html = f"""
      <div style="margin-top:24px;padding-top:20px;border-top:1px solid #3a3a3e">
        <div style="font-size:13px;color:#999;margin-bottom:8px;text-transform:uppercase;
                    letter-spacing:0.5px;font-weight:600">Shipping to</div>
        <div style="color:#e0e0e0;font-size:14px;line-height:1.6">{addr_body}</div>
      </div>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#1a1a1e;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
  <div style="max-width:560px;margin:0 auto;padding:32px 16px">
    <!-- Header -->
    <div style="text-align:center;margin-bottom:32px">
      <h1 style="margin:0;font-size:22px;color:#d4a843;font-weight:700">{STORE_NAME}</h1>
      <p style="margin:8px 0 0;color:#999;font-size:14px">Order Receipt</p>
    </div>

    <!-- Card -->
    <div style="background:#222226;border:1px solid #3a3a3e;border-radius:12px;overflow:hidden">
      <!-- Order header -->
      <div style="padding:20px 24px;border-bottom:1px solid #3a3a3e;
                  display:flex;justify-content:space-between;align-items:center">
        <div>
          <div style="font-size:13px;color:#999;margin-bottom:4px">Order number</div>
          <div style="font-family:monospace;font-size:15px;color:#e0e0e0;font-weight:600">
            {order['order_number']}
          </div>
        </div>
      </div>

      <!-- Items -->
      <div style="padding:12px 24px">
        <table style="width:100%;border-collapse:collapse;font-size:14px">
          {item_rows}
        </table>
      </div>

      <!-- Totals -->
      <div style="padding:16px 24px;border-top:1px solid #3a3a3e">
        <table style="width:100%;border-collapse:collapse;font-size:14px">
          {totals_rows}
          <tr>
            <td style="padding:12px 0 6px;font-weight:700;color:#e0e0e0;font-size:16px;
                        border-top:1px solid #3a3a3e">Total</td>
            <td style="padding:12px 0 6px;text-align:right;font-weight:700;color:#d4a843;
                        font-size:16px;border-top:1px solid #3a3a3e">
              {_fmt_money(order['total_cents'], currency)}
            </td>
          </tr>
        </table>
      </div>

      <!-- Shipping address -->
      {shipping_html and f'<div style="padding:0 24px 20px">{shipping_html}</div>' or ''}
    </div>

    <!-- Footer -->
    <div style="text-align:center;margin-top:24px;font-size:13px;color:#777">
      <p style="margin:0 0 12px">We'll send tracking as soon as your order ships.</p>
      <a href="{site}/store/orders"
         style="color:#d4a843;text-decoration:none;font-weight:600">View your orders</a>
    </div>

    <div style="text-align:center;margin-top:32px;font-size:11px;color:#555">
      {STORE_NAME} &mdash; sorcererssummit.com
    </div>
  </div>
</body>
</html>"""
