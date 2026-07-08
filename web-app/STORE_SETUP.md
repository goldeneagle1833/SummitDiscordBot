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

## Next phases

2. Stripe Checkout: checkout endpoint creating a session from a pending
   order, webhook route with signature verification calling `mark_paid`.
3. Admin order queue UI (React) + Discord bot notifications (admin channel
   ping on paid, buyer DM with tracking on shipped).
4. Google Maps Address Validation on the checkout address form.
5. PayPal, then crypto (NOWPayments or similar), reusing the same order flow.
