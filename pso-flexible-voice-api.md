# Flexible voice choice — matchmaking API changes for Play Sorcery Online

Players can now say they are **also OK with their other voice choice**. Everything is
additive: a client that never sends the new field gets exactly the old behaviour.

## Matching rules

- Each queue entry has a first choice (`voice` or `no_voice`) and, optionally,
  `voice_flexible: true` ("the other choice is OK too").
- Two players pair when they share a choice they would both play. Strict players only pair
  with the same choice, as before.
- A match is **on voice whenever both players would play voice** (e.g. a no-voice-first,
  voice-OK player and a voice player get a voice game).
- Among compatible partners, ones that make a voice match come first, then oldest first.
- A voice-first, no-voice-OK player waits `VOICE_HOLD_SECONDS` (30) for a voice partner. During
  that hold no no-voice game is made for them; after it, a 5-second sweep pairs them with a
  waiting no-voice player through the normal join flow.
- Strict voice players still get the "play without voice?" DM; flexible players don't need it.
- Discord join modal: two checkboxes, "Are you willing to play this match with voice on Discord?" and "Are you willing to play this match without voice?" (on voice,
  without voice; at least one). Both start unticked the first time; after that the modal ticks
  the player's last answers (table `last_voice_answers` in match_records.db, also saved from API
  joins). Both ticked is Either: voice first, no voice OK. PSO asks the same two questions as
  Yes/No, starting at No and remembering the last answers in the browser.
- The Discord status board shows a count per queue instead of listing waiting players.

## Status

`GET /api/matchmaking/users/{discordUserId}/status`, per queue (all fields are new and optional
to read):

| Field                      | Meaning                                                                  |
|----------------------------|--------------------------------------------------------------------------|
| `voice_flexible_supported` | `true` when joins to this queue may send `voice_flexible`.               |
| `voice_hold_seconds`       | How long a voice-first, no-voice-OK player waits for voice (30).          |
| `waiting_willing`          | `{voice, no_voice}`: waiting players who would play each choice.         |
| `voice_flexible`           | The player's own entry is also OK with the other choice.                 |

`waiting_by_voice` is unchanged (first choices).

## Joining

`POST /api/matchmaking/users/{discordUserId}/queues` accepts `"voice_flexible": true`
alongside `voice`. Left out (or false) means only `voice`, exactly as before. Limited ignores it.
