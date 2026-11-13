"""Play Sorcery Online test mode for the precon queue.

While an admin has PSO test mode on (Admin > Events) and the real precon queue
is closed, the three precon calls PSO makes answer 200 with sample data:

- status lists a precon queue marked ``"test_mode": true``
- joining checks the request the same way a real join does, then answers with
  the table request Summit *would* send PSO; nobody is queued
- a precon result for a pairing Summit doesn't have is checked and echoed back;
  nothing is recorded or rated

So PSO can build and test against the real endpoints without a ladder running.
"""

from services.precon_ladder import normalize_precon, precon_choices, precon_label

TEST_NOTE = "Precon test mode: no ladder is running. Nobody was queued and nothing was recorded."
SAMPLE_PAIRING_ID = 0
_VALID_OUTCOMES = {"decided", "no_contest", "conflict", "unknown"}


def test_queue_entry(voice_choices, default_voice, label="Precon (LM/FM)", emoji="🧙"):
    """The precon queue as status shows it in test mode."""
    return {
        "type": "precon",
        "label": label,
        "emoji": emoji,
        "waiting_count": 0,
        "joined": False,
        "deck_mode": "precon",
        "voice_options": True,
        "voice_choices": list(voice_choices),
        "default_voice": default_voice,
        "voice_flexible_supported": True,
        "voice_hold_seconds": 0,
        "precon_choices": precon_choices(),
        "precon": None,
        "waiting_by_voice": dict.fromkeys(voice_choices, 0),
        "waiting_willing": dict.fromkeys(voice_choices, 0),
        "voice": None,
        "voice_flexible": False,
        "test_mode": True,
        "test_note": TEST_NOTE,
    }


def test_join(payload, user_id, display_name, voice):
    """Check a precon join like a real one; return the test answer. ValueError on a bad request."""
    precon = normalize_precon(payload.get("precon"))
    if not precon:
        raise ValueError("precon must be one of: lavamancer, frostmage")
    other = "frostmage" if precon == "lavamancer" else "lavamancer"
    return {
        "test_mode": True,
        "test_note": TEST_NOTE,
        "accepted": {"queue_type": "precon", "precon": precon, "precon_label": precon_label(precon), "voice": voice},
        # What Summit sends PSO when a real precon pairing is made
        "sample_table_request": {
            "queueType": "precon",
            "pairingId": SAMPLE_PAIRING_ID,
            "deckUrl": None,
            "players": [
                {"discordUserId": str(user_id), "displayName": display_name, "deckUrl": None, "precon": precon},
                {"discordUserId": "0", "displayName": "Test Opponent", "deckUrl": None, "precon": other},
            ],
        },
    }


def test_result(fields, guild_id, pairing_id, replay_url=None, players=None):
    """Check a precon result like a real one; echo what would be recorded. ValueError on a bad request."""
    outcome = fields.get("outcome") or "decided"
    if outcome not in _VALID_OUTCOMES:
        raise ValueError("Invalid Play Sorcery Online outcome")
    winner_id, loser_id = fields.get("winner_id"), fields.get("loser_id")
    if outcome == "decided":
        if not winner_id or not loser_id:
            raise ValueError("winner_id and loser_id are required for a decided result")
        if str(winner_id) == str(loser_id):
            raise ValueError("The winner and loser must be different players")
    precons = {}
    for entry in players if isinstance(players, list) else []:
        if not isinstance(entry, dict):
            continue
        who = entry.get("discordUserId") or entry.get("discord_user_id") or entry.get("user_id")
        if entry.get("precon") is not None:
            key = normalize_precon(entry.get("precon"))
            if not key:
                raise ValueError("A player's precon must be one of: lavamancer, frostmage")
            precons[str(who)] = key
    return {
        "test_mode": True,
        "test_note": TEST_NOTE,
        "recorded": False,
        "would_record": {
            "guild_id": guild_id,
            "pairing_id": pairing_id,
            "queue_type": "precon",
            "outcome": outcome,
            "winner_id": str(winner_id) if winner_id else None,
            "loser_id": str(loser_id) if loser_id else None,
            "reporter_id": str(fields["reporter_id"]) if fields.get("reporter_id") else None,
            "winner_precon": precons.get(str(winner_id)),
            "loser_precon": precons.get(str(loser_id)),
            "winner_went_first": fields.get("winner_went_first"),
            "replay_url": replay_url,
        },
    }
