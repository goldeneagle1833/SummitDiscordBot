"""Voice-chat preferences for every LFG queue.

Voice is a preference on a queue entry, not a separate queue: every player
in Ranked stays on one ladder. A player picks ``voice`` or ``no_voice``, and
players only pair with the same choice. There is no "either" option; an old
``either`` value (e.g. from an outdated client) is read as voice. Voice is the
default when a join path gives no preference. Limited has no voice choice at
all: players pair with whoever is waiting. Ranked voice matches count toward top-cut
eligibility.
"""

VOICE = "voice"
NO_VOICE = "no_voice"
LEGACY_EITHER = "either"  # retired choice, read as voice
VOICE_PREFERENCES = (VOICE, NO_VOICE)
DEFAULT_VOICE = VOICE

# Queues with no voice choice: players join and pair with whoever is waiting.
NO_VOICE_CHOICE_QUEUES = ("limited",)


def queue_has_voice_choice(queue_type):
    """Whether players pick voice or no voice when joining this queue."""
    return queue_type not in NO_VOICE_CHOICE_QUEUES

VOICE_LABELS = {
    VOICE: "🔊 Voice",
    NO_VOICE: "🔇 No voice",
}

VOICE_ICONS = {
    VOICE: "🔊",
    NO_VOICE: "🔇",
}

SUMMIT_VOICE_URL = "https://discord.com/channels/1319120227643949211/1319121204480577586"


def normalize_voice_preference(value):
    """Return a valid preference, ``voice`` when missing or ``either``, or None when invalid."""
    if value is None or value == "":
        return DEFAULT_VOICE
    value = str(value).strip().lower().replace("-", "_")
    if value == LEGACY_EITHER:
        return VOICE
    return value if value in VOICE_PREFERENCES else None


def voice_preferences_compatible(pref_a, pref_b):
    """Players pair only with the same voice choice."""
    return (normalize_voice_preference(pref_a) or DEFAULT_VOICE) == (
        normalize_voice_preference(pref_b) or DEFAULT_VOICE
    )


def resolve_match_voice(pref_a, pref_b):
    """A match is on voice unless a player asked for no voice."""
    return NO_VOICE not in (pref_a or DEFAULT_VOICE, pref_b or DEFAULT_VOICE)


def voice_from_checkboxes(values):
    """Preference from the join modal's checkboxes: only "no voice" ticked means no voice.

    The modal allows one tick; none ticked (or, from an old modal, both) means voice.
    """
    ticked = set(values or ())
    if NO_VOICE in ticked and VOICE not in ticked:
        return NO_VOICE
    return VOICE


def voice_match_tag(is_voice_match):
    """Match-found title suffix saying whether the match is on voice."""
    return "(🔊 Voice match)" if is_voice_match else "(🔇 No-voice match)"


def voice_match_text(is_voice_match):
    """Match-found DM line: the room link, voice matches only."""
    if is_voice_match:
        return f"\n\n🔊 **Voice chat:** [Join To Make a Room](<{SUMMIT_VOICE_URL}>)"
    return ""
