"""Stripe checkout service for the token-card store.

Flow:
  1. POST /api/store/checkout creates a pending order (stock reserved) and a
     Stripe Checkout Session, returning the hosted payment URL.
  2. Stripe redirects the buyer back to FRONTEND_URL success/cancel pages.
  3. Stripe calls POST /api/store/webhooks/stripe; we verify the signature,
     confirm the amount, and mark the order paid. Expired sessions restock.

Security invariants:
  - Prices always come from the database, never the client.
  - The webhook is the ONLY thing that marks an order paid. The success
    redirect page must never be trusted as proof of payment.
  - Amount and currency from Stripe are checked against the order before
    fulfillment; mismatches are flagged for manual review, not auto-paid.
"""

import logging
import os

import stripe

from repositories.store import StoreRepository
from webapp_config import FRONTEND_URL

logger = logging.getLogger(__name__)

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
FLAT_SHIPPING_CENTS = int(os.environ.get("STORE_FLAT_SHIPPING_CENTS", "599"))
CHECKOUT_EXPIRES_MINUTES = 60  # Stripe minimum is 30

stripe.api_key = STRIPE_SECRET_KEY
stripe.api_version = "2025-06-30.basil"


def _site_url(path: str) -> str:
    base = FRONTEND_URL if FRONTEND_URL != "/" else os.environ.get(
        "PUBLIC_SITE_URL", "http://localhost:5173"
    )
    return base.rstrip("/") + path


class StoreCheckoutService:
    """Creates checkout sessions and processes Stripe webhook events."""

    def __init__(self, repo: StoreRepository | None = None):
        self.repo = repo or StoreRepository()

    def is_configured(self) -> bool:
        return bool(STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET)

    # ------------------------------------------------------------------
    # Checkout
    # ------------------------------------------------------------------

    def create_checkout(
        self,
        user_id: str,
        username: str,
        items: list[dict],
        shipping_address: dict | None = None,
        email: str | None = None,
        auth_provider: str = "discord",
        address_validated: bool = False,
    ) -> dict:
        """Create a pending order and a Stripe Checkout Session.

        Returns {order_number, checkout_url}. Raises ValueError for stock or
        validation problems (caller maps these to HTTP 400/409).
        """
        import time

        order = self.repo.create_order(
            user_id=user_id,
            username=username,
            items=items,
            shipping_address=shipping_address or {},
            email=email,
            auth_provider=auth_provider,
            shipping_cents=FLAT_SHIPPING_CENTS,
            tax_cents=0,  # TODO phase 5+: Stripe Tax for Ohio nexus
            address_validated=address_validated,
        )

        full_order = self.repo.get_order(order["id"])
        line_items = [
            {
                "price_data": {
                    "currency": full_order["currency"].lower(),
                    "product_data": {"name": item["product_name"]},
                    "unit_amount": item["unit_price_cents"],
                },
                "quantity": item["quantity"],
            }
            for item in full_order["items"]
        ]
        if FLAT_SHIPPING_CENTS:
            line_items.append(
                {
                    "price_data": {
                        "currency": full_order["currency"].lower(),
                        "product_data": {"name": "Shipping"},
                        "unit_amount": FLAT_SHIPPING_CENTS,
                    },
                    "quantity": 1,
                }
            )

        try:
            checkout_session = stripe.checkout.Session.create(
                mode="payment",
                line_items=line_items,
                customer_email=email,
                shipping_address_collection={
                    "allowed_countries": ["US"],
                },
                metadata={
                    "order_id": str(order["id"]),
                    "order_number": order["order_number"],
                },
                success_url=_site_url(
                    f"/store/success?order={order['order_number']}"
                ),
                cancel_url=_site_url(
                    f"/store/cancelled?order={order['order_number']}"
                ),
                expires_at=int(time.time()) + CHECKOUT_EXPIRES_MINUTES * 60,
            )
        except stripe.StripeError:
            # Stripe rejected the session: release the reserved stock.
            self.repo.set_status(order["id"], "cancelled")
            self.repo.restock_order_items(order["id"])
            logger.exception(
                f"Stripe session creation failed for order {order['order_number']}"
            )
            raise

        self.repo.attach_payment(order["id"], "stripe", checkout_session.id)
        logger.info(
            f"Checkout created: order {order['order_number']} "
            f"session {checkout_session.id}"
        )
        return {
            "order_number": order["order_number"],
            "checkout_url": checkout_session.url,
        }

    # ------------------------------------------------------------------
    # Webhook
    # ------------------------------------------------------------------

    def construct_event(self, payload: bytes, sig_header: str):
        """Verify webhook signature; raises on tampering or bad signature."""
        return stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )

    def handle_event(self, event) -> dict:
        """Process a verified Stripe event. Returns a status summary dict."""
        etype = event["type"]
        # Stripe Event objects don't support .get(); convert to plain dict
        # so our handlers can use dict.get() safely.
        raw = event["data"]["object"]
        if not isinstance(raw, dict):
            import json
            obj = json.loads(str(raw))
        else:
            obj = raw

        if etype == "checkout.session.completed":
            return self._handle_completed(obj)
        if etype == "checkout.session.expired":
            return self._handle_expired(obj)

        logger.debug(f"Ignoring Stripe event type: {etype}")
        return {"handled": False, "reason": f"ignored event {etype}"}

    def _order_from_session(self, session_obj) -> dict | None:
        order_id = (session_obj.get("metadata") or {}).get("order_id")
        if order_id:
            order = self.repo.get_order(int(order_id))
            if order:
                return order
        # Fallback: look up by attached session id
        return self.repo.get_order_by_payment_ref("stripe", session_obj["id"])

    def _handle_completed(self, session_obj) -> dict:
        order = self._order_from_session(session_obj)
        if order is None:
            logger.error(f"Webhook for unknown order: session {session_obj['id']}")
            return {"handled": False, "reason": "order not found"}

        if session_obj.get("payment_status") != "paid":
            # Delayed methods would surface here; card payments are 'paid'.
            logger.info(
                f"Session completed but not paid yet: {order['order_number']}"
            )
            return {"handled": False, "reason": "payment not settled"}

        # Verify what Stripe charged matches what we expected.
        amount = session_obj.get("amount_total")
        currency = (session_obj.get("currency") or "").upper()
        if amount != order["total_cents"] or currency != order["currency"]:
            self.repo.log_action(
                "stripe-webhook", "system", "amount_mismatch",
                f"order={order['order_number']} expected={order['total_cents']} "
                f"{order['currency']} got={amount} {currency}",
            )
            logger.error(
                f"AMOUNT MISMATCH on {order['order_number']}: "
                f"expected {order['total_cents']} {order['currency']}, "
                f"got {amount} {currency} - flagged for manual review"
            )
            return {"handled": False, "reason": "amount mismatch"}

        if self.repo.mark_paid(order["id"]):
            # Save shipping address collected by Stripe Checkout
            shipping = session_obj.get("shipping_details") or session_obj.get("shipping") or {}
            if shipping.get("address"):
                addr = shipping["address"]
                self.repo.update_shipping_address(order["id"], {
                    "name": shipping.get("name", ""),
                    "line1": addr.get("line1", ""),
                    "line2": addr.get("line2", ""),
                    "city": addr.get("city", ""),
                    "state": addr.get("state", ""),
                    "postal": addr.get("postal_code", ""),
                    "country": addr.get("country", "US"),
                })
            self.repo.log_action(
                "stripe-webhook", "system", "order_paid",
                f"order={order['order_number']} amount={amount}",
            )
            logger.info(f"Order paid: {order['order_number']}")
            try:
                from services.store_notifications import StoreNotificationService
                StoreNotificationService(self.repo).notify_order_paid(
                    self.repo.get_order(order["id"])
                )
            except Exception:
                logger.exception(
                    f"Notification enqueue failed for {order['order_number']}"
                )
            return {"handled": True, "order_number": order["order_number"]}

        # Already paid: webhook retry/duplicate. Fine.
        return {"handled": True, "reason": "already paid (duplicate event)"}

    def _handle_expired(self, session_obj) -> dict:
        order = self._order_from_session(session_obj)
        if order is None or order["status"] != "pending_payment":
            return {"handled": False, "reason": "no pending order to expire"}

        self.repo.set_status(order["id"], "cancelled")
        self.repo.restock_order_items(order["id"])
        self.repo.log_action(
            "stripe-webhook", "system", "checkout_expired",
            f"order={order['order_number']} restocked",
        )
        logger.info(f"Checkout expired, restocked: {order['order_number']}")
        return {"handled": True, "order_number": order["order_number"]}
