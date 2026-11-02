# Summit Applaud API (for Play Sorcery Online)

**Applaud** is the friendly opposite of **Report Player**: after a game, a player applauds
their opponent and says why (good sport, great on voice, helped me learn, ...). On Discord
this is the 👏 **Applaud** button on the Summit match message. This endpoint lets Play Sorcery
Online do the same from inside PSO. Players see the word "Applaud"; the endpoint and field
names still say "kudos" (the feature's earlier name), and they stay that way.

Applause goes into the same Summit list as the Discord button. Applauded players can be
picked as the **Player of the Day** on the sorcererssummit.com homepage, which shows the
reason (and, unless the giver asked otherwise, who gave it).

Base URL: `https://sorcererssummit.com`

## Authentication

Send the partner API key in the `X-API-Key` header (the same key PSO already uses for
`/api/report-external-match`, `/api/blocks` and `/api/player-reports`).
`Authorization: Bearer <key>` also works.

```
X-API-Key: <your-api-key>
```

A missing or wrong key returns `401`:

```json
{ "success": false, "error": "Invalid API key" }
```

## Player IDs

All IDs are **Discord user IDs** as strings, e.g. `"123456789012345678"`, the same
`discordUserId` Summit sends PSO when it opens a table.

Always send the giving player's own ID from their PSO login, never an ID the player typed in.

---

## Applaud an opponent: `POST /api/player-kudos`

### Request

```
POST https://sorcererssummit.com/api/player-kudos
X-API-Key: <your-api-key>
Content-Type: application/json
```

```json
{
  "giver_id": "123456789012345678",
  "receiver_id": "876543210987654321",
  "giver_name": "Alice",
  "receiver_name": "Bob",
  "reasons": ["good_sport", "great_voice"],
  "message": "Super friendly and explained Rubble to me. GG!",
  "anonymous": false,
  "pairing_id": 1234
}
```

| Field           | Required | Description                                                                 |
|-----------------|----------|-----------------------------------------------------------------------------|
| `giver_id`      | yes      | Discord user ID of the player applauding                                     |
| `receiver_id`   | yes      | Discord user ID of the opponent being applauded (must differ from the giver)  |
| `reasons`       | see note | List of reason codes from the table below                                   |
| `message`       | see note | Short thank-you in the player's own words, up to 200 characters. **Public**: it can be shown on the Summit homepage. |
| `anonymous`     | no       | `true` keeps the giver's name off the website. Default `false` (the giver is named, since it's praise). Admins always see who gave it. |
| `giver_name`    | no       | Name to use if Summit doesn't know the player (max 100 chars)               |
| `receiver_name` | no       | Same, for the receiver                                                      |
| `pairing_id`    | no       | Summit `pairingId` from the table Summit opened, if there was one            |

**Note:** send at least one reason **or** a message. Applause with neither is rejected,
same as the Discord form.

### Reason codes

| Code          | Shown as                                    |
|---------------|---------------------------------------------|
| `good_sport`  | Good sport, win or lose                     |
| `friendly`    | Friendly and fun to play with               |
| `great_voice` | Great to talk with on voice                 |
| `helpful`     | Helped me learn or explained a rule         |
| `good_pace`   | Played at a good pace                       |
| `fair_play`   | Honest and fair, reported the result right  |
| `great_game`  | Great game, well played                     |

### Only opponents you actually played

Applause is tied to a **recorded Summit match** between the two players:

- The two must have a match on record (a reported and confirmed Summit result) from the
  last **14 days**. With `pairing_id`, Summit uses that pairing's match; if that pairing has
  no recorded result, any recent match between the two counts.
- Each player can applaud **once** per match. A second game between the same two players
  means a second chance.
- Both players can applaud each other for the same match.

PSO should only show an Applaud option for opponents the player just finished a Summit
game with. Casual PSO games that never reached Summit can't be applauded.

### Responses

`201 Created`:

```json
{ "success": true, "kudos_id": 42, "match_id": 98765 }
```

`422` when there's no recorded match between the two in the last 14 days (for example the
result hasn't been reported yet):

```json
{ "success": false, "code": "no_match", "error": "No recorded match between these players in the last 14 days" }
```

`409` when the giver already applauded that opponent for that match:

```json
{ "success": false, "code": "already_given", "error": "This opponent was already applauded for this match" }
```

`400` for bad input (missing IDs, applauding yourself, unknown reason codes, a message over
200 characters, `anonymous` that isn't `true`/`false`, a non-integer `pairing_id`). Unknown
reasons also return the allowed list:

```json
{ "success": false, "error": "Unknown reasons: toxic", "allowed_reasons": ["good_sport", "friendly", "great_voice", "helpful", "good_pace", "fair_play", "great_game"] }
```

---

## What happens next

- Summit admins see every applause on the admin log page (**Player Applause**), tagged
  "via Play Sorcery Online", and can hide one from the homepage.
- Each day the homepage **Player of the Day** is picked from players applauded in
  the previous 7 days (today's applause counts from tomorrow). Players applauded by more different
  people have a better chance, and the same player isn't picked several days in a row when
  others are available. The slide shows the player, the thank-you message or reasons, and
  the giver's name unless they chose `anonymous`.
- Report Player and blocks are unchanged: they stay private and work exactly as before.
