# Discord Monetization Purchase Tracking

## Overview

This system tracks real money purchases made through Discord's built-in monetization features (subscriptions, server products, premium roles, etc.). All purchases are automatically logged to a database for administrative review.

## Features

### Automatic Purchase Tracking

The bot automatically tracks the following events:

- **New Purchases**: When someone buys a subscription or one-time product
- **Renewals**: When a subscription is renewed
- **Updates**: When an entitlement is modified
- **Cancellations**: When a subscription is cancelled or refunded

### Database Storage

All purchases are stored in `discord_purchases.db` with the following information:

- User ID and username
- Purchase type (subscription, one_time_purchase, renewal)
- Product information (SKU ID and name)
- Entitlement and subscription IDs
- Purchase date and expiration date
- Active status
- Additional notes

## Admin Commands

### View Purchase History

```
!purchase_history [@user] [limit]
```

View purchase records with optional filtering.

**Examples:**

- `!purchase_history` - Shows last 20 purchases from all users
- `!purchase_history @User` - Shows last 20 purchases from a specific user
- `!purchase_history @User 50` - Shows last 50 purchases from a specific user
- `!purchase_history 50` - Shows last 50 purchases from all users

**Permissions Required:** Administrator

**Output Includes:**

- User information
- Purchase type and product name
- Active/Inactive status
- Purchase and expiration dates
- Subscription IDs (for subscriptions)
- Notes about the purchase

### View Purchase Statistics

```
!purchase_stats
```

View aggregated statistics about all purchases.

**Permissions Required:** Administrator

**Output Includes:**

- Total purchases and active purchases
- Number of unique buyers
- Breakdown by purchase type
- Top 5 most popular products
- Top 5 buyers by purchase count

## Setup Requirements

### Discord Developer Portal

To use Discord monetization features, you need to:

1. **Enable Monetization** in your server:

   - Go to Server Settings → Monetization
   - Complete the application process
   - Set up your payment information

2. **Create Products/Subscriptions**:

   - Navigate to Server Settings → Server Subscriptions
   - Create subscription tiers or one-time products
   - Set pricing and benefits
   - Note the SKU IDs for your products

3. **Bot Permissions**:
   - The bot automatically receives entitlement events
   - No special intents required for basic tracking
   - Administrator permission required to use tracking commands

### Product Name Mapping (Optional)

By default, products are displayed as "SKU\_[ID]". To show friendly names, you can modify the `on_entitlement_create` method in `shop.py` to map SKU IDs to names:

```python
# Example mapping
sku_names = {
    "1234567890": "Premium Member",
    "0987654321": "Supporter Pack",
    "1111111111": "VIP Access"
}
sku_name = sku_names.get(sku_id, f"SKU_{sku_id}")
```

## Events Tracked

### on_entitlement_create

Triggered when:

- User purchases a subscription
- User purchases a one-time product
- User is granted an entitlement manually

### on_entitlement_update

Triggered when:

- Subscription is renewed
- Entitlement is modified
- Expiration date changes

### on_entitlement_delete

Triggered when:

- Subscription is cancelled
- Purchase is refunded
- Entitlement is manually revoked

## Database Schema

```sql
CREATE TABLE purchase_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    user_discriminator TEXT,
    purchase_type TEXT NOT NULL,
    sku_id TEXT,
    sku_name TEXT,
    entitlement_id TEXT,
    subscription_id TEXT,
    guild_id INTEGER,
    purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    is_active BOOLEAN DEFAULT 1,
    notes TEXT
)
```

## Usage Examples

### Check Recent Purchases

```
!purchase_history
```

Output: Shows the last 20 purchases from all users with full details

### Check Specific User's Purchases

```
!purchase_history @JohnDoe
```

Output: Shows all purchases made by JohnDoe

### View Server Stats

```
!purchase_stats
```

Output:

- Total Purchases: 45
- Active: 32
- Unique Buyers: 15
- Top Products and Buyers

## Privacy and Data Management

### Data Retention

- All purchase records are kept indefinitely
- Cancelled/refunded purchases are marked as inactive but not deleted
- This allows for historical analysis and dispute resolution

### GDPR Considerations

- Store only necessary purchase information
- Implement data deletion procedures if required
- Inform users about data collection in your privacy policy

### Manual Data Management

You can access the database directly for advanced queries:

```python
import sqlite3
conn = sqlite3.connect("discord_purchases.db")
cur = conn.cursor()
# Your queries here
```

## Troubleshooting

### Purchases Not Being Tracked

1. Verify monetization is enabled in your server
2. Check that the bot has proper permissions
3. Review bot logs for error messages
4. Ensure the ShopCog is loaded in main.py

### Missing Product Names

- Update the SKU ID to name mapping in the code
- Check Discord Developer Portal for correct SKU IDs

### Database Errors

- Verify write permissions for the bot directory
- Check if discord_purchases.db exists and is accessible
- Review logs for specific SQL errors

## Future Enhancements

Potential additions:

- Export purchase data to CSV
- Email notifications for purchases
- Revenue tracking and reporting
- Webhook integration for purchase alerts
- User-facing purchase history command
- Automated role assignment based on purchases

## Support

For issues or questions:

1. Check the bot logs in `bot.log`
2. Verify your Discord server monetization setup
3. Review the entitlement events in Discord's developer dashboard
4. Contact the bot administrator
