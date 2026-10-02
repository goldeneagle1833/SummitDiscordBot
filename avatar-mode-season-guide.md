# Avatar-mode seasons

A Summit season can run in one of two ways. The admin picks one when the season starts,
and it stays that way until the season ends.

| Season type | How you're rated |
|-------------|------------------|
| **Player mode** | One season Elo per player. Every ranked game moves it, whatever avatar you played. This is how every season worked until now. |
| **Avatar mode** | One season Elo for each avatar you play. Your Imposter rating and your Persecutor rating are separate entries on the same ladder. |

This guide explains Avatar mode.

---

## The short version

- Every player/avatar pair has its own season Elo, starting at **1500**.
- A ranked game only moves the two avatar entries that were played in it.
- You can appear on the ladder once for every avatar you've played.
- Ranked games need a **deck link**. Your avatar is read from the deck; you don't pick it
  from a list.
- **Top cut is still one invite per player**, no matter how many of your avatars are near
  the top.
- Lifetime Elo is unchanged: one number per player, moved by every ranked game.

## Why

- Trying a new or off-meta avatar no longer risks the rating you built on your main.
- A strong main entry doesn't discourage you from playing more games.
- More avatars show up in ranked play, and everyone gets real per-avatar standings.

## Example

| Rank | Player | Avatar | Season Elo |
|------|--------|--------|------------|
| 1 | Aadu | Imposter | 1650 |
| 8 | Sky | Battlemage | 1572 |
| 21 | Aadu | Persecutor | 1530 |

Aadu has two entries because Imposter and Persecutor are rated separately. A game on
Imposter doesn't touch the Persecutor entry. Both games still move Aadu's single lifetime
Elo.

---

## Playing ranked

### 1. Join with a deck link

Ranked needs a deck link in an Avatar-mode season:

- **Curiosa / sorcerytcg.com** deck links and **Play Sorcery Online** deck links both work.
- The deck must be **public**, so the bot can read it.
- If the bot can't find an avatar in the link, you're told right away and aren't queued.
  Fix the link and join again.

This applies everywhere a ranked game can start:

| How you start a game | Where the deck link goes |
|----------------------|--------------------------|
| Ranked queue button | The Deck URL box in the join form (now required) |
| `!issue_challenge` | `!issue_challenge <deck link>` (add `no_voice` for a no-voice game), or the `deck_url` option on `/issue-challenge` |
| `!challenge @player` | Both the challenger and the player who accepts enter a deck link |
| Play Sorcery Online | Their ranked join form asks for it |

Casual, Rumble and Limited queues are unchanged.

### 2. Your avatar is locked when the match is made

When you're paired, the bot reads both decks again and **locks each player's avatar to
that match**. Both players are told the two avatars in the match message.

- You choose your deck **before** you know your opponent, so nobody can pick an avatar to
  dodge a matchup.
- Editing the deck afterwards doesn't change the avatar the game is rated on.

### 3. Report and confirm as usual

Reporting hasn't changed. The confirmation your opponent receives now lists **both
avatars** next to the result. If an avatar is wrong, press **Dispute** instead of
confirming and an admin will sort it out.

---

## How the rating works

It's the same Elo formula as always, applied to the two avatar entries in the match:

- A new avatar entry starts at **1500**, even for an experienced player.
- The season K-factor starts at 16 on day one and rises by 2 a day to 32, exactly as in
  past seasons.
- Each ranked game moves three numbers for each player:
  1. **Lifetime Elo** (one per player), as always.
  2. **The avatar entry** you played. This is the season ladder.
  3. Your old-style one-per-player season Elo, which is kept up to date behind the scenes
     but isn't shown or used in an Avatar-mode season.

**Ladder challenges** (`!issue_challenge`) work as before. The special stakes (2x gain for
the challenger's opponent, 0.5x loss for the Top 16 player) apply when the two **avatar
entries in that match** are 100 or more Elo apart.

---

## Leaderboards and profiles

**Discord**
- The leaderboard channel and `!event_leaderboard` list entries as *Player (Avatar)*.
- `!rank` shows every avatar you've played this season, each with its Elo, rank and games.

**Website**
- The home page ladder has an Avatar column. Under each avatar it shows where that entry
  stands among everyone on the same avatar, for example "#2 of 11 Imposter players".
- Your profile lists every avatar entry with its Elo and rank, adds season Elo and rank to
  Avatar Performance, and has a season Elo graph for each avatar.
- The Top Players by Avatar page opens on the current season.

---

## Top cut

Top-cut qualification belongs to the **player**, not the avatar.

- The ladder is read in Elo order, and each player counts **once**, at their best avatar.
- A second high entry from the same player never takes another slot; the next player down
  the ladder gets it.
- Every entry still shows on the leaderboard, so several high entries improve what you see
  next to your name, but not your number of invites.
- The voice-game requirement for top cut counts your games across **all** your avatars.
- In the top-cut bracket you may play any legal avatar, not just the one you qualified with.
  Bracket games move lifetime Elo only.

---

## What stays the same

- One lifetime Elo per player.
- One shared ranked queue with random matchmaking and the same voice / no-voice choice.
- Casual, Rumble, Limited and top-cut games don't change season Elo.
- The size and structure of top cut.
- Reporting, confirming, disputes and `!correct_match`.

---

## Questions

**I've only got time for a few games. Should I stick to one avatar?**
If you're chasing top cut, concentrating games on one avatar gives that entry the most
chances to climb. Other avatars you try can't hurt it.

**I'm good, and my new avatar starts at 1500. Is that fair to my opponents?**
A new entry rises quickly: beating established entries is worth around 20 points a win
until it settles. The community preferred one simple rule (every avatar starts at 1500)
over special cases.

**Can people see what I'm playing?**
Your opponent sees your avatar when you're matched, and avatar entries are public on the
leaderboard. Your deck list and elements are not shown.

**What if my deck link stops working after I've queued?**
The avatar found when you joined is used, so the match still goes ahead.

**What if I played a different avatar from the deck I linked?**
The game is rated on the deck you linked. Your opponent can dispute the report if the
avatar shown isn't the one you played.

---

## For admins

| Task | Command |
|------|---------|
| Start an Avatar-mode season | `!start_event avatar <season name>` |
| Start a Player-mode season | `!start_event <season name>` (or `!start_event player <season name>`) |
| See the running season's mode | `!event_status` |
| Report a match by hand | `/admin-report winner loser`, then enter both avatars in the form |
| Report a ladder challenge by hand | `/admin-challenge-report winner loser top16_player`, then both avatars |
| Set one avatar entry's Elo | `!spot_elo_reset @player 1500 <avatar name>` |
| Flip a result | `!correct_match <match id>` (the avatars swap with the players) |
| Remove a match | `!remove_match <match id>` (lifetime, season and avatar Elo are each undone) |

- **The mode is locked once the season starts.** To change it, end the season and start a
  new one.
- Avatar names typed in admin forms are checked against the official avatar list. A typo
  is rejected with a suggestion ("did you mean Imposter?") and nothing is recorded.
- The prefix commands `!admin_report` and `!admin_challenge_report` point you to the slash
  versions during an Avatar-mode season, because the slash versions ask for the avatars.
- Start seasons from Discord. The Start Event button on the website doesn't work yet.
- Rating inflation from abandoned avatar entries is a known tradeoff of this format; watch
  the average season Elo of active entries over the season.
