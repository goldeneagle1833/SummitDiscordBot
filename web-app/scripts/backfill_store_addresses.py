#!/usr/bin/env python3
"""Backfill shipping addresses for store orders that lost them.

Before the webhook handler learned about ``collected_information`` (Stripe
API versions >= 2025-03-31), paid orders were saved without the address the
buyer entered on Stripe Checkout. The address is still on the Checkout
Session in Stripe, so this pulls it back for every order that has a Stripe
session id but no street line.

Reads STRIPE_SECRET_KEY from the shared discord-bot/.env like the web app.
Sessions created under a different key (test-mode orders once the live key
is in place) can't be fetched and are reported, not changed.

Usage (from web-app/, inside the venv):
    python scripts/backfill_store_addresses.py            # dry run, prints what it would set
    python scripts/backfill_store_addresses.py --apply    # write the addresses
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import webapp_config  # noqa: E402,F401  (loads discord-bot/.env)
import stripe  # noqa: E402

from repositories.store import StoreRepository  # noqa: E402
from services.store_checkout import (  # noqa: E402
    STRIPE_SECRET_KEY,
    shipping_address_from_session,
)


def orders_missing_address(repo: StoreRepository) -> list[dict]:
    with repo._connect() as conn:
        rows = conn.execute(
            """SELECT id, order_number, payment_ref FROM orders
               WHERE payment_provider = 'stripe'
                 AND payment_ref IS NOT NULL AND payment_ref != ''
                 AND (ship_line1 IS NULL OR ship_line1 = '')
                 AND status IN ('paid', 'shipped', 'delivered')
               ORDER BY created_at"""
        ).fetchall()
    return [dict(r) for r in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill store order addresses from Stripe")
    parser.add_argument("--apply", action="store_true", help="write changes (default is dry run)")
    args = parser.parse_args()

    if not STRIPE_SECRET_KEY:
        print("STRIPE_SECRET_KEY is not set; nothing to do", file=sys.stderr)
        return 1
    stripe.api_key = STRIPE_SECRET_KEY

    repo = StoreRepository()
    rows = orders_missing_address(repo)
    if not rows:
        print("No orders need a backfill.")
        return 0

    updated = missing = failed = 0
    for row in rows:
        order_id, order_number, session_id = row["id"], row["order_number"], row["payment_ref"]
        try:
            session = stripe.checkout.Session.retrieve(session_id)
        except stripe.StripeError as e:
            failed += 1
            print(f"{order_number}: could not fetch {session_id}: {getattr(e, 'user_message', None) or e}")
            continue

        address = shipping_address_from_session(session.to_dict_recursive())
        if not address:
            missing += 1
            print(f"{order_number}: Stripe has no shipping address on {session_id}")
            continue

        summary = (
            f"{address['name']}, {address['line1']}, "
            f"{address['city']} {address['state']} {address['postal']} {address['country']}"
        )
        if args.apply:
            repo.update_shipping_address(order_id, address)
            repo.log_action(
                "backfill-script", "system", "address_backfilled", f"order={order_number}"
            )
            print(f"{order_number}: set -> {summary}")
        else:
            print(f"{order_number}: would set -> {summary}")
        updated += 1

    mode = "updated" if args.apply else "would update"
    print(f"\n{mode}: {updated}, no address in Stripe: {missing}, fetch failed: {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
