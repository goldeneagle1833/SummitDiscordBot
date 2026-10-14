"""Who may see a match's Sorcery Online replay link.

A replay shows both players' decks, and ranked deck lists stay private. The
two players in the match and admins always see it; everyone else only when
both players turned on "Game Replays" in their profile privacy settings.
"""

from repositories.user_profiles import UserProfileRepository
from utils.auth import get_current_user, is_admin


def viewable_replays(matches: list[tuple[str, str]]) -> list[bool]:
    """For each (winner_id, loser_id) pair, whether the current viewer may see its replay."""
    if is_admin():
        return [True] * len(matches)
    user = get_current_user()
    viewer = str(user["id"]).removeprefix("google_") if user else None
    pairs = [(str(w), str(l)) for w, l in matches]
    public = UserProfileRepository().users_with_public_section(
        {p for pair in pairs for p in pair}, "replays",
    ) if pairs else set()
    return [viewer in pair or all(p in public for p in pair) for pair in pairs]
