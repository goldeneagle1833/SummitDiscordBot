# API Contracts: Match Reporting Endpoints

**Feature**: 001-web-match-report-modal
**Base Path**: `/api/match-report`
**Authentication**: Required (Flask session from Discord OAuth)
**Date**: 2026-03-10

## Overview

RESTful API endpoints for web-based match reporting and confirmation system. All endpoints require authenticated Flask session.

---

## Endpoints Summary

| Method | Endpoint | Purpose | Auth Required |
|--------|----------|---------|---------------|
| GET | `/api/match-report/search-opponents` | Autocomplete opponent search | Yes |
| POST | `/api/match-report/submit` | Submit new match report | Yes |
| GET | `/api/match-report/pending` | Get user's pending confirmations | Yes |
| GET | `/api/match-report/confirmation/{id}` | Get specific confirmation details | Yes |
| POST | `/api/match-report/confirm/{id}` | Confirm opponent's report | Yes |
| POST | `/api/match-report/deny/{id}` | Deny opponent's report | Yes |

---

## 1. Search Opponents

**Endpoint**: `GET /api/match-report/search-opponents`

**Purpose**: Autocomplete search for opponents by display name or user ID, prioritizing recent match opponents.

**Authentication**: Required

**Query Parameters**:
```
q      string    required    Search query (display name or user ID)
limit  integer   optional    Max results (default: 10, max: 50)
```

**Request Example**:
```
GET /api/match-report/search-opponents?q=Player&limit=5
```

**Response** (200 OK):
```json
{
  "success": true,
  "opponents": [
    {
      "user_id": "123456789",
      "display_name": "PlayerOne",
      "avatar": "https://cdn.discordapp.com/avatars/123.../abc.png",
      "recent_match_count": 5,
      "last_matched_at": 1234567890,
      "is_recent": true
    },
    {
      "user_id": "987654321",
      "display_name": "PlayerTwo",
      "avatar": null,
      "recent_match_count": 0,
      "last_matched_at": null,
      "is_recent": false
    }
  ]
}
```

**Response Fields**:
- `user_id`: Discord user ID (string)
- `display_name`: User's display name from user_profiles
- `avatar`: URL to user's avatar (nullable)
- `recent_match_count`: Number of recent matches with this opponent (0 if never matched)
- `last_matched_at`: Unix timestamp of last match (nullable)
- `is_recent`: Boolean flag indicating if in top recent opponents

**Error Responses**:

```json
// 401 Unauthorized (not logged in)
{
  "success": false,
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Authentication required. Please log in."
  }
}

// 400 Bad Request (missing query)
{
  "success": false,
  "error": {
    "code": "MISSING_QUERY",
    "message": "Query parameter 'q' is required"
  }
}

// 400 Bad Request (query too short)
{
  "success": false,
  "error": {
    "code": "QUERY_TOO_SHORT",
    "message": "Query must be at least 2 characters"
  }
}
```

**Business Logic**:
1. Validate user is authenticated
2. Validate query parameter (min 2 chars)
3. Search recent opponents first (from match_records)
4. If <10 results, search user_profiles by display_name
5. Deduplicate and sort by recent_match_count DESC, then alphabetically
6. Exclude current user from results

---

## 2. Submit Match Report

**Endpoint**: `POST /api/match-report/submit`

**Purpose**: Create a new match report with pending confirmation status.

**Authentication**: Required

**Request Body**:
```json
{
  "opponent_user_id": "123456789",
  "result": "won",
  "went_first": "opponent",
  "submitter_deck_url": "https://curiosa.io/decks/abc123",
  "opponent_deck_url": "https://curiosa.io/decks/xyz789",
  "final_life_submitter": 12,
  "final_life_opponent": 0
}
```

**Field Specifications**:

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `opponent_user_id` | string | Yes | Must exist in user_profiles, != current user |
| `result` | string | Yes | Enum: "won" \| "lost" |
| `went_first` | string | Yes | Enum: "submitter" \| "opponent" |
| `submitter_deck_url` | string | No | Must match Curiosa.io URL pattern if provided |
| `opponent_deck_url` | string | No | Must match Curiosa.io URL pattern if provided |
| `final_life_submitter` | integer | Yes | Range: 0-99 |
| `final_life_opponent` | integer | Yes | Range: 0-99 |

**Response** (201 Created):
```json
{
  "success": true,
  "confirmation_id": 42,
  "expires_at": 1234567890,
  "opponent": {
    "user_id": "123456789",
    "display_name": "OpponentName"
  },
  "message": "Match report submitted. Awaiting confirmation from OpponentName."
}
```

**Error Responses**:

```json
// 400 Bad Request (validation error)
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input data",
    "details": {
      "opponent_user_id": "Opponent not found",
      "submitter_deck_url": "Invalid Curiosa.io deck URL format"
    }
  }
}

// 409 Conflict (duplicate pending report)
{
  "success": false,
  "error": {
    "code": "DUPLICATE_PENDING",
    "message": "You already have a pending match report with this opponent. Please wait for confirmation or expiration.",
    "details": {
      "existing_confirmation_id": 38,
      "expires_at": 1234567890
    }
  }
}

// 400 Bad Request (self-reporting)
{
  "success": false,
  "error": {
    "code": "SELF_REPORT_NOT_ALLOWED",
    "message": "Cannot report a match against yourself"
  }
}

// 500 Internal Server Error
{
  "success": false,
  "error": {
    "code": "DATABASE_ERROR",
    "message": "Failed to create match report. Please try again."
  }
}
```

**Business Logic**:
1. Validate all required fields and constraints
2. Check opponent exists in user_profiles
3. Check for duplicate pending reports (within 1 hour)
4. Calculate winner/loser based on result
5. Map deck URLs to winner/loser
6. Create match_confirmations record with status='pending'
7. Set created_at = now(), expires_at = now() + 48hr
8. Return confirmation ID and expiration time

---

## 3. Get Pending Confirmations

**Endpoint**: `GET /api/match-report/pending`

**Purpose**: Retrieve all pending match reports awaiting current user's confirmation.

**Authentication**: Required

**Query Parameters**: None

**Response** (200 OK):
```json
{
  "success": true,
  "pending_confirmations": [
    {
      "confirmation_id": 42,
      "submitter": {
        "user_id": "987654321",
        "display_name": "OpponentName",
        "avatar": "https://cdn.discordapp.com/avatars/..."
      },
      "reported_result": "loss",
      "went_first": "opponent",
      "submitter_deck_url": "https://curiosa.io/decks/abc",
      "opponent_deck_url": "https://curiosa.io/decks/xyz",
      "final_life_submitter": 0,
      "final_life_opponent": 15,
      "created_at": 1234567890,
      "expires_at": 1234567890,
      "time_remaining_seconds": 86400
    }
  ],
  "count": 1
}
```

**Response Fields**:
- `confirmation_id`: ID for confirm/deny actions
- `submitter`: User who submitted the report
- `reported_result`: "win" or "loss" from *your* perspective (opponent's opposite)
- `went_first`: Turn order ('submitter' means they went first, 'opponent' means you went first)
- `deck_urls`: Submitted deck URLs
- `final_life_*`: Final life totals as reported
- `created_at` / `expires_at`: Unix timestamps
- `time_remaining_seconds`: Seconds until expiration

**Error Responses**:

```json
// 401 Unauthorized
{
  "success": false,
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Authentication required"
  }
}
```

**Business Logic**:
1. Query match_confirmations WHERE opponent_discord_id = current_user
2. Filter status = 'pending' AND expires_at > now()
3. Join with user_profiles to get submitter display name/avatar
4. Calculate time_remaining_seconds
5. Transform result to opponent's perspective

---

## 4. Get Confirmation Details

**Endpoint**: `GET /api/match-report/confirmation/{id}`

**Purpose**: Retrieve detailed information about a specific confirmation request.

**Authentication**: Required

**Path Parameters**:
```
id    integer    required    Confirmation ID
```

**Response** (200 OK):
```json
{
  "success": true,
  "confirmation": {
    "confirmation_id": 42,
    "submitter": {
      "user_id": "987654321",
      "display_name": "PlayerOne",
      "avatar": "https://..."
    },
    "opponent": {
      "user_id": "123456789",
      "display_name": "PlayerTwo",
      "avatar": "https://..."
    },
    "winner": "submitter",
    "went_first": "opponent",
    "submitter_deck_url": "https://curiosa.io/decks/abc",
    "opponent_deck_url": "https://curiosa.io/decks/xyz",
    "final_life_winner": 18,
    "final_life_loser": 0,
    "status": "pending",
    "created_at": 1234567890,
    "expires_at": 1234567890,
    "time_remaining_seconds": 43200
  }
}
```

**Error Responses**:

```json
// 404 Not Found
{
  "success": false,
  "error": {
    "code": "CONFIRMATION_NOT_FOUND",
    "message": "Confirmation ID 42 not found"
  }
}

// 403 Forbidden (not authorized to view)
{
  "success": false,
  "error": {
    "code": "FORBIDDEN",
    "message": "You are not authorized to view this confirmation"
  }
}
```

**Business Logic**:
1. Query match_confirmations WHERE id = {id}
2. Verify current user is either submitter or opponent
3. Return full details with enriched user profiles

---

## 5. Confirm Match Report

**Endpoint**: `POST /api/match-report/confirm/{id}`

**Purpose**: Accept and finalize an opponent's match report, creating a match record and updating ELO.

**Authentication**: Required

**Path Parameters**:
```
id    integer    required    Confirmation ID to confirm
```

**Request Body**:
```json
{
  "confirmation_id": 42
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "message": "Match confirmed!",
  "match_id": 123,
  "elo_changes": {
    "winner": {
      "user_id": "987654321",
      "old_elo": 1500,
      "new_elo": 1516,
      "change": +16
    },
    "loser": {
      "user_id": "123456789",
      "old_elo": 1450,
      "new_elo": 1434,
      "change": -16
    }
  }
}
```

**Error Responses**:

```json
// 403 Forbidden (not the opponent)
{
  "success": false,
  "error": {
    "code": "FORBIDDEN",
    "message": "Only the opponent can confirm this report"
  }
}

// 404 Not Found
{
  "success": false,
  "error": {
    "code": "CONFIRMATION_NOT_FOUND",
    "message": "Confirmation not found or already processed"
  }
}

// 409 Conflict (already confirmed/expired)
{
  "success": false,
  "error": {
    "code": "ALREADY_PROCESSED",
    "message": "This confirmation has already been confirmed",
    "details": {
      "status": "confirmed",
      "confirmed_at": 1234567890
    }
  }
}

// 410 Gone (expired)
{
  "success": false,
  "error": {
    "code": "CONFIRMATION_EXPIRED",
    "message": "This confirmation has expired"
  }
}

// 500 Internal Server Error
{
  "success": false,
  "error": {
    "code": "FINALIZATION_ERROR",
    "message": "Failed to finalize match. ELO update rolled back."
  }
}
```

**Business Logic** (Atomic Transaction):
1. Validate confirmation exists and status = 'pending'
2. Verify current_user = opponent_discord_id
3. Verify not expired (expires_at > now())
4. BEGIN TRANSACTION
   - UPDATE match_confirmations SET status='confirmed', confirmed_at=now()
   - INSERT INTO match_records (winner_id, loser_id, ...)
   - Calculate ELO changes
   - UPDATE elo table for both players
   - COMMIT
5. Notify both players (async, non-blocking)
6. Return match ID and ELO changes

---

## 6. Deny Match Report

**Endpoint**: `POST /api/match-report/deny/{id}`

**Purpose**: Reject an opponent's match report. No match record or ELO changes occur.

**Authentication**: Required

**Path Parameters**:
```
id    integer    required    Confirmation ID to deny
```

**Request Body**:
```json
{
  "confirmation_id": 42,
  "reason": "Wrong result reported"
}
```

**Field Specifications**:

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `confirmation_id` | integer | Yes | Must match path parameter |
| `reason` | string | No | Max 500 characters |

**Response** (200 OK):
```json
{
  "success": true,
  "message": "Match report denied."
}
```

**Error Responses**:

```json
// 403 Forbidden
{
  "success": false,
  "error": {
    "code": "FORBIDDEN",
    "message": "Only the opponent can deny this report"
  }
}

// 404 Not Found
{
  "success": false,
  "error": {
    "code": "CONFIRMATION_NOT_FOUND",
    "message": "Confirmation not found"
  }
}

// 409 Conflict
{
  "success": false,
  "error": {
    "code": "ALREADY_PROCESSED",
    "message": "This confirmation has already been processed",
    "details": {
      "status": "disputed",
      "confirmed_at": 1234567890
    }
  }
}
```

**Business Logic**:
1. Validate confirmation exists
2. Verify current_user = opponent_discord_id
3. Verify status = 'pending' (not already processed)
4. UPDATE match_confirmations SET status='disputed', confirmed_at=now(), dispute_reason=?
5. Notify both players (submitter + opponent)
6. Return success message

---

## Authentication & Authorization

**Session Requirements**:
- All endpoints require valid Flask session with `user_id` set
- Sessions established via Discord OAuth (`/auth/discord/callback`)
- Session cookie: `session` (httpOnly, secure in production, sameSite=Lax)

**Authorization Checks**:

| Endpoint | Authorization Rule |
|----------|-------------------|
| `/submit` | User must be submitter (session user_id = submitter) |
| `/pending` | User sees only their own pending confirmations (opponent_discord_id = user_id) |
| `/confirmation/{id}` | User must be submitter OR opponent |
| `/confirm/{id}` | User must be opponent (opponent_discord_id = user_id) |
| `/deny/{id}` | User must be opponent (opponent_discord_id = user_id) |

**Unauthorized Response** (401):
```json
{
  "success": false,
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Authentication required. Redirecting to login...",
    "redirect_url": "/auth/discord"
  }
}
```

---

## Rate Limiting

**Recommended Limits** (per user):

| Endpoint | Limit | Window |
|----------|-------|--------|
| `/search-opponents` | 30 requests | 1 minute |
| `/submit` | 10 requests | 1 hour |
| `/pending` | 60 requests | 1 minute |
| `/confirm/{id}` | 20 requests | 1 minute |
| `/deny/{id}` | 20 requests | 1 minute |

**Rate Limit Response** (429 Too Many Requests):
```json
{
  "success": false,
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Too many requests. Please wait before trying again.",
    "retry_after": 45
  }
}
```

---

## CORS & Security Headers

**CORS Policy**:
- `Access-Control-Allow-Origin`: Same-origin only (no CORS needed for same domain)
- For future mobile app: Whitelist specific origins

**Security Headers**:
```
Content-Type: application/json
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Content-Security-Policy: default-src 'self'
```

**CSRF Protection**:
- Use Flask session SameSite=Lax cookies (CSRF protection built-in)
- Or: Require `X-CSRF-Token` header from custom endpoint (`GET /api/csrf-token`)

---

## Error Code Reference

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `UNAUTHORIZED` | 401 | Not authenticated |
| `FORBIDDEN` | 403 | Not authorized for this action |
| `CONFIRMATION_NOT_FOUND` | 404 | Confirmation ID doesn't exist |
| `VALIDATION_ERROR` | 400 | Invalid input data |
| `DUPLICATE_PENDING` | 409 | Pending report already exists |
| `SELF_REPORT_NOT_ALLOWED` | 400 | Can't report against self |
| `ALREADY_PROCESSED` | 409 | Confirmation already confirmed/denied |
| `CONFIRMATION_EXPIRED` | 410 | Confirmation past expiration time |
| `MISSING_QUERY` | 400 | Required query parameter missing |
| `QUERY_TOO_SHORT` | 400 | Search query too short (min 2 chars) |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `DATABASE_ERROR` | 500 | Database operation failed |
| `FINALIZATION_ERROR` | 500 | Match finalization failed (ELO update) |

---

## Testing Examples

### cURL Examples

**1. Search Opponents**:
```bash
curl -X GET 'http://localhost:5000/api/match-report/search-opponents?q=Player&limit=5' \
  -H 'Cookie: session=your_session_cookie_here'
```

**2. Submit Match Report**:
```bash
curl -X POST 'http://localhost:5000/api/match-report/submit' \
  -H 'Content-Type: application/json' \
  -H 'Cookie: session=your_session_cookie_here' \
  -d '{
    "opponent_user_id": "123456789",
    "result": "won",
    "went_first": "submitter",
    "submitter_deck_url": "https://curiosa.io/decks/test1",
    "opponent_deck_url": "https://curiosa.io/decks/test2",
    "final_life_submitter": 18,
    "final_life_opponent": 0
  }'
```

**3. Get Pending Confirmations**:
```bash
curl -X GET 'http://localhost:5000/api/match-report/pending' \
  -H 'Cookie: session=your_session_cookie_here'
```

**4. Confirm Match**:
```bash
curl -X POST 'http://localhost:5000/api/match-report/confirm/42' \
  -H 'Content-Type: application/json' \
  -H 'Cookie: session=your_session_cookie_here' \
  -d '{"confirmation_id": 42}'
```

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2026-03-10 | 1.0.0 | Initial API contract specification |

---

## Next Steps

- Implement route handlers in `web-app/routes/api/match_reporting.py`
- Implement service layer in `web-app/services/match_confirmation.py`
- Write integration tests for all endpoints
- Update frontend JavaScript to consume these APIs
