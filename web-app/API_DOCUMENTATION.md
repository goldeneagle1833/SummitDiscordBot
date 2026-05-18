# Summit Discord Bot - Match Reporting API

This document describes how to use the Match Reporting API to submit match results from external applications.

## Base URL

```
https://sorcererssummit.com
```

For local development:

```
http://localhost:5000
```

## Authentication

All API endpoints require authentication using an API key. The API key must be included in the request headers.

### Header Format

**Option 1: X-API-Key Header**

```
X-API-Key: your_api_key_here
```

**Option 2: Bearer Token**

```
Authorization: Bearer your_api_key_here
```

### Getting an API Key

Contact your server administrator to obtain an API key. The API key is configured in the server's environment variables.

## Endpoints

### 1. Health Check

Check if the API server is running.

**Endpoint:** `GET /api/status`

**Authentication:** Not required

**Response:**

```json
{
  "status": "online",
  "message": "Summit Web App is running!"
}
```

---

### 2. Report Match Result

Submit a match result between two players. This endpoint will:

- Record the match in the database
- Update ELO ratings for both players
- Optionally scrape and store deck data from Curiosa URLs

**Endpoint:** `POST /api/report-match`

**Authentication:** Required

**Content-Type:** `application/json`

#### Request Body

##### Required Fields

| Field         | Type    | Description                        |
| ------------- | ------- | ---------------------------------- |
| `winner_name` | string  | Display name of the winning player |
| `winner_id`   | integer | Discord user ID of the winner      |
| `loser_name`  | string  | Display name of the losing player  |
| `loser_id`    | integer | Discord user ID of the loser       |

##### Optional Fields

| Field             | Type    | Default             | Description                                                           |
| ----------------- | ------- | ------------------- | --------------------------------------------------------------------- |
| `first_player`    | string  | `"n"`               | Who went first: `"y"` (winner went first) or `"n"` (loser went first) |
| `match_time`      | integer | `0`                 | Duration of the match in minutes                                      |
| `winner_deck_url` | string  | `"No URL provided"` | URL to winner's deck on Curiosa.io                                    |
| `loser_deck_url`  | string  | `"No URL provided"` | URL to loser's deck on Curiosa.io                                     |
| `match_comment`   | string  | `""`                | Additional notes or comments about the match                          |
| `reporter_id`     | integer | `winner_id`         | Discord user ID of the person reporting the match                     |

#### Example Request

```bash
curl -X POST https://sorcererssummit.com/api/report-match \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key_here" \
  -d '{
    "winner_name": "PlayerOne",
    "winner_id": 123456789,
    "loser_name": "PlayerTwo",
    "loser_id": 987654321,
    "first_player": "y",
    "match_time": 25,
    "winner_deck_url": "https://curiosa.io/decks/abc123",
    "loser_deck_url": "https://curiosa.io/decks/xyz789",
    "match_comment": "Great game! Close match."
  }'
```

#### Success Response

**Status Code:** `201 Created`

```json
{
  "success": true,
  "match_id": 1234,
  "winner": {
    "name": "PlayerOne",
    "id": 123456789,
    "elo": 1532,
    "elo_change": 16
  },
  "loser": {
    "name": "PlayerTwo",
    "id": 987654321,
    "elo": 1484,
    "elo_change": -16
  }
}
```

#### Error Responses

**Missing Required Fields (400 Bad Request)**

```json
{
  "error": "Missing required fields",
  "missing": ["winner_id", "loser_name"]
}
```

**Invalid Data Type (400 Bad Request)**

```json
{
  "error": "Invalid data type",
  "detail": "invalid literal for int() with base 10: 'abc'"
}
```

**Invalid first_player Value (400 Bad Request)**

```json
{
  "error": "Invalid value for first_player",
  "detail": "Must be 'y' or 'n'"
}
```

**Authentication Error (401 Unauthorized)**

```json
{
  "error": "Invalid or missing API key"
}
```

**Server Error (500 Internal Server Error)**

```json
{
  "error": "Failed to report match",
  "detail": "Database connection failed"
}
```

---

### 3. Get Match Data by Date Range

Retrieve all ranked match results between two dates (inclusive). Returns winner/loser names, ELO changes, match duration, and timestamps.

**Endpoint:** `GET /api/matches/date-range`

**Authentication:** Required

#### Query Parameters

| Parameter    | Required | Format       | Description                      |
| ------------ | -------- | ------------ | -------------------------------- |
| `start_date` | Yes      | `YYYY-MM-DD` | Start of date range (inclusive)  |
| `end_date`   | Yes      | `YYYY-MM-DD` | End of date range (inclusive)    |

#### Example Request

```bash
curl -H "X-API-Key: your_api_key_here" \
  "https://sorcererssummit.com/api/matches/date-range?start_date=2026-05-01&end_date=2026-05-15"
```

#### Success Response

**Status Code:** `200 OK`

```json
{
  "start_date": "2026-05-01",
  "end_date": "2026-05-15",
  "total_matches": 2,
  "matches": [
    {
      "match_id": 1542,
      "winner": "PlayerOne",
      "winner_elo_change": 16,
      "loser": "PlayerTwo",
      "loser_elo_change": -16,
      "match_time": 1823,
      "timestamp": "2026-05-14 19:32:05",
      "winner_id": "123456789012345678",
      "loser_id": "987654321098765432",
      "winner_deck": {
        "avatar": "Fen Cleric",
        "spellbook": ["Card A", "Card B"],
        "atlas": ["Land A", "Land B"]
      },
      "loser_deck": {
        "avatar": "Storm Mage",
        "spellbook": ["Card C", "Card D"],
        "atlas": ["Land C", "Land D"]
      }
    },
    {
      "match_id": 1541,
      "winner": "PlayerThree",
      "winner_elo_change": 12,
      "loser": "PlayerOne",
      "loser_elo_change": -12,
      "match_time": 2105,
      "timestamp": "2026-05-13 15:10:22",
      "winner_id": "111222333444555666",
      "loser_id": "123456789012345678",
      "winner_deck": null,
      "loser_deck": null
    }
  ]
}
```

#### Response Fields

| Field              | Type        | Description                                      |
| ------------------ | ----------- | ------------------------------------------------ |
| `match_id`         | int         | Unique match identifier                          |
| `winner`           | string      | Winner's display name                            |
| `winner_elo_change`| int         | ELO points gained by winner                      |
| `loser`            | string      | Loser's display name                             |
| `loser_elo_change` | int         | ELO points lost by loser (negative)              |
| `match_time`       | int         | Match duration in seconds (0 if unknown)         |
| `timestamp`        | string      | When the match was played (UTC)                  |
| `winner_id`        | string      | Winner's Discord user ID                         |
| `loser_id`         | string      | Loser's Discord user ID                          |
| `winner_deck`      | object/null | Winner's deck contents (null if not available)   |
| `loser_deck`       | object/null | Loser's deck contents (null if not available)    |

#### Error Responses

| Status | Body |
| ------ | ---- |
| 400    | `{"error": "start_date and end_date query params are required"}` |
| 400    | `{"error": "Dates must be in YYYY-MM-DD format"}` |
| 400    | `{"error": "start_date must be before or equal to end_date"}` |
| 401    | `{"error": "Invalid or missing API key"}` |

---

## Code Examples

### Python

```python
import requests

API_URL = "https://sorcererssummit.com/api/report-match"
API_KEY = "your_api_key_here"

headers = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY
}

match_data = {
    "winner_name": "Alice",
    "winner_id": 111111111,
    "loser_name": "Bob",
    "loser_id": 222222222,
    "first_player": "y",
    "match_time": 30,
    "winner_deck_url": "https://curiosa.io/decks/alice-deck",
    "loser_deck_url": "https://curiosa.io/decks/bob-deck",
    "match_comment": "Tournament semifinal match"
}

response = requests.post(API_URL, json=match_data, headers=headers)

if response.status_code == 201:
    result = response.json()
    print(f"Match recorded successfully! Match ID: {result['match_id']}")
    print(f"Winner ELO: {result['winner']['elo']} ({result['winner']['elo_change']:+d})")
    print(f"Loser ELO: {result['loser']['elo']} ({result['loser']['elo_change']:+d})")
else:
    print(f"Error: {response.status_code}")
    print(response.json())
```

### JavaScript (Node.js)

```javascript
const axios = require("axios");

const API_URL = "https://sorcererssummit.com/api/report-match";
const API_KEY = "your_api_key_here";

const matchData = {
  winner_name: "Alice",
  winner_id: 111111111,
  loser_name: "Bob",
  loser_id: 222222222,
  first_player: "y",
  match_time: 30,
  winner_deck_url: "https://curiosa.io/decks/alice-deck",
  loser_deck_url: "https://curiosa.io/decks/bob-deck",
  match_comment: "Tournament semifinal match",
};

axios
  .post(API_URL, matchData, {
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": API_KEY,
    },
  })
  .then((response) => {
    const result = response.data;
    console.log(`Match recorded successfully! Match ID: ${result.match_id}`);
    console.log(
      `Winner ELO: ${result.winner.elo} (${
        result.winner.elo_change >= 0 ? "+" : ""
      }${result.winner.elo_change})`
    );
    console.log(
      `Loser ELO: ${result.loser.elo} (${
        result.loser.elo_change >= 0 ? "+" : ""
      }${result.loser.elo_change})`
    );
  })
  .catch((error) => {
    console.error("Error:", error.response?.status);
    console.error(error.response?.data);
  });
```

### cURL

```bash
curl -X POST https://sorcererssummit.com/api/report-match \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key_here" \
  -d '{
    "winner_name": "Alice",
    "winner_id": 111111111,
    "loser_name": "Bob",
    "loser_id": 222222222,
    "first_player": "y",
    "match_time": 30,
    "winner_deck_url": "https://curiosa.io/decks/alice-deck",
    "loser_deck_url": "https://curiosa.io/decks/bob-deck",
    "match_comment": "Tournament semifinal match"
  }'
```

---

## Data Validation

### Player IDs

- Must be valid Discord user IDs (integers)
- Winner and loser IDs must be different
- Players will be automatically created in the ELO database if they don't exist (starting at 1500 ELO)

### First Player

- Must be either `"y"` or `"n"` (case-insensitive)
- `"y"` indicates the winner went first
- `"n"` indicates the loser went first

### Match Time

- Must be a positive integer representing minutes
- Set to `0` if unknown

### Deck URLs

- Should be valid Curiosa.io deck URLs
- If provided, the system will attempt to scrape deck data for statistics
- Invalid URLs will not cause the API call to fail

---

## ELO System

The bot uses a standard ELO rating system with the following parameters:

- **Starting ELO:** 1500
- **K-factor:** 32
- **Formula:** `new_elo = old_elo + K * (actual_score - expected_score)`

Where:

- `expected_score = 1 / (1 + 10^((opponent_elo - player_elo) / 400))`
- `actual_score = 1` for wins, `0` for losses

Both players' ELO ratings are updated automatically when a match is reported.

---

## Best Practices

1. **Store the API key securely** - Never commit API keys to version control
2. **Validate input** - Ensure player IDs and names are correct before submitting
3. **Handle errors gracefully** - Check response status codes and handle errors appropriately
4. **Use HTTPS in production** - Always use HTTPS when deployed to protect API keys
5. **Rate limiting** - Be considerate with API requests; the system is not rate-limited but excessive requests may impact performance
6. **Report matches promptly** - For accurate ELO tracking, report matches as soon as they're completed

---

## Troubleshooting

### "Invalid or missing API key"

- Verify your API key is correct
- Check that you're including the API key in the request headers
- Contact your server administrator if the issue persists

### "Missing required fields"

- Ensure all required fields are included in your request body
- Check for typos in field names (they are case-sensitive)
- Verify that your JSON is properly formatted

### "Invalid data type"

- Ensure `winner_id`, `loser_id`, and `match_time` are integers, not strings
- Convert numeric values to proper types before sending

### Match not appearing in Discord

- The API only records matches in the database
- Discord notifications are handled separately by the bot
- Check the web interface at `/match-history` to verify the match was recorded

---

## Support

For additional support or questions:

- Check the main bot documentation
- Contact your server administrator
- Review the API logs on the server for detailed error messages

---

## Changelog

### Version 1.0 (Initial Release)

- POST /api/report-match endpoint
- API key authentication
- ELO calculation and updates
- Deck data scraping from Curiosa.io
- Comprehensive error handling

Summary of Changes

1. API Authentication System (web-app/app.py)
   Added API key authentication using the @require_api_key decorator
   Supports both X-API-Key header and Authorization: Bearer formats
   Secure validation with logging of unauthorized attempts
2. Match Reporting Endpoint (web-app/app.py)
   Endpoint: POST /api/report-match
   Required fields:
   winner_name and winner_id
   loser_name and loser_id
   Optional fields:
   first_player (y/n)
   match_time (minutes)
   winner_deck_url and loser_deck_url
   match_comment
   reporter_id
   Automatically updates ELO ratings for both players
   Returns match ID and updated ELO stats
3. Comprehensive Documentation (web-app/API_DOCUMENTATION.md)
   Complete API reference with all endpoints
   Code examples in Python, JavaScript, and cURL
   Error handling guide
   Best practices and troubleshooting tips
4. Environment Configuration (discord-bot/.env)
   Added API_KEY variable (currently set to a placeholder)
   IMPORTANT: Change the API key before deploying to production!
   Quick Start
   Example API Call

import requests

response = requests.post(
"https://sorcererssummit.com/api/report-match",
headers={
"Content-Type": "application/json",
"X-API-Key": "summit_api_key_change_this_in_production_12345"
},
json={
"winner_name": "Alice",
"winner_id": 123456789,
"loser_name": "Bob",
"loser_id": 987654321,
"match_time": 25,
"winner_deck_url": "https://curiosa.io/decks/abc123"
}
)

print(response.json())

# Returns: {"success": true, "match_id": 1234, "winner": {...}, "loser": {...}}

Next Steps
Change the API Key - Update the API_KEY in discord-bot/.env to a secure random value before production use

Test the API - Start your Flask web app and test the endpoint:

cd web-app
python app.py
Share Documentation - Provide API_DOCUMENTATION.md to other developers who need to integrate with your bot

Deploy Securely - When deploying to production:

Use HTTPS
Generate a cryptographically secure API key
Consider rate limiting if needed
The API is fully integrated with your existing database and ELO system, so all matches reported through the API will appear in your match history and update player rankings automatically!
