# Research: Explorer Standings

## R-1: carde.io API Discovery

**Decision**: Use the carde.io JSON REST API directly — no HTML scraping.

**Rationale**: The sorcerytcg.com event pages are a React SPA powered by carde.io. The underlying API is publicly accessible (no auth headers required). Three endpoints cover all needed data:

| Endpoint | Data |
|----------|------|
| `GET https://api.carde.io/api/play/events/{event_uuid}` | Event metadata, phase list, tournament IDs, venue, player count |
| `GET https://api.carde.io/api/play/tournaments/{tournament_id}/standings` | Final standings for a given tournament phase (top cut) |
| `GET https://api.carde.io/api/play/activityPhases/{phase_id}/roster?sortBy=seed` | Full player list with standings (Swiss phase) |

**URL parsing**: Extract the UUID from `https://play.sorcerytcg.com/events/{uuid}`. Use `{uuid}` as the `event_uuid` for the API call.

**Alternatives considered**: HTML scraping via BeautifulSoup — rejected because the site requires JS execution (SPA). The JSON API is cleaner and more stable.

---

## R-2: Phase Resolution for Final Standings

**Decision**: Use the highest-stage completed phase for top-cut standings; use stage-1 (Swiss) for full roster.

**Rationale**: The event response includes `phases` keyed by stage number ("1" = Swiss, "2" = Single Elimination). Each phase contains a `tournament.id`. For completed events:

1. Sort phases by stage descending; take the first with `status: "complete"` -> final phase
2. Fetch `GET .../tournaments/{final_tournament_id}/standings` for top-cut placements (authoritative 1-N)
3. Fetch `GET .../activityPhases/{swiss_phase_id}/roster?sortBy=seed` for all players with Swiss standings

**Merge algorithm**:
- Players in the final-phase standings -> use their `standing` directly (1st, 2nd, etc.)
- Remaining players (in Swiss roster but not in top cut) -> offset their Swiss standing by the top-cut size
- For Swiss-only events (no phase 2) -> use Swiss standings directly

---

## R-3: Database Location

**Decision**: `web-app/explorer.db` + `EXPLORER_DB_PATH` in `webapp_config.py`.

**Rationale**: Consistent with `analytics.db` which also lives in `web-app/`. Explorer data is web-only.

**Alternatives considered**: Adding tables to `match_records.db` or `elo.db` — rejected (mixes concerns).

---

## R-4: Explorer Admin Authorization

**Decision**: New `is_explorer_admin()` + `require_explorer_admin` decorator in `utils/auth.py`. Admin list stored in `explorer_admins` table (UI-managed).

**Rationale**: The `is_curio_editor()` pattern is a direct template. Global admins always have access. Explorer-specific admins are UI-managed (no deploy cycle needed).

---

## R-5: Three-Track Points Configuration

**Decision**: JSON column `points_config` in `explorer_seasons` encoding all three tracks + qualification threshold.

**Three tracks**:
- **Pathfinder** = `participation` (10) + `bonus_pathfinder[exact_wins]` (0-win: +5, 1-win: +4, 2-win: +3, 3+-win: +0)
- **Persecutor** = `persecutor[final_standing]` for standings 1–8 only
- **Grand Explorer** = Pathfinder + Persecutor
- **Qualified** = season Persecutor total ≥ `trials_threshold` (default: 10)

**Default config**:
```json
{
  "participation": 10,
  "bonus_pathfinder": {"0": 5, "1": 4, "2": 3},
  "persecutor": {"1": 10, "2": 5, "3": 4, "4": 4, "5": 3, "6": 3, "7": 2, "8": 2},
  "trials_threshold": 10
}
```

**Win count derivation**: Swiss `tieBreakers.points // 3` (3 pts/win in standard config). Stored as `wins` integer in `explorer_results` at import time.

**Alternatives considered**: Hardcoded in service — rejected (per-season configurability required). Separate `points_rules` table — over-engineered for this small lookup.

---

## R-6: Migration Pattern

**Decision**: New `web-app/migrations/create_explorer_tables.py`, called in `app.py` on startup.

**Precedent**: `create_analytics_tables.py` follows this exact pattern.

---

## Summary

| # | Topic | Decision |
|---|-------|----------|
| R-1 | API | carde.io JSON REST API, no scraping |
| R-2 | Phase resolution | Highest stage = final; stage-1 = full roster; merge by offset |
| R-3 | Database | web-app/explorer.db + EXPLORER_DB_PATH |
| R-4 | Auth | is_explorer_admin() + require_explorer_admin; DB-backed |
| R-5 | Points config | Three-track JSON (pathfinder, persecutor, threshold) in explorer_seasons |
| R-6 | Migration | create_explorer_tables.py in app.py startup |
