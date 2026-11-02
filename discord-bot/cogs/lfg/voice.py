"""Voice-chat preferences for every LFG queue.

Voice is a preference on a queue entry, not a separate queue: every player
in Ranked stays on one ladder. A player picks a first choice, ``voice`` or ``no_voice``,
and can say they are also OK with the other one (``voice_flexible``). Two
players pair when they share a choice they'd play: strict players only pair
with the same choice, as before. A match is on voice whenever both players are
willing to play voice. A player whose first choice is voice but who is also OK
without voice waits ``VOICE_HOLD_SECONDS`` for another voice player before a
no-voice game is made for them. There is no "either" option; an old
``either`` value (e.g. from an outdated client) is read as voice. Voice is the
default when a join path gives no preference. Limited has no voice choice at
all: players pair with whoever is waiting. Ranked voice matches count toward top-cut
eligibility.
"""

import datetime

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


# A voice-first player who is also OK without voice waits this long for a voice
# partner before a no-voice game is made for them.
VOICE_HOLD_SECONDS = 30


def normalize_voice_flexible(value):
    """Whether a join says the player is also OK with their other voice choice."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return False


def willing_voice_choices(pref, flexible=False):
    """The voice choices a player would play: their first choice, plus the other when flexible."""
    first = normalize_voice_preference(pref) or DEFAULT_VOICE
    return {VOICE, NO_VOICE} if flexible else {first}


def voice_preferences_compatible(pref_a, pref_b, flexible_a=False, flexible_b=False):
    """Players pair when they share a voice choice they'd both play."""
    return bool(willing_voice_choices(pref_a, flexible_a) & willing_voice_choices(pref_b, flexible_b))


def resolve_match_voice(pref_a, pref_b, flexible_a=False, flexible_b=False):
    """A match is on voice whenever both players are willing to play voice."""
    return VOICE in (willing_voice_choices(pref_a, flexible_a) & willing_voice_choices(pref_b, flexible_b))


def entry_voice_flexible(entry):
    """Whether a queue entry is also OK with its other voice choice."""
    return bool((entry or {}).get("voice_flexible"))


def holding_for_voice(pref, flexible, joined_at, now=None):
    """A voice-first, no-voice-OK player still waiting out the voice hold."""
    if not flexible or (normalize_voice_preference(pref) or DEFAULT_VOICE) != VOICE:
        return False
    now = now or datetime.datetime.now()
    return (now - joined_at).total_seconds() < VOICE_HOLD_SECONDS


# Join-modal answers: "Which games will you play?" Ticking both is Either (voice first).
WILL_PLAY_VOICE = VOICE
WILL_PLAY_NO_VOICE = NO_VOICE


def voice_choice_from_checkboxes(values):
    """(first choice, also OK with the other) from the join modal's "which games will you play?".

    Both ticked is Either: voice first, no voice OK. Nothing ticked (an old modal) is voice only.
    """
    ticked = set(values or ())
    if VOICE in ticked and NO_VOICE in ticked:
        return VOICE, True
    if NO_VOICE in ticked:
        return NO_VOICE, False
    return VOICE, False


def voice_choice_label(pref, flexible=False):
    """How a player's voice choice reads in queue messages."""
    first = normalize_voice_preference(pref) or DEFAULT_VOICE
    if not flexible:
        return VOICE_LABELS[first]
    return "🤝 Voice or no voice (voice first)"


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
