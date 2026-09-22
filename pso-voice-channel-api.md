# Summit Voice Channel Lookup API

## `GET /api/matchmaking/voice`

Given the Discord IDs of the players in a game, returns the Summit voice channel they are
talking in, a link that drops a listener straight into it, and who is already in there.

Built for a "🔊 Listen in — 6 watching" button next to a live game.

### Authentication

Requires the partner API key via the `X-API-Key` header (same key as the matchmaking relay).

### Request

```
GET https://sorcererssummit.com/api/matchmaking/voice?user_ids=123456789012345678,987654321098765432
X-API-Key: <your-api-key>
```

| Parameter  | Description                                                                 |
|------------|-----------------------------------------------------------------------------|
| `user_ids` | Discord user IDs, comma-separated or repeated (`?user_ids=1&user_ids=2`). Up to 10. |

### Response

`200 OK`

```json
{
  "status": "together",
  "channel": {
    "id": "1234567890",
    "name": "The Dungeon",
    "channel_url": "https://discord.com/channels/<guild>/<channel>",
    "invite_url": "https://discord.gg/abc123",
    "listen_url": "https://discord.gg/abc123",
    "member_count": 8,
    "player_count": 2,
    "spectator_count": 6,
    "spectators": [
      {
        "user_id": "111",
        "display_name": "OFN-CJ",
        "avatar_url": "https://cdn.discordapp.com/avatars/...",
        "is_player": false,
        "streaming": false
      }
    ],
    "players_in_channel": [
      { "user_id": "123456789012345678", "display_name": "Bruce", "is_player": true, "streaming": true }
    ]
  },
  "players": [
    {
      "user_id": "123456789012345678",
      "display_name": "Bruce",
      "in_voice": true,
      "channel_id": "1234567890",
      "streaming": true
    },
    {
      "user_id": "987654321098765432",
      "display_name": "Aadu",
      "in_voice": true,
      "channel_id": "1234567890",
      "streaming": false
    }
  ],
  "summit_invite_url": "https://discord.gg/sorcererssummit",
  "voice_hub_url": "https://discord.com/channels/1319120227643949211/1552047481129541713"
}
```

| Field               | Description                                                                          |
|---------------------|--------------------------------------------------------------------------------------|
| `status`            | `together` (all requested players in one channel), `split` (someone is in voice but not all of them together), `not_in_voice`, or `unavailable` (bot offline — served with `503`) |
| `channel`           | The busiest channel among the requested players; `null` when nobody is in voice        |
| `listen_url`        | What the button should link to — a channel invite, falling back to the channel deep link |
| `member_count`      | Humans in the channel (bots excluded)                                                  |
| `spectator_count`   | Everyone in the channel who isn't one of the requested players — the "6 watching" number |
| `spectators`        | Up to 25 of those listeners, in channel order                                          |
| `streaming`         | `true` when that member is screen-sharing (Go Live) in the channel                     |
| `players[].in_voice`| `false` when the player isn't in a Summit voice channel (or isn't a Summit member)     |

`display_name` is `null` for a user ID that isn't a member of the Summit.

### Errors

| Status | Meaning                                                             |
|--------|---------------------------------------------------------------------|
| `400`  | `user_ids` missing, non-numeric, or more than 10 ids                 |
| `401`  | Missing or invalid API key                                           |
| `503`  | Summit bot is offline or still starting — body is `{"status": "unavailable", ...}` |

### Notes

- Reads the bot's cached Discord state, so polling is cheap; the invite link is created once
  per channel per 30 minutes and lives for an hour.
- Invites are to the voice channel itself, so a click joins the Summit and lands on that channel.
  If the bot lacks Create Invite permission there, `invite_url` is `null` and `listen_url` falls
  back to the `discord.com/channels/...` deep link (members only).
- Voice rooms are created on demand: players join the hub channel and the bot spins up a named
  room, so channel IDs change from game to game. Always look it up per game.
