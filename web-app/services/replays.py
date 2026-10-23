"""Who may see a match's Sorcery Online replay link.

A replay shows both players' decks, and ranked deck lists stay private. The
two players in the match and admins always see it; everyone else only when
both players turned on "Game Replays" in their profile privacy settings.
"""

from repositories.pso_game_lookups import PsoGameLookupRepository
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


def own_backfilled_replays(match_ids) -> dict[int, str]:
    """{match_id: url} of the viewer's own replays from the Season 8 PSO backfill.

    PSO hands back each player's own view of the game, and those links play
    even when the player made the replay private on PSO. So they are only ever
    shown to that player: not to the opponent, admins or the public, whatever
    the "Game Replays" setting says.
    """
    user = get_current_user()
    if not user:
        return {}
    viewer = str(user["id"]).removeprefix("google_")
    out = {}
    for match_id, row in PsoGameLookupRepository().replays_for(match_ids).items():
        if viewer == str(row["winner_id"]) and row["winner_replay_url"]:
            out[match_id] = row["winner_replay_url"]
        elif viewer == str(row["loser_id"]) and row["loser_replay_url"]:
            out[match_id] = row["loser_replay_url"]
    return out
