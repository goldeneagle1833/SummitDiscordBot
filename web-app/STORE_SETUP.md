# Summit Store — Phase 1 Setup

Foundation for the token-card store: dedicated `store.db`, store-admin
permission tier, product management API, order queue API, and backups.

## File placement

| File in this bundle | Goes to |
|---|---|
| `repositories/store.py` | `web-app/repositories/store.py` |
| `utils/store_auth.py` | `web-app/utils/store_auth.py` |
| `routes/store.py` | `web-app/routes/api/store.py` |
| `scripts/backup_store_db.py` | `web-app/scripts/backup_store_db.py` |

## Blueprint registration

Already wired into `web-app/routes/api/__init__.py` in this branch.

## Environment variables

Add to `discord-bot/.env` (shared config):

```env
# Discord IDs allowed into the store admin section.
# Deliberately separate from ADMIN_IDS — global admins do NOT get store access.
STORE_ADMIN_IDS=123456789012345678

# Optional override; defaults to web-app/store.db
# STORE_DB_PATH=/var/data/store.db
```

## API summary

Public:
- `GET /api/store/products` — active products only

Store admin (`STORE_ADMIN_IDS`, localhost, or API key):
- `GET  /api/store/admin/products` — includes inactive
- `POST /api/store/admin/products` — `{sku, name, price_cents, description?, image_url?, stock_quantity?}`
- `PATCH /api/store/admin/products/<id>` — partial update
- `POST /api/store/admin/products/<id>/deactivate` — soft delete
- `GET  /api/store/admin/orders?status=paid` — order queue
- `GET  /api/store/admin/orders/<id>` — order with items + shipping address
- `POST /api/store/admin/orders/<id>/ship` — `{tracking_number, tracking_carrier?}`
- `POST /api/store/admin/orders/<id>/status` — `{status}`; cancelling restocks items
- `GET  /api/store/admin/audit` — who did what
- `GET  /api/store/admin/backup` — downloads a live-safe snapshot of store.db

## Backups

Two layers:

1. **Server-side rotation (cron):**
   ```
   15 2 * * * cd /path/to/web-app && /usr/bin/python3 scripts/backup_store_db.py
   ```
   Keeps 14 daily snapshots in `web-app/backups/store/` (integrity-checked).

2. **To your local machine:** either click the backup download endpoint from
   the admin UI, or schedule from your local machine:
   ```
   rsync -avz user@server:/path/to/web-app/backups/store/ ~/SummitBackups/store/
   ```

Make sure `backups/` and `store.db` are in `.gitignore` — order records
contain customer shipping addresses and must never be committed.

## Design notes

- **Prices are integer cents.** Never floats — floating point money is how
  you end up owing someone $0.000001.
- **Order items snapshot product name and price** at purchase time, so
  editing a product later never rewrites order history.
- **`mark_paid` is idempotent** (only transitions `pending_payment -> paid`),
  which matters because payment webhooks can and do fire twice.
- **Stock is decremented at order creation** inside a transaction and
  restored on cancellation, preventing overselling during checkout races.
- **Products are soft-deleted** (`is_active = 0`) because order rows
  reference them.

## Phase 2: Stripe checkout (included)

New endpoints:
- `POST /api/store/checkout` (logged-in) — body `{items, shipping_address, email?}`;
  creates a pending order (stock reserved), returns `{order_number, checkout_url}`.
  Redirect the buyer to `checkout_url`.
- `GET  /api/store/orders/mine` (logged-in) — buyer's own order history.
- `POST /api/store/webhooks/stripe` — signature-verified; the ONLY code path
  that marks an order paid. Never trust the success redirect page as payment
  proof. Verifies amount + currency against the order; mismatches are audited
  and left for manual review instead of auto-fulfilled. Expired sessions
  cancel the order and restock.

Setup:
1. `pip install -r requirements.txt` (adds `stripe`)
2. Set `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` in `.env`
3. In the Stripe dashboard, add a webhook endpoint pointing to
   `https://yourdomain.com/api/store/webhooks/stripe` listening for
   `checkout.session.completed` and `checkout.session.expired`.
4. Local testing without a public URL: `stripe listen --forward-to
   localhost:5000/api/store/webhooks/stripe` (Stripe CLI prints the
   `whsec_...` secret to use). Card `4242 4242 4242 4242` completes test
   payments.

Notes:
- Prices are always read from the database; the client only sends product
  IDs and quantities.
- Shipping is a flat rate via `STORE_FLAT_SHIPPING_CENTS` for now.
- Tax is 0 for now — revisit with Stripe Tax once volume justifies it.

## Phase 3a: Notifications + checkout prefill (included)

Routing when an order is paid or shipped:
- Admin channel ping — always (set `STORE_ORDERS_CHANNEL_ID` in bot config)
- Buyer logged in with **Discord** — bot DM (plus email if given at checkout,
  since DMs can be closed)
- Buyer logged in with **Google** — email via SMTP

How it works: the web app writes rows to a `notifications` outbox table in
store.db; the bot's `StoreNotificationsCog` polls every 30s and delivers
Discord messages; the web app sends email inline with failed sends left
pending (retry via `StoreNotificationService.retry_pending_emails()`).
Delivery attempts cap at 5, then the row is marked failed with the error
recorded — visible via the audit/admin endpoints.

`GET /api/store/checkout/prefill` (logged-in) returns `{username,
auth_provider, name, email, address}` for pre-populating the checkout form:
Google users get name/email from their profile, and repeat buyers of either
provider get their most recent shipping address.

SMTP setup is in `.env.example`. Without SMTP configured, email rows are
marked failed with a clear error, and Discord users are unaffected.

## Next phases

3b. React store + admin UI (product management, order queue, checkout form).
4. Admin order queue UI (React) + Discord bot notifications (admin channel
   ping on paid, buyer DM with tracking on shipped).
4. Google Maps Address Validation on the checkout address form.
5. PayPal, then crypto (NOWPayments or similar), reusing the same order flow.
