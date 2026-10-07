"""Stripe checkout service for the token-card store.

Flow:
  1. POST /api/store/checkout creates a pending order (stock reserved) and a
     Stripe Checkout Session, returning the hosted payment URL.
  2. Stripe redirects the buyer back to FRONTEND_URL success/cancel pages.
  3. Stripe calls POST /api/store/webhooks/stripe; we verify the signature,
     confirm the amount, and mark the order paid. Expired sessions restock.

Storefronts:
  Summit Store takes payments on Summit's own Stripe account. Every other
  storefront takes them on its own Stripe account, connected to Summit's
  through Stripe Connect (Standard accounts, direct charges): the session
  is created on the connected account, and its events arrive on the
  Connect webhook endpoint with ``event.account`` set. A storefront can't
  check out until its account can take charges.

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
from webapp_config import FRONTEND_URL, FREE_SHIPPING_ROLE_IDS

logger = logging.getLogger(__name__)

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
# Signing secret of the separate "connected accounts" webhook endpoint
STRIPE_CONNECT_WEBHOOK_SECRET = os.environ.get("STRIPE_CONNECT_WEBHOOK_SECRET", "")
FLAT_SHIPPING_CENTS = int(os.environ.get("STORE_FLAT_SHIPPING_CENTS", "599"))
CHECKOUT_EXPIRES_MINUTES = 60  # Stripe minimum is 30

# Stripe Shipping Rate IDs (create via Stripe Dashboard or API)
STRIPE_SHIPPING_RATE_DOMESTIC = os.environ.get("STRIPE_SHIPPING_RATE_DOMESTIC", "")
STRIPE_SHIPPING_RATE_INTERNATIONAL = os.environ.get("STRIPE_SHIPPING_RATE_INTERNATIONAL", "")
STRIPE_SHIPPING_RATE_FREE = os.environ.get("STRIPE_SHIPPING_RATE_FREE", "")

stripe.api_key = STRIPE_SECRET_KEY


def _site_url(path: str) -> str:
    base = FRONTEND_URL if FRONTEND_URL != "/" else os.environ.get(
        "PUBLIC_SITE_URL", "http://localhost:5173"
    )
    return base.rstrip("/") + path


def shipping_address_from_session(session_obj) -> dict | None:
    """Pull the buyer's shipping address out of a Checkout Session.

    Stripe API versions from 2025-03-31 onward moved the address from the
    top-level ``shipping_details`` to ``collected_information.shipping_details``.
    Which shape arrives depends on the API version pinned on the webhook
    endpoint (and on the SDK for retrieves), so accept both. Returns the
    address in the repository's key format, or None if none was collected.
    """
    shipping = (
        session_obj.get("shipping_details")
        or (session_obj.get("collected_information") or {}).get("shipping_details")
        or session_obj.get("shipping")
        or {}
    )
    addr = shipping.get("address") if shipping else None
    if not addr:
        return None
    return {
        "name": shipping.get("name") or "",
        "line1": addr.get("line1") or "",
        "line2": addr.get("line2") or "",
        "city": addr.get("city") or "",
        "state": addr.get("state") or "",
        "postal": addr.get("postal_code") or "",
        "country": addr.get("country") or "US",
    }


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
        discord_roles: list[str] | None = None,
    ) -> dict:
        """Create a pending order and a Stripe Checkout Session.

        Returns {order_number, checkout_url}. Raises ValueError for stock or
        validation problems (caller maps these to HTTP 400/409).
        """
        import time

        storefront = self._storefront_for_items(items)
        if storefront and not self.repo.accepts_payments(storefront):
            raise ValueError(f"{storefront['name']} isn't taking orders yet")
        stripe_account = self.repo.stripe_account_for(storefront)

        # Free shipping for Patreon / Summit ticket holders, on Summit's
        # own products only
        has_free_shipping = bool(
            not stripe_account
            and discord_roles and FREE_SHIPPING_ROLE_IDS.intersection(discord_roles)
        )

        # Build Stripe shipping_options from Shipping Rate objects. Those
        # live on Summit's account, so connected storefronts use their own
        # flat rate instead.
        use_shipping_rates = bool(
            not stripe_account
            and STRIPE_SHIPPING_RATE_DOMESTIC
            and STRIPE_SHIPPING_RATE_INTERNATIONAL
        )

        if stripe_account:
            shipping_options = None
            shipping_cents = (
                storefront["shipping_cents"]
                if storefront.get("shipping_cents") is not None
                else FLAT_SHIPPING_CENTS
            )
        elif has_free_shipping and STRIPE_SHIPPING_RATE_FREE:
            shipping_options = [
                {"shipping_rate": STRIPE_SHIPPING_RATE_FREE},
            ]
            shipping_cents = 0
        elif use_shipping_rates:
            shipping_options = [
                {"shipping_rate": STRIPE_SHIPPING_RATE_DOMESTIC},
                {"shipping_rate": STRIPE_SHIPPING_RATE_INTERNATIONAL},
            ]
            # Actual shipping cost determined by Stripe at checkout;
            # store 0 now, update from webhook when payment completes.
            shipping_cents = 0
        else:
            # Fallback: flat-rate domestic-only (legacy / unconfigured)
            shipping_options = None
            shipping_cents = 0 if has_free_shipping else FLAT_SHIPPING_CENTS

        order = self.repo.create_order(
            user_id=user_id,
            username=username,
            items=items,
            shipping_address=shipping_address or {},
            email=email,
            auth_provider=auth_provider,
            shipping_cents=shipping_cents,
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
        # Only add shipping as a line item if NOT using Stripe Shipping Rates
        if not use_shipping_rates and not has_free_shipping and shipping_cents:
            line_items.append(
                {
                    "price_data": {
                        "currency": full_order["currency"].lower(),
                        "product_data": {"name": "Shipping"},
                        "unit_amount": shipping_cents,
                    },
                    "quantity": 1,
                }
            )

        # The success/cancel pages clear or keep this storefront's cart only
        storefront = self.repo.get_storefront(full_order["storefront_id"]) or {}
        stripe_account = self.repo.stripe_account_for(storefront)
        sf = f"&storefront={storefront.get('slug', '')}" if storefront else ""

        session_params = {
            "mode": "payment",
            "line_items": line_items,
            "customer_email": email,
            "metadata": {
                "order_id": str(order["id"]),
                "order_number": order["order_number"],
                "storefront": storefront.get("slug", ""),
            },
            "success_url": _site_url(
                f"/store/success?order={order['order_number']}{sf}"
            ),
            "cancel_url": _site_url(
                f"/store/cancelled?order={order['order_number']}{sf}"
            ),
            "expires_at": int(time.time()) + CHECKOUT_EXPIRES_MINUTES * 60,
        }

        # Always collect a shipping address
        session_params["shipping_address_collection"] = {
            "allowed_countries": ["US", "CA", "GB", "AU", "DE", "FR",
                                  "NL", "IT", "ES", "AT", "BE", "JP"],
        }

        if shipping_options:
            session_params["shipping_options"] = shipping_options

        try:
            checkout_session = stripe.checkout.Session.create(
                **session_params, **self._account_kwargs(stripe_account)
            )
        except stripe.StripeError:
            # Stripe rejected the session: release the reserved stock.
            self.repo.cancel_order(order["id"], from_statuses=("pending_payment",))
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

    def _storefront_for_items(self, items: list[dict]) -> dict | None:
        for item in items:
            try:
                product = self.repo.get_product(int(item.get("product_id")))
            except (TypeError, ValueError):
                continue
            if product:
                return self.repo.get_storefront(product.get("storefront_id"))
        return None

    @staticmethod
    def _account_kwargs(stripe_account: str | None) -> dict:
        return {"stripe_account": stripe_account} if stripe_account else {}

    def _order_account(self, order: dict) -> str | None:
        return self.repo.stripe_account_for(
            self.repo.get_storefront(order.get("storefront_id"))
        )

    # ------------------------------------------------------------------
    # Stripe Connect onboarding (one Standard account per storefront)
    # ------------------------------------------------------------------

    def start_onboarding(self, storefront: dict, return_url: str, refresh_url: str) -> str:
        """Return a Stripe onboarding link, creating the account if needed."""
        account_id = storefront.get("stripe_account_id")
        if not account_id:
            account = stripe.Account.create(
                type="standard",
                email=storefront.get("contact_email") or None,
                business_profile={"name": storefront["name"]},
                metadata={"storefront_id": str(storefront["id"]),
                          "storefront": storefront["slug"]},
            )
            account_id = account.id
            self.repo.set_storefront_stripe(storefront["id"], account_id, False)
        link = stripe.AccountLink.create(
            account=account_id,
            type="account_onboarding",
            return_url=return_url,
            refresh_url=refresh_url,
        )
        return link.url

    def refresh_account_status(self, storefront: dict) -> bool:
        """Ask Stripe whether the storefront's account can take charges."""
        account_id = storefront.get("stripe_account_id")
        if not account_id:
            return False
        account = stripe.Account.retrieve(account_id)
        enabled = bool(account.get("charges_enabled"))
        self.repo.set_stripe_charges_enabled(account_id, enabled)
        return enabled

    # ------------------------------------------------------------------
    # Admin cancel
    # ------------------------------------------------------------------

    def cancel_order(self, order: dict) -> bool:
        """Cancel an order and return its stock.

        For unpaid orders the Stripe Checkout Session is expired first, so
        the buyer can't pay for an order that no longer exists. Returns False
        if the order was not in a cancellable status (nothing changed).
        Raises ValueError if the buyer completed payment in the meantime.
        """
        if order["status"] == "pending_payment":
            self._expire_checkout_session(order)
        return self.repo.cancel_order(order["id"])

    def _expire_checkout_session(self, order: dict) -> None:
        if order.get("payment_provider") != "stripe" or not order.get("payment_ref"):
            return  # Session was never created, nothing to close
        account = self._account_kwargs(self._order_account(order))
        try:
            stripe.checkout.Session.expire(order["payment_ref"], **account)
        except stripe.StripeError:
            # Expire only works on open sessions; find out why it wasn't.
            status = stripe.checkout.Session.retrieve(
                order["payment_ref"], **account
            ).status
            if status == "complete":
                raise ValueError(
                    "The buyer just completed payment for this order. "
                    "Refresh the order queue before cancelling."
                )
            if status != "expired":
                raise

    # ------------------------------------------------------------------
    # Webhook
    # ------------------------------------------------------------------

    def construct_event(self, payload: bytes, sig_header: str):
        """Verify webhook signature; raises on tampering or bad signature.

        Summit's own events and connected-account events come from two
        endpoints with different signing secrets; either one is accepted.
        """
        secrets = [s for s in (STRIPE_WEBHOOK_SECRET, STRIPE_CONNECT_WEBHOOK_SECRET) if s]
        for secret in secrets[:-1]:
            try:
                return stripe.Webhook.construct_event(payload, sig_header, secret)
            except stripe.SignatureVerificationError:
                continue
        return stripe.Webhook.construct_event(payload, sig_header, secrets[-1])

    def handle_event(self, event) -> dict:
        """Process a verified Stripe event. Returns a status summary dict."""
        etype = event["type"]
        # Set on events from a storefront's connected account; None for Summit's
        try:
            account = event["account"] or None
        except (KeyError, TypeError):
            account = None
        # Stripe Event objects don't support .get(); convert to plain dict
        # so our handlers can use dict.get() safely.
        raw = event["data"]["object"]
        if not isinstance(raw, dict):
            import json
            obj = json.loads(str(raw))
        else:
            obj = raw

        if etype == "checkout.session.completed":
            return self._handle_completed(obj, account)
        if etype == "checkout.session.expired":
            return self._handle_expired(obj, account)
        if etype == "account.updated":
            if self.repo.set_stripe_charges_enabled(
                obj.get("id"), bool(obj.get("charges_enabled"))
            ):
                return {"handled": True, "reason": "storefront account updated"}
            return {"handled": False, "reason": "unknown account"}

        logger.debug(f"Ignoring Stripe event type: {etype}")
        return {"handled": False, "reason": f"ignored event {etype}"}

    def _order_from_session(self, session_obj, account: str | None = None) -> dict | None:
        order = None
        order_id = (session_obj.get("metadata") or {}).get("order_id")
        if order_id:
            order = self.repo.get_order(int(order_id))
        if order is None:
            # Fallback: look up by attached session id
            order = self.repo.get_order_by_payment_ref("stripe", session_obj["id"])
        if order is None:
            return None
        # A storefront owner controls their own Stripe account, so a session
        # from it may only ever settle that storefront's orders.
        expected = self._order_account(order)
        if (account or None) != expected:
            logger.error(
                f"Stripe account mismatch for {order['order_number']}: "
                f"event from {account or 'platform'}, order belongs to "
                f"{expected or 'platform'}"
            )
            self.repo.log_action(
                "stripe-webhook", "system", "account_mismatch",
                f"order={order['order_number']} event_account={account} "
                f"expected={expected} session={session_obj.get('id')}",
            )
            return None
        return order

    def _handle_completed(self, session_obj, account: str | None = None) -> dict:
        order = self._order_from_session(session_obj, account)
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

        # When using Stripe Shipping Rates, the order's shipping_cents is 0
        # at creation time because Stripe determines it. Update the order
        # with the actual shipping cost before comparing totals.
        stripe_shipping = session_obj.get("shipping_cost") or {}
        stripe_shipping_cents = stripe_shipping.get("amount_total", 0)
        if stripe_shipping_cents and order["shipping_cents"] == 0:
            new_total = order["subtotal_cents"] + stripe_shipping_cents + order["tax_cents"]
            with self.repo._connect() as conn:
                conn.execute(
                    """UPDATE orders SET shipping_cents = ?, total_cents = ?,
                       updated_at = ? WHERE id = ?""",
                    (stripe_shipping_cents, new_total,
                     self.repo._now(), order["id"]),
                )
            order["shipping_cents"] = stripe_shipping_cents
            order["total_cents"] = new_total

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

        # Save the shipping address collected by Stripe Checkout BEFORE the
        # paid transition: if anything below fails, the webhook returns 500
        # and Stripe retries, but a retry skips everything after mark_paid.
        address = shipping_address_from_session(session_obj)
        if address:
            self.repo.update_shipping_address(order["id"], address)

        if self.repo.mark_paid(order["id"]):
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

        status = self.repo.get_order(order["id"])["status"]
        if status in ("paid", "shipped", "delivered"):
            # Already paid: webhook retry/duplicate. Fine.
            return {"handled": True, "reason": "already paid (duplicate event)"}

        # The buyer was charged for an order that is no longer pending
        # (cancelled by an admin, or refunded). Its stock has already been
        # released, so a human has to refund or restore it.
        charged = f"{(amount or 0) / 100:.2f} {currency}"
        self.repo.log_action(
            "stripe-webhook", "system", "paid_after_cancel",
            f"order={order['order_number']} status={status} "
            f"amount={amount} session={session_obj['id']}",
        )
        self.repo.enqueue_notification(
            order["id"], "discord_admin", "store-admins",
            f"Payment received for {status} order {order['order_number']}",
            f"**{order['username']}** ({order['user_id']}) was charged {charged} "
            f"for an order that is **{status}**. Its stock was already released.\n"
            f"Refund the payment in Stripe, or restore the order manually.",
        )
        logger.error(
            f"PAYMENT FOR {status.upper()} ORDER {order['order_number']}: "
            f"charged {charged}, session {session_obj['id']} - needs manual action"
        )
        return {"handled": False, "reason": f"payment received for {status} order"}

    def _handle_expired(self, session_obj, account: str | None = None) -> dict:
        order = self._order_from_session(session_obj, account)
        if order is None or not self.repo.cancel_order(
            order["id"], from_statuses=("pending_payment",)
        ):
            return {"handled": False, "reason": "no pending order to expire"}

        self.repo.log_action(
            "stripe-webhook", "system", "checkout_expired",
            f"order={order['order_number']} restocked",
        )
        logger.info(f"Checkout expired, restocked: {order['order_number']}")
        return {"handled": True, "order_number": order["order_number"]}
