"""Voice-chat preferences for every LFG queue.

Voice is a preference on a queue entry, not a separate queue: every player
in Ranked stays on one ladder. A player picks ``voice``, ``no_voice`` or
``either``. Voice and no-voice players only pair with the same choice or with
``either`` players, who pair with anyone. Voice is the default when a join
path gives no preference. Ranked voice matches count toward top-cut
eligibility.
"""

VOICE = "voice"
NO_VOICE = "no_voice"
EITHER = "either"
VOICE_PREFERENCES = (VOICE, NO_VOICE, EITHER)
DEFAULT_VOICE = VOICE

VOICE_LABELS = {
    VOICE: "🔊 Voice",
    NO_VOICE: "🔇 No voice",
    EITHER: "🔊🔇 Voice or no voice",
}

VOICE_ICONS = {
    VOICE: "🔊",
    NO_VOICE: "🔇",
    EITHER: "🔊🔇",
}

SUMMIT_VOICE_URL = "https://discord.com/channels/1319120227643949211/1552047481129541713"


def normalize_voice_preference(value):
    """Return a valid preference, ``voice`` when missing, or None when invalid."""
    if value is None or value == "":
        return DEFAULT_VOICE
    value = str(value).strip().lower().replace("-", "_")
    return value if value in VOICE_PREFERENCES else None


def voice_preferences_compatible(pref_a, pref_b):
    """Players pair with the same voice choice; ``either`` pairs with anyone."""
    pref_a, pref_b = pref_a or DEFAULT_VOICE, pref_b or DEFAULT_VOICE
    return EITHER in (pref_a, pref_b) or pref_a == pref_b


def resolve_match_voice(pref_a, pref_b):
    """A match is on voice unless a player asked for no voice.

    Two ``either`` players play on voice.
    """
    return NO_VOICE not in (pref_a or DEFAULT_VOICE, pref_b or DEFAULT_VOICE)


def voice_from_checkboxes(values):
    """Preference from the join modal's checkboxes: none ticked means voice."""
    ticked = set(values or ())
    if VOICE in ticked and NO_VOICE in ticked:
        return EITHER
    if NO_VOICE in ticked:
        return NO_VOICE
    return VOICE


def voice_match_tag(is_voice_match):
    """Match-found title suffix saying whether the match is on voice."""
    return "(🔊 Voice match)" if is_voice_match else "(🔇 No-voice match)"


def voice_match_text(is_voice_match):
    """Match-found DM line: the room link, voice matches only."""
    if is_voice_match:
        return f"\n\n🔊 **Voice chat:** [Join To Make a Room]({SUMMIT_VOICE_URL})"
    return ""
