# Feature Specification: Mobile Life Counter with Match Reporting

**Feature Branch**: `001-mobile-life-counter`
**Created**: 2026-03-09
**Status**: Draft
**Input**: User description: "When the user is in a moble view at the top right of the bar with the Sorcerers Summit title it will have a lifecounter icon this will take moble users to a page with a life counter to use during games. use the element icons in the img folder it will also have a way for players to report thier games when on person reaches 0 in the counter a report icon will show up. when the player fillout out the report it will then send the oppont a convermationi"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Track Life During Game (Priority: P1)

A mobile user playing a Sorcery game needs to track their life total and their opponent's life total during gameplay. They navigate to the life counter from the main navigation and adjust life totals as the game progresses.

**Why this priority**: This is the core functionality - providing a convenient way for mobile users to track game state during matches. Without this, the feature has no value.

**Independent Test**: Can be fully tested by loading the life counter page on a mobile device, adjusting life totals up and down for both players, and verifying the display updates correctly. Delivers immediate value for casual game tracking.

**Acceptance Scenarios**:

1. **Given** a user is viewing the web app on a mobile device, **When** they tap the life counter icon in the top-right navigation bar, **Then** they are taken to a life counter page showing two player life totals
2. **Given** a user is on the life counter page, **When** they tap the increment/decrement buttons for their life total, **Then** their life value updates immediately and accurately
3. **Given** a user is on the life counter page, **When** they tap the increment/decrement buttons for opponent's life total, **Then** the opponent's life value updates immediately and accurately
4. **Given** a user is tracking life totals, **When** they tap on element icons, **Then** element-specific counters are displayed and can be adjusted independently
5. **Given** a user has adjusted life totals, **When** they navigate away and return to the life counter page, **Then** the life totals are preserved for the current session

---

### User Story 2 - Report Match Results (Priority: P2)

When a game ends (one player reaches 0 life), the winning player can submit a match report to record the result for ranking/statistics purposes. The system captures the essential match details and notifies the opponent to confirm.

**Why this priority**: This enables integration with the existing ELO system and match tracking, but the life counter is still useful without it for casual games.

**Independent Test**: Can be tested by reducing a player's life to 0, verifying the report button appears, filling out the match report form with winner/loser info, and confirming the report is submitted. Does not require opponent confirmation to test core flow.

**Acceptance Scenarios**:

1. **Given** a player's life total reaches 0, **When** the life counter page updates, **Then** a match report icon/button appears prominently on the screen
2. **Given** the match report button is visible, **When** the user taps it, **Then** a match report form is displayed
3. **Given** the user is viewing the match report form, **When** they enter the required match details (winner, loser) and optional details (deck links), **Then** they can submit the report
4. **Given** the user submits a match report, **When** the submission completes successfully, **Then** the system displays a confirmation message and indicates the report is pending opponent confirmation
5. **Given** a match report has been submitted, **When** the system processes it, **Then** the opponent receives a notification/confirmation request

---

### User Story 3 - Confirm Match Results (Priority: P3)

The opponent receives a match report confirmation request and can either confirm or dispute the reported results. This ensures both players agree on the match outcome before it affects rankings.

**Why this priority**: This adds validation to prevent false reports, but the system can function with auto-confirmation or admin review as fallback.

**Independent Test**: Can be tested by simulating a match report submission, viewing the confirmation request from the opponent's perspective, and confirming or disputing the result. Verifies the two-sided confirmation flow works end-to-end.

**Acceptance Scenarios**:

1. **Given** an opponent receives a match report confirmation request, **When** they view the request, **Then** they see the reported match details (players, life totals at end, submitted deck links if any)
2. **Given** the opponent is viewing a match report confirmation request, **When** they confirm the results, **Then** the match is recorded as official and ELO ratings are updated
3. **Given** the opponent is viewing a match report confirmation request, **When** they dispute the results, **Then** the match report is flagged for review and no rating changes occur
4. **Given** a match report has been submitted, **When** 24 hours pass without opponent response, **Then** the match is automatically confirmed and ratings are updated
5. **Given** a user has multiple pending match confirmations, **When** they view their notifications or match history, **Then** they can see all pending confirmation requests

---

### Edge Cases

- What happens when a user starts tracking a game, navigates away, and starts another game? Should the system support tracking multiple concurrent games?
- How does the system handle network connectivity issues during match report submission?
- What if both players' life totals reach 0 simultaneously (draw scenario)?
- How does the system handle users who repeatedly dispute legitimate match reports (abuse prevention)?
- What if a user wants to report a match that wasn't tracked with the life counter (manual match reporting)?
- Should the system support resetting the life counter to start a new game?
- What happens if the user accidentally taps the report button before the game is truly over?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display a life counter icon in the top-right of the mobile navigation bar, adjacent to the "Sorcerers Summit" title
- **FR-002**: System MUST render the life counter page with a mobile-optimized layout when the life counter icon is tapped
- **FR-003**: Life counter page MUST display two independent life total trackers (one for each player)
- **FR-004**: Each life total tracker MUST start at 20 by default and allow users to increment/decrement the value
- **FR-005**: System MUST display element icons (water, fire, earth, air) from the existing img folder for selecting player elements
- **FR-006**: System MUST provide additional counter types visible in the UI (dice counters, pyramid counters, etc.) for tracking other game resources
- **FR-007**: System MUST preserve life totals and counter values within the current browser session (session storage)
- **FR-008**: System MUST display a match report button when any player's life total reaches 0
- **FR-009**: Match report form MUST collect: winner name/ID, loser name/ID, optional deck links for both players
- **FR-010**: System MUST integrate with existing ELO system when match reports are confirmed
- **FR-011**: System MUST send a match confirmation request to the opponent when a match report is submitted; opponent may be identified via automatic lookup from recent LFG matches or manual entry
- **FR-012**: Opponent MUST be able to confirm or dispute match reports
- **FR-013**: System MUST automatically confirm match reports after 24 hours if opponent does not respond
- **FR-014**: System MUST prevent rating changes for disputed match reports until resolved
- **FR-015**: System MUST provide a way to reset the life counter to start tracking a new game
- **FR-016**: Mobile navigation MUST show active indicator when user is on the life counter page

### Key Entities *(include if feature involves data)*

- **Life Counter Session**: Represents an active game being tracked, contains current life totals for two players, element selections, and additional counter values; persists for browser session duration
- **Match Report**: Represents a completed game submission, contains winner/loser identifiers, final life totals, optional deck links, submission timestamp, and confirmation status
- **Confirmation Request**: Represents a pending opponent confirmation, contains reference to match report, opponent identifier, creation timestamp, and response status (pending/confirmed/disputed)
- **Player Element**: Represents element selection for each player (water, fire, earth, air), used for visual identification and potentially for tracking element-specific counters

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Mobile users can start tracking a game within 2 taps from any page on the website (tap navigation icon, tap life counter icon)
- **SC-002**: Life total adjustments register within 100ms of user tap (immediate visual feedback)
- **SC-003**: 90% of submitted match reports are confirmed within 24 hours (either by opponent or auto-confirmation)
- **SC-004**: Match report submission completes within 5 seconds on standard mobile network connection
- **SC-005**: Users can complete the full flow (start counter, track game, submit report) within 3 minutes for a typical game
- **SC-006**: Zero rating changes occur for disputed matches unless manually resolved by admin
- **SC-007**: Life counter page renders correctly on mobile devices with screen widths from 320px to 768px
- **SC-008**: 95% of users successfully locate and access the life counter on their first visit (discoverability)

## Assumptions *(document reasonable defaults)*

1. **Starting life total**: Defaulting to 20 based on Sorcery: Contested Realm standard rules
2. **Element icons**: Using existing element icon assets from web-app/static/img/ folder (water, fire, earth, air)
3. **Integration pattern**: Integrating with existing match reporting infrastructure in web-app/services/match.py and web-app/repositories/matches.py
4. **Mobile breakpoint**: Treating screen widths ≤ 768px as "mobile view" for displaying the life counter icon
5. **Opponent identification**: System will support both automatic lookup from recent LFG matches AND manual opponent entry for flexibility
6. **Session persistence**: Life counter values persist only for current browser session (not stored in database) to keep feature lightweight
7. **Notification method**: Match confirmation requests delivered via existing notification system (in-app notifications, potentially Discord DM if user is linked)
8. **Authentication**: Users must be logged in via Discord OAuth to submit match reports (consistent with existing web app auth)
9. **Counter types**: Supporting life total counter (primary) plus 4 element counters and 2-3 additional utility counters based on UI mockup
10. **Draw handling**: If both players reach 0 simultaneously, match report allows selecting "Draw" as outcome (no winner/loser)

## Out of Scope

- Desktop/tablet version of the life counter (feature is explicitly mobile-only per requirement)
- Real-time synchronization between opponent devices (both players use their own device to track)
- Historical life total tracking (showing life changes over time during a game)
- Voice commands for adjusting life totals
- Integration with streaming/recording features
- Spectator mode for viewing other players' life counters
- Tournament-specific features (pairings, standings integration)
- Life counter themes or customization options
- Sound effects for life total changes
- Undo/redo functionality for counter adjustments
