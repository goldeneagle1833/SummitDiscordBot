"""Voice-chat preferences for every LFG queue.

Voice is a preference on a queue entry, not a separate queue: every player
in Ranked stays on one ladder. A player picks ``voice`` or ``no_voice`` and
only pairs with players who picked the same. Voice is the default when a
join path gives no preference. Ranked voice matches count toward top-cut
eligibility.
"""

VOICE = "voice"
NO_VOICE = "no_voice"
VOICE_PREFERENCES = (VOICE, NO_VOICE)
DEFAULT_VOICE = VOICE

VOICE_LABELS = {
    VOICE: "🔊 Voice",
    NO_VOICE: "🔇 No voice",
}

VOICE_ICONS = {
    VOICE: "🔊",
    NO_VOICE: "🔇",
}

SUMMIT_VOICE_URL = "https://discord.com/channels/1319120227643949211/1552047481129541713"


def normalize_voice_preference(value):
    """Return a valid preference, ``voice`` when missing, or None when invalid."""
    if value is None or value == "":
        return DEFAULT_VOICE
    value = str(value).strip().lower().replace("-", "_")
    return value if value in VOICE_PREFERENCES else None


def voice_preferences_compatible(pref_a, pref_b):
    """Players only pair with others who made the same voice choice."""
    return (pref_a or DEFAULT_VOICE) == (pref_b or DEFAULT_VOICE)


def resolve_match_voice(pref_a, pref_b):
    """A match is played on voice when the players asked for voice."""
    return VOICE in (pref_a or DEFAULT_VOICE, pref_b or DEFAULT_VOICE)


def voice_match_tag(is_voice_match):
    """Match-found title suffix saying whether the match is on voice."""
    return "(🔊 Voice match)" if is_voice_match else "(🔇 No-voice match)"


def voice_match_text(is_voice_match):
    """Match-found DM line: the room link, voice matches only."""
    if is_voice_match:
        return f"\n\n🔊 **Voice chat:** [Join To Make a Room]({SUMMIT_VOICE_URL})"
    return ""
