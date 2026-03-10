# API Contracts: Life Counter Endpoints

**Feature**: Mobile Life Counter with Match Reporting
**Branch**: `001-mobile-life-counter`
**Date**: 2026-03-09

This document defines all REST API endpoints for the life counter feature.

---

## Base URL

All endpoints are prefixed with `/api/life-counter` unless otherwise noted.

**Authentication**: All endpoints except SSE stream require Flask-Login authentication (user must be logged in via Discord OAuth).

---

## Endpoints

### 1. Submit Match Report

**POST** `/api/life-counter/match-report`

**Purpose**: Submit a completed match report and create pending confirmation request.

**Authentication**: Required (Flask-Login)

**Request Headers**:
```http
Content-Type: application/json
```

**Request Body**:
```json
{
  "opponent_identification": {
    "method": "discord_username" | "discord_id" | "lfg_lookup",
    "value": "Username#1234" | "123456789" | null
  },
  "match_result": {
    "winner": "self" | "opponent",
    "final_life": {
      "self": 15,
      "opponent": 0
    }
  },
  "decks": {
    "self_deck_url": "https://curiosa.io/decks/...",
    "opponent_deck_url": "https://curiosa.io/decks/..." | null
  }
}
```

**Request Body Fields**:
- `opponent_identification.method` (string, required): How opponent is identified
  - `"discord_username"`: Search by Discord username (e.g., "Username#1234")
  - `"discord_id"`: Direct Discord user ID (e.g., 123456789)
  - `"lfg_lookup"`: Auto-lookup from recent LFG matches (value can be null)
- `opponent_identification.value` (string | number | null): Depends on method
- `match_result.winner` (string, required): Who won ("self" or "opponent")
- `match_result.final_life.self` (integer, required): Your final life total
- `match_result.final_life.opponent` (integer, required): Opponent's final life total
- `decks.self_deck_url` (string, optional): Your deck URL from Curiosa.io
- `decks.opponent_deck_url` (string, optional): Opponent's deck URL if known

**Response** (Success - 201 Created):
```json
{
  "success": true,
  "message": "Match report submitted. Awaiting opponent confirmation.",
  "confirmation_id": 42,
  "expires_at": 1710086400,
  "opponent": {
    "discord_id": "123456789",
    "username": "OpponentName"
  }
}
```

**Response** (Error - 400 Bad Request):
```json
{
  "success": false,
  "error": "OPPONENT_NOT_FOUND",
  "message": "Could not find Discord user with username 'BadName#1234'"
}
```

**Response** (Error - 409 Conflict):
```json
{
  "success": false,
  "error": "DUPLICATE_REPORT",
  "message": "A pending match report already exists for this opponent within the last hour."
}
```

**Response** (Error - 401 Unauthorized):
```json
{
  "success": false,
  "error": "AUTHENTICATION_REQUIRED",
  "message": "You must be logged in to submit match reports."
}
```

**Validation Rules**:
- At least one player's final life must be ≤ 0 (someone must have lost)
- Winner and loser must be different users
- Opponent must be a valid Discord user in the system
- No duplicate pending confirmations for same opponent within 1 hour

**Side Effects**:
- Creates `match_confirmations` record with status='pending'
- Triggers SSE notification to opponent
- Sets expiration timestamp to 24 hours from now

---

### 2. Confirm Match Report

**POST** `/api/life-counter/confirm/{confirmation_id}`

**Purpose**: Opponent confirms a match report is accurate.

**Authentication**: Required (Flask-Login)

**Path Parameters**:
- `confirmation_id` (integer, required): ID of the match confirmation to confirm

**Request Headers**:
```http
Content-Type: application/json
```

**Request Body**:
```json
{
  "action": "confirm"
}
```

**Response** (Success - 200 OK):
```json
{
  "success": true,
  "message": "Match confirmed. ELO ratings updated.",
  "match_id": 1234,
  "elo_changes": {
    "winner": {
      "discord_id": "123456789",
      "old_elo": 1500,
      "new_elo": 1516,
      "change": +16
    },
    "loser": {
      "discord_id": "987654321",
      "old_elo": 1480,
      "new_elo": 1464,
      "change": -16
    }
  }
}
```

**Response** (Error - 403 Forbidden):
```json
{
  "success": false,
  "error": "NOT_AUTHORIZED",
  "message": "You are not the opponent for this match confirmation."
}
```

**Response** (Error - 404 Not Found):
```json
{
  "success": false,
  "error": "CONFIRMATION_NOT_FOUND",
  "message": "Match confirmation with ID 42 not found."
}
```

**Response** (Error - 410 Gone):
```json
{
  "success": false,
  "error": "ALREADY_PROCESSED",
  "message": "This match confirmation has already been confirmed."
}
```

**Validation Rules**:
- Requesting user must be the `opponent_discord_id` in the confirmation record
- Confirmation status must be 'pending'
- Confirmation must not be expired (though expired ones auto-confirm via cron)

**Side Effects**:
- Updates `match_confirmations.status` to 'confirmed'
- Sets `confirmed_at` timestamp
- Creates `match_records` entry
- Updates ELO ratings via existing ELO service
- Links `match_report_id` back to created match record

---

### 3. Dispute Match Report

**POST** `/api/life-counter/dispute/{confirmation_id}`

**Purpose**: Opponent disputes a match report as inaccurate.

**Authentication**: Required (Flask-Login)

**Path Parameters**:
- `confirmation_id` (integer, required): ID of the match confirmation to dispute

**Request Headers**:
```http
Content-Type: application/json
```

**Request Body**:
```json
{
  "action": "dispute",
  "reason": "The match result was incorrect. I actually won."
}
```

**Request Body Fields**:
- `action` (string, required): Must be "dispute"
- `reason` (string, optional): Free-text explanation for dispute (max 500 chars)

**Response** (Success - 200 OK):
```json
{
  "success": true,
  "message": "Match disputed. Flagged for admin review. No ELO changes will occur.",
  "confirmation_id": 42
}
```

**Response** (Error - 403 Forbidden):
```json
{
  "success": false,
  "error": "NOT_AUTHORIZED",
  "message": "You are not the opponent for this match confirmation."
}
```

**Response** (Error - 404 Not Found):
```json
{
  "success": false,
  "error": "CONFIRMATION_NOT_FOUND",
  "message": "Match confirmation with ID 42 not found."
}
```

**Response** (Error - 410 Gone):
```json
{
  "success": false,
  "error": "ALREADY_PROCESSED",
  "message": "This match confirmation has already been processed."
}
```

**Validation Rules**:
- Requesting user must be the `opponent_discord_id` in the confirmation record
- Confirmation status must be 'pending'
- Reason field max 500 characters if provided

**Side Effects**:
- Updates `match_confirmations.status` to 'disputed'
- Sets `confirmed_at` timestamp and stores `dispute_reason`
- Sends notification to admin Discord channel (via webhook)
- Does NOT update ELO ratings
- Does NOT create `match_records` entry

---

### 4. Get Pending Confirmations

**GET** `/api/life-counter/pending-confirmations`

**Purpose**: Retrieve all pending match confirmations for the current user.

**Authentication**: Required (Flask-Login)

**Request Headers**: None (standard GET)

**Query Parameters**: None

**Response** (Success - 200 OK):
```json
{
  "success": true,
  "count": 2,
  "confirmations": [
    {
      "confirmation_id": 42,
      "submitter": {
        "discord_id": "123456789",
        "username": "OpponentName"
      },
      "match_details": {
        "winner": "submitter",
        "final_life": {
          "submitter": 15,
          "you": 0
        },
        "decks": {
          "submitter_deck_url": "https://curiosa.io/decks/...",
          "your_deck_url": null
        }
      },
      "created_at": 1709999999,
      "expires_at": 1710086400,
      "time_remaining_seconds": 86400
    },
    {
      "confirmation_id": 43,
      "submitter": {
        "discord_id": "987654321",
        "username": "AnotherPlayer"
      },
      "match_details": {
        "winner": "you",
        "final_life": {
          "you": 3,
          "submitter": 0
        },
        "decks": {
          "your_deck_url": "https://curiosa.io/decks/...",
          "submitter_deck_url": "https://curiosa.io/decks/..."
        }
      },
      "created_at": 1709989999,
      "expires_at": 1710076400,
      "time_remaining_seconds": 76400
    }
  ]
}
```

**Response** (Success - No Pending - 200 OK):
```json
{
  "success": true,
  "count": 0,
  "confirmations": []
}
```

**Response** (Error - 401 Unauthorized):
```json
{
  "success": false,
  "error": "AUTHENTICATION_REQUIRED",
  "message": "You must be logged in to view pending confirmations."
}
```

**Validation Rules**: None (just returns current user's pending confirmations)

**Side Effects**: None (read-only operation)

---

### 5. Get LFG Recent Opponents

**GET** `/api/life-counter/lfg-opponents`

**Purpose**: Retrieve list of recent LFG opponents for auto-fill in match report form.

**Authentication**: Required (Flask-Login)

**Request Headers**: None (standard GET)

**Query Parameters**:
- `limit` (integer, optional): Max number of opponents to return (default 5, max 20)

**Response** (Success - 200 OK):
```json
{
  "success": true,
  "opponents": [
    {
      "discord_id": "123456789",
      "username": "RecentOpponent",
      "last_matched_at": 1709999999,
      "match_count": 3
    },
    {
      "discord_id": "987654321",
      "username": "AnotherRecent",
      "last_matched_at": 1709989999,
      "match_count": 1
    }
  ]
}
```

**Response** (Success - No Recent Matches - 200 OK):
```json
{
  "success": true,
  "opponents": []
}
```

**Response** (Error - 401 Unauthorized):
```json
{
  "success": false,
  "error": "AUTHENTICATION_REQUIRED",
  "message": "You must be logged in to view LFG opponents."
}
```

**Validation Rules**:
- Limit must be between 1 and 20
- Only returns opponents from last 30 days

**Side Effects**: None (read-only operation)

**Query Logic**:
- Look up user's recent matches from `match_records` where user is winner or loser
- Extract opponent Discord IDs
- Fetch opponent usernames from Discord user cache
- Sort by most recent match first
- Limit to specified count

---

## Error Handling

### Standard Error Response Format

All error responses follow this structure:

```json
{
  "success": false,
  "error": "ERROR_CODE",
  "message": "Human-readable error message",
  "details": {} // Optional additional context
}
```

### Error Codes

| Code | HTTP Status | Meaning |
|------|-------------|---------|
| `AUTHENTICATION_REQUIRED` | 401 | User not logged in |
| `NOT_AUTHORIZED` | 403 | User lacks permission for action |
| `OPPONENT_NOT_FOUND` | 400 | Could not identify opponent |
| `DUPLICATE_REPORT` | 409 | Pending report already exists |
| `CONFIRMATION_NOT_FOUND` | 404 | Invalid confirmation ID |
| `ALREADY_PROCESSED` | 410 | Confirmation already confirmed/disputed |
| `INVALID_REQUEST` | 400 | Malformed request body |
| `SERVER_ERROR` | 500 | Unexpected server error |

---

## Rate Limiting

**Not implemented in MVP**, but recommended for production:

- Match report submission: 10 requests per hour per user
- Confirmation actions: 50 requests per hour per user
- Pending confirmations check: 100 requests per hour per user

---

## CORS Policy

All API endpoints return standard CORS headers:

```http
Access-Control-Allow-Origin: https://sorcererssummit.com
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type
Access-Control-Allow-Credentials: true
```

---

## Next Steps

- ✅ API contracts defined for 5 endpoints
- ⬜ Define SSE notification contract in `notifications.md`
- ⬜ Create quickstart guide in `quickstart.md`
