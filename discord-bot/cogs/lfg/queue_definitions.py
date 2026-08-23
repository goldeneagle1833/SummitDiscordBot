"""Single source of truth for public LFG queue metadata."""

from services.pilots_service import is_pilot_active


QUEUE_DEFINITIONS = (
    {"type": "points", "label": "Rumble (Omens)", "emoji": "📊", "pilot": "PointsQueue", "deck_mode": "required"},
    {"type": "ranked", "label": "Ranked", "emoji": "⚔️", "pilot": "RankedQueue", "deck_mode": "required"},
    {"type": "testing", "label": "Casual", "emoji": "⭐", "pilot": "CasualQueue", "deck_mode": "required"},
    {"type": "limited", "label": "Limited", "emoji": "🎲", "pilot": "GrewWolves", "deck_mode": "active_run"},
    {"type": "rumble", "label": "Rumble", "emoji": "💥", "pilot": "RumbleQueue", "deck_mode": "required"},
)


def enabled_queue_definitions():
    return [definition for definition in QUEUE_DEFINITIONS if is_pilot_active(definition["pilot"])]


def queue_definition(queue_type):
    return next((definition for definition in QUEUE_DEFINITIONS if definition["type"] == queue_type), None)


def queue_is_enabled(queue_type):
    definition = queue_definition(queue_type)
    return bool(definition and is_pilot_active(definition["pilot"]))
