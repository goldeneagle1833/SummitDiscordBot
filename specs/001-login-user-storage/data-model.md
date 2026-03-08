# Data Model: Login User Storage

**Feature Branch**: `001-login-user-storage`
**Date**: 2026-03-07

## Entities

### UserProfile

Represents a user's stored login information, captured on authentication.

| Field           | Type      | Constraints                          | Description                                      |
|-----------------|-----------|--------------------------------------|--------------------------------------------------|
| user_id         | TEXT      | NOT NULL                             | Unique user identifier from the login provider   |
| provider        | TEXT      | NOT NULL, DEFAULT 'discord'          | Login provider name (e.g., "discord")            |
| display_name    | TEXT      | NOT NULL                             | User's display name at time of last login        |
| avatar          | TEXT      | NULLABLE                             | Avatar reference/hash (provider-specific format) |
| first_login_at  | TEXT      | NOT NULL                             | ISO 8601 timestamp of first login                |
| last_login_at   | TEXT      | NOT NULL                             | ISO 8601 timestamp of most recent login          |

**Primary Key**: Composite `(user_id, provider)`

**Uniqueness**: One record per user per login provider. The composite primary key enforces this constraint and prevents duplicate records (SC-005).

### Relationships

- **UserProfile → match_records**: A user profile's `user_id` corresponds to `winner_id` / `losser_id` in the `match_records` table. This is a logical relationship, not enforced by foreign keys (consistent with existing schema patterns in this project).
- **UserProfile → overall_standings (elo.db)**: A user profile's `user_id` corresponds to `user_id` in the `overall_standings` table in the separate ELO database. Cross-database, no foreign key.

### State Transitions

No state machine applies. The record is either:
1. **Created** (first login) - all fields populated, `first_login_at == last_login_at`
2. **Updated** (subsequent logins) - `display_name`, `avatar`, and `last_login_at` refreshed; `first_login_at` preserved

### Validation Rules

- `user_id` must be a non-empty string (Discord IDs are large integers stored as strings for compatibility)
- `provider` must be a non-empty string (defaults to "discord")
- `display_name` must be a non-empty string
- `avatar` may be null (Discord users without custom avatars)
- Timestamps must be valid ISO 8601 format (e.g., "2026-03-07T14:30:00")

## SQL Schema

```sql
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'discord',
    display_name TEXT NOT NULL,
    avatar TEXT,
    first_login_at TEXT NOT NULL,
    last_login_at TEXT NOT NULL,
    PRIMARY KEY (user_id, provider)
);
```

## Upsert Pattern

```sql
INSERT INTO user_profiles (user_id, provider, display_name, avatar, first_login_at, last_login_at)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT (user_id, provider)
DO UPDATE SET
    display_name = excluded.display_name,
    avatar = excluded.avatar,
    last_login_at = excluded.last_login_at;
```

This single statement handles both FR-003 (new record on first login) and FR-004 (update on returning login) atomically, while preserving `first_login_at` on updates.
