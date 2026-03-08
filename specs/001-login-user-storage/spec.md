# Feature Specification: Login User Storage

**Feature Branch**: `001-login-user-storage`
**Created**: 2026-03-07
**Status**: Draft
**Input**: User description: "When the user logs in with Discord auth or any login in the future, add their info to a new table in the match records db so we can use it in the future"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - First-Time Login Captures User Profile (Priority: P1)

A new visitor arrives at the Summit web application and clicks "Login with Discord." After completing the Discord authorization flow, the system automatically saves their profile information (user ID, username, avatar, and login timestamp) to a dedicated user profiles table in the match records database. The user proceeds to browse the site normally, unaware that their info has been persisted behind the scenes for future use.

**Why this priority**: This is the core functionality of the feature. Without capturing user data on first login, no other user profile features can exist. It establishes the foundation for all future user-related features.

**Independent Test**: Can be fully tested by logging in via Discord OAuth and verifying a new record exists in the user profiles table with the correct user ID, username, avatar, and timestamps.

**Acceptance Scenarios**:

1. **Given** a user has never logged in before, **When** they complete Discord OAuth login, **Then** a new record is created in the user profiles table containing their Discord user ID, username, avatar reference, login provider, first login time, and last login time.
2. **Given** a user has never logged in before, **When** they complete login, **Then** their browsing session continues without interruption or delay.

---

### User Story 2 - Returning User Updates Profile on Login (Priority: P1)

A returning user logs in again via Discord. The system recognizes their existing record by user ID and updates their profile with any changed information (e.g., new username, new avatar) and refreshes the "last login" timestamp. No duplicate records are created.

**Why this priority**: Equally critical to first-time capture. Users change their Discord usernames and avatars frequently. Keeping stored data current ensures accuracy for any feature that relies on this table.

**Independent Test**: Can be fully tested by logging in, changing the Discord username, logging in again, and verifying the record was updated (not duplicated) with the new username and a refreshed last-login timestamp.

**Acceptance Scenarios**:

1. **Given** a user has logged in before and their record exists, **When** they log in again, **Then** their existing record is updated with current username, avatar, and last login timestamp.
2. **Given** a user has logged in before and changed their Discord username, **When** they log in again, **Then** the stored username reflects the new value.
3. **Given** a user has logged in before, **When** they log in again, **Then** no duplicate record is created.

---

### User Story 3 - Support for Future Login Providers (Priority: P2)

The user profiles table is designed to accommodate multiple login providers beyond Discord. When a future login method is added (e.g., email/password, Google OAuth), user information from that provider is stored in the same table with a provider identifier. If the same person logs in with a different provider, they receive a separate record (account linking is out of scope for this feature).

**Why this priority**: The user explicitly requested support for future login methods. Designing the storage schema to be provider-aware from the start avoids costly migrations later. However, only Discord login needs to work now.

**Independent Test**: Can be tested by verifying the user profiles table schema includes a login provider field, and that inserting a record with a non-Discord provider value succeeds.

**Acceptance Scenarios**:

1. **Given** the user profiles table exists, **When** a record is created, **Then** it includes a login provider identifier distinguishing which authentication method was used.
2. **Given** a user logged in via Discord, **When** a future provider login creates a record with a different provider, **Then** both records coexist without conflict.

---

### Edge Cases

- What happens when the Discord API returns incomplete user data (e.g., missing avatar)? The system stores whatever fields are available and leaves optional fields empty.
- What happens if the database write fails during login? The user's login session proceeds normally; the profile save failure is logged but does not block the user experience.
- What happens if two login requests arrive simultaneously for the same user? The system handles concurrent writes gracefully, resulting in a single up-to-date record without errors.
- What happens when a user logs out? No changes to the user profiles table; the record persists for future reference.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST create a dedicated user profiles table in the match records database to store login user information.
- **FR-002**: System MUST capture and store the following user data on login: unique user identifier, display name, avatar reference, login provider name, first login timestamp, and last login timestamp.
- **FR-003**: System MUST create a new record when a user logs in for the first time (no existing record for that user ID and provider combination).
- **FR-004**: System MUST update the existing record (display name, avatar, last login timestamp) when a returning user logs in, rather than creating a duplicate.
- **FR-005**: System MUST include a login provider field in each record to distinguish between authentication methods (e.g., "discord" for the current OAuth flow).
- **FR-006**: System MUST NOT disrupt the user's login experience if the profile storage operation fails; failures should be logged silently.
- **FR-007**: System MUST automatically create the user profiles table if it does not yet exist (first-run initialization).

### Key Entities

- **User Profile**: Represents a user's stored login information. Key attributes: unique user identifier (from the login provider), display name, avatar reference, login provider name, first login timestamp, last login timestamp.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of successful logins result in a user profile record being created or updated in the database.
- **SC-002**: Login flow completion time remains unchanged (within 500ms of current performance) after adding profile storage.
- **SC-003**: Returning users' records reflect their most recent display name and avatar within one login cycle.
- **SC-004**: The user profiles table supports at least 10,000 user records without degradation in login performance.
- **SC-005**: Zero duplicate records exist for the same user ID and login provider combination.

## Assumptions

- The match records database is the appropriate location for this table, as specified by the user.
- Only Discord OAuth login exists today; future login providers will be integrated separately but this feature prepares the schema for them.
- The "identify" OAuth scope (currently in use) provides sufficient user data (user ID, username, avatar) for profile storage. No additional OAuth scopes are needed.
- Avatar storage is a reference/hash string, not the actual image binary.
- Account linking across providers (e.g., merging a Discord login and a future Google login into one profile) is out of scope for this feature.
- The user profiles table is for the web application login flow only; Discord bot interactions do not trigger profile storage.

## Scope Boundaries

### In Scope

- Creating a new user profiles table in the match records database
- Storing user info (ID, display name, avatar, provider, timestamps) on Discord OAuth login
- Updating existing records on subsequent logins
- Designing the table schema to accommodate future login providers

### Out of Scope

- Implementing any new login providers (only Discord OAuth exists today)
- Account linking or merging across different login providers
- User-facing profile pages or profile editing capabilities
- Exposing stored user data through new web pages or dashboard views
- Migrating existing user data from other tables (e.g., ELO standings) into the new table
- Adding new OAuth scopes to capture additional user data (e.g., email)

## Dependencies

- Existing Discord OAuth login flow in the web application must be functional
- Match records database must be accessible from the web application
