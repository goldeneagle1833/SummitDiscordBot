"""Single source of truth for public LFG queue metadata."""

from services.pilots_service import is_pilot_active


QUEUE_DEFINITIONS = (
    {"type": "points", "label": "Rumble (Omens)", "emoji": "📊", "pilot": "PointsQueue", "deck_mode": "required"},
    {
        "type": "ranked",
        "label": "Ranked",
        "emoji": "⚔️",
        "pilot": "RankedQueue",
        "deck_mode": "required",
        "status_note": "Seer/Scry is back, LM and FM legal",
    },
    {
        "type": "testing",
        "label": "Casual",
        "emoji": "⭐",
        "status_emoji": "🧪",
        "status_note": "Spoiled cards are legal",
        "pilot": "CasualQueue",
        "deck_mode": "required",
    },
    {"type": "limited", "label": "Limited", "emoji": "🎲", "pilot": "GrewWolves", "deck_mode": "active_run"},
    {"type": "rumble", "label": "Rumble", "emoji": "💥", "pilot": "RumbleQueue", "deck_mode": "required"},
    {
        "type": "precon",
        "label": "Precon (LM/FM)",
        "emoji": "🧙",
        "pilot": None,  # switched by precon_settings.queue_enabled, not a pilot
        # No deck link: one player gets Lavamancer, the other Frostmage, at random
        "deck_mode": "precon",
        "status_note": "Lavamancer vs Frostmage, assigned at random",
    },
)


def _definition_enabled(definition):
    if definition["type"] == "precon":
        # Its own switch (Admin > Precon Ladder or !precon_queue), and only
        # while a precon ladder season is running
        from services.precon_service import queue_is_open

        return queue_is_open()
    return is_pilot_active(definition["pilot"])


def enabled_queue_definitions():
    return [definition for definition in QUEUE_DEFINITIONS if _definition_enabled(definition)]


def queue_definition(queue_type):
    return next((definition for definition in QUEUE_DEFINITIONS if definition["type"] == queue_type), None)


def queue_is_enabled(queue_type):
    definition = queue_definition(queue_type)
    return bool(definition and _definition_enabled(definition))


def queue_notes_text():
    """Rules notes for enabled queues, shown on the empty LFG status message."""
    lines = [
        f'{definition.get("status_emoji", definition["emoji"])} **{definition["label"]}:** {definition["status_note"]}'
        for definition in enabled_queue_definitions()
        if definition.get("status_note")
    ]
    return "\n\n" + "\n".join(lines) if lines else ""
