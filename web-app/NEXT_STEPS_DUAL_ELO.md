# Next Steps: Dual ELO Implementation

## ✅ Completed

1. **Database & Match Reports**
   - ✅ Created `match_reports_web` table with TEXT IDs
   - ✅ Updated `match_confirmation.py` to keep `google_` prefix
   - ✅ Updated `paper_elo.py` to only update `paper_elo`/`paper_event_elo`
   - ✅ Web matches now save to separate table with proper IDs

2. **Documentation**
   - ✅ Created migration guide ([README_MATCH_REPORTS_WEB.md](migrations/README_MATCH_REPORTS_WEB.md))
   - ✅ Created dual ELO spec ([DUAL_ELO_SPEC.md](DUAL_ELO_SPEC.md))

## 🚧 TODO: Frontend Toggle Implementation

### 1. Add Toggle to Player Profile HTML

**File**: `templates/pages/player.html`

**Location**: Inside `<div class="player-header">`, next to player name

**Code to add** (around line 137):
```html
<div>
  <div style="display: flex; align-items: center; gap: 1rem;">
    <h1 class="player-name" id="player-name">Loading...</h1>

    <!-- ELO Source Toggle -->
    <div class="elo-source-toggle" id="elo-source-toggle" style="display: none;">
      <button class="elo-source-btn active" data-source="web" title="Web-reported matches">
        🌐 Web
      </button>
      <button class="elo-source-btn" data-source="bot" title="Bot-reported matches">
        🤖 Bot
      </button>
    </div>
  </div>
  <div class="player-elo" id="player-elo"></div>
  <div class="player-rank" id="player-rank"></div>
</div>
```

**CSS to add** (in `<style>` section):
```css
.elo-source-toggle {
  display: inline-flex;
  background: var(--color-bg-secondary, #2a2a3e);
  border: 1px solid var(--color-border, #3a3a4e);
  border-radius: 8px;
  overflow: hidden;
}

.elo-source-btn {
  padding: 6px 14px;
  font-size: 13px;
  border: none;
  background: transparent;
  color: var(--color-text-muted, #8b949e);
  cursor: pointer;
  transition: all 0.2s ease;
  font-weight: 500;
}

.elo-source-btn:hover {
  background: var(--color-bg-hover, #3a3a4e);
}

.elo-source-btn.active {
  background: var(--color-primary, #a855f7);
  color: white;
}
```

### 2. Update JavaScript in player.html

**Location**: `<script>` section in player.html

**Add these variables** (after line 583):
```javascript
let currentEloSource = 'web'; // or 'bot'
let hasWebMatches = false;
let hasBotMatches = false;
```

**Add toggle handler** (in DOMContentLoaded):
```javascript
// ELO Source Toggle Handler
document.querySelectorAll('.elo-source-btn').forEach(btn => {
  btn.addEventListener('click', async function() {
    const source = this.dataset.source;
    if (source === currentEloSource) return; // Already selected

    // Update UI
    document.querySelectorAll('.elo-source-btn').forEach(b => b.classList.remove('active'));
    this.classList.add('active');

    // Update state
    currentEloSource = source;
    localStorage.setItem('elo_source_preference', source);

    // Refetch data with new source
    const eventFilter = document.getElementById("elo-filter")?.value || "lifetime";
    await fetchPlayerData(eventFilter, 1, source);
  });
});
```

**Update fetchPlayerData function** (modify line 859):
```javascript
async function fetchPlayerData(eventFilter = "lifetime", page = 1, eloSource = null) {
  try {
    currentPage = page;

    // Use provided source or current source
    if (!eloSource) eloSource = currentEloSource;

    let url = `/api/player/${playerId}?page=${page}&per_page=${perPage}&source=${eloSource}`;
    if (eventFilter && eventFilter !== "lifetime") {
      url += `&event=${eventFilter}`;
    }

    const res = await fetch(url);
    // ... rest of function

    // After loading data, show toggle if player has both types
    hasWebMatches = data.has_web_matches || false;
    hasBotMatches = data.has_bot_matches || false;

    if (hasWebMatches || hasBotMatches) {
      document.getElementById('elo-source-toggle').style.display = 'inline-flex';

      // Set default based on user's auth provider or saved preference
      const saved = localStorage.getItem('elo_source_preference');
      if (saved) {
        currentEloSource = saved;
      } else {
        // Default to web for Google users, bot for Discord users
        currentEloSource = data.is_google_user ? 'web' : 'bot';
      }

      // Update toggle UI
      document.querySelectorAll('.elo-source-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.source === currentEloSource);
      });
    }
```

### 3. Update Backend API

**File**: `web-app/routes/api/players.py`

**Update /api/player/<player_id> endpoint**:

Add `source` query parameter handling:
```python
@players_bp.route("/player/<player_id>")
def get_player(player_id: str):
    # Get source parameter (web, bot, or auto)
    source = request.args.get("source", "auto")

    # If auto, detect based on user_id format
    if source == "auto":
        source = "web" if player_id.startswith("google_") else "bot"

    # Use different ELO columns based on source
    if source == "web":
        elo_column = "paper_elo"
        event_elo_column = "paper_event_elo"
    else:  # bot
        elo_column = "elo"  # or online_elo if migrated
        event_elo_column = "event_elo"  # or online_event_elo

    # Filter matches by source when building match history
    # match_records for bot, match_reports_web for web

    # Return response with elo_source indicator
    return jsonify({
        ...
        "elo_source": source,
        "has_web_matches": bool(web_match_count > 0),
        "has_bot_matches": bool(bot_match_count > 0),
        "paper_elo": player_paper_elo,
        "online_elo": player_online_elo,
        ...
    })
```

### 4. Discord Bot Migration (Separate Task)

**File**: `discord-bot/services/elo_service.py`

The bot should be updated to use `online_elo` and `online_event_elo` columns instead of legacy `elo`/`event_elo`.

This is a separate migration task and doesn't block the web toggle feature.

## Testing Steps

1. Run migration: `python web-app/migrations/create_match_reports_web.py`
2. Submit a web match report (with Google user)
3. Verify it appears in `match_reports_web` table
4. Check player profile shows toggle
5. Toggle between Web/Bot modes
6. Verify data switches correctly
7. Verify localStorage saves preference

## Rollout Strategy

1. ✅ Phase 1: Database & backend (DONE)
2. Phase 2: Frontend toggle (IN PROGRESS)
3. Phase 3: Bot migration (FUTURE)
4. Phase 4: Deprecate legacy columns (FUTURE)

## Quick Start

To implement the toggle now:
1. Add HTML/CSS from section 1
2. Add JavaScript from section 2
3. Update API from section 3
4. Test!
