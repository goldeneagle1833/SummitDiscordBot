"""Voice-chat preferences for the Ranked and Casual queues.

Voice is a preference on a queue entry, not a separate queue: every player
in Ranked stays on one ladder. A player picks ``voice``, ``no_voice`` or
``any``; ``voice`` and ``no_voice`` never pair, ``any`` pairs with both.
A pairing is a voice match when either player asked for voice, and ranked
voice matches count toward top-cut eligibility.
"""

VOICE = "voice"
NO_VOICE = "no_voice"
ANY_VOICE = "any"
VOICE_PREFERENCES = (VOICE, NO_VOICE, ANY_VOICE)

VOICE_QUEUE_TYPES = ("ranked", "testing")

VOICE_LABELS = {
    VOICE: "🔊 Voice",
    NO_VOICE: "🔇 No voice",
    ANY_VOICE: "🤷 Either",
}

SUMMIT_VOICE_URL = "https://discord.gg/zSvyvyAVT"


def queue_supports_voice(queue_type):
    return queue_type in VOICE_QUEUE_TYPES


def normalize_voice_preference(value):
    """Return a valid preference, ``any`` when missing, or None when invalid."""
    if value is None or value == "":
        return ANY_VOICE
    value = str(value).strip().lower().replace("-", "_")
    return value if value in VOICE_PREFERENCES else None


def voice_preferences_compatible(pref_a, pref_b):
    return {pref_a or ANY_VOICE, pref_b or ANY_VOICE} != {VOICE, NO_VOICE}


def resolve_match_voice(pref_a, pref_b):
    """A match is played on voice when either player asked for voice."""
    return VOICE in (pref_a, pref_b)


def voice_match_text(queue_type, is_voice_match):
    """Match-found DM line for voice-enabled queues."""
    if is_voice_match:
        return (
            f"\n\n🔊 **Voice match** — join voice to play: "
            f"[Join To Make a Room]({SUMMIT_VOICE_URL})"
        )
    return ""
