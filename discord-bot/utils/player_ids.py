"""Player ids that are not Discord accounts.

Players who sign in to the website with Google get a Summit player number
the first time a match is reported for them (the web app hands these out,
see web-app/services/summit_player_numbers.py). It is a 16-digit number in
a range no Discord account can have: Discord user ids are snowflakes made
after Discord launched in 2015, which are all 17+ digits. So the number
fits every INTEGER player column the bot already has, and the bot can tell
it apart from a Discord id without a lookup.

Nothing Discord-only (DMs, mentions, roles, member lookups) works for them.
"""

SUMMIT_NUMBER_MIN = 1_000_000_000_000_000
SUMMIT_NUMBER_END = 10_000_000_000_000_000  # exclusive


def is_summit_player_number(user_id) -> bool:
    """True for a Summit player number (a website-only player)."""
    try:
        value = int(str(user_id).strip())
    except (TypeError, ValueError):
        return False
    return SUMMIT_NUMBER_MIN <= value < SUMMIT_NUMBER_END


def player_mention(user_id, name) -> str:
    """A Discord mention for a Discord player, the bold name otherwise."""
    if is_summit_player_number(user_id):
        return f"**{name}**"
    return f"<@{user_id}>"
