# Analysis of Centralized Matchmaking Proposal

## What Summit Gains
- Players earn dust (participation rewards) — that's the only concrete benefit

---

## What Summit Loses

### Control Over Matchmaking
- Ranked queue moves to the main server's bot — no longer control the matching algorithm, queue behavior, timeouts, format rules, or UX
- Any bugs or downtime on their end breaks Summit ranked play
- Can't iterate or improve the ranked experience anymore

### Control Over Player Base
- Anyone on the main server can queue, not just Summit community members
- Lose the ability to ban/restrict problematic players from ranked
- Community identity gets diluted — players interact with the main server instead of Summit

### Data Sovereignty
- Go from owning data to polling someone else's DB, rate-limited to 1/minute
- If their API changes or goes down, leaderboards/ELO break
- Dependent on their schema and data format

### Technical Concerns
- 1-minute delay for match data is a real UX downgrade — currently updates instantly
- Existing match reporting flow (confirmations, buttons, deck submission) needs to be rebuilt around their data format
- Need to reverse-engineer or adapt to whatever their bot provides

---

## The Framing

The pitch is "the only change is where they click the matchmaking button" — but that undersells it significantly. Summit has a sophisticated system (ELO, match confirmation, deck checking, multiple queues, challenge system, ladder). Moving the core ranked queue to another server means:

- The bot becomes a secondary consumer of someone else's data
- Lose the ability to enforce own rules
- Community's ranked experience is now controlled by a third party

---

## Questions Worth Asking

1. Can Summit's bot be the matchmaking provider for its own server, with results **pushed** to the central DB instead? (Keep control, they get the data)
2. What happens if their bot goes down — can Summit fall back to its own queue?
3. Can Summit still enforce deck checking, format rules, and player restrictions?
4. Who decides the matching algorithm (ELO-based vs random)?
5. What's the governance model — do participating leagues get a say in changes?

---

## Bottom Line

The dust rewards are nice but the trade-off is giving up control of the core product (ranked matchmaking) to a third party. The better architecture would be **federated** — each league runs their own matchmaking and reports results to a central DB — rather than **centralized** where one bot does all matching. Push back and propose that Summit's bot reports match results to their system rather than surrendering the queue entirely.
