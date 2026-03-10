# Feature Specification: Web-Based Match Reporting Modal

**Feature Branch**: `001-web-match-report-modal`
**Created**: 2026-03-10
**Status**: Draft
**Input**: User description: "Web-based match reporting modal with buttons for win/loss reporting, turn order selection, and match confirmation"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Report Match Victory (Priority: P1)

A player who just completed a match wants to report their victory through the website, providing all necessary match details including opponent, deck information, and turn order.

**Why this priority**: This is the core functionality - enabling players to report match results. Without this, no match data can be captured via the web interface.

**Independent Test**: Can be fully tested by logging into the website, opening the match report modal, selecting an opponent, entering a valid deck URL, choosing turn order, and clicking "I Won". The system should save the pending match report.

**Acceptance Scenarios**:

1. **Given** user is logged into the website, **When** they open the match report modal, select an opponent, enter a valid deck URL, choose "First" for turn order, and click "I Won", **Then** the system creates a pending match report marked as a win for the user
2. **Given** user has filled out all required fields, **When** they click "I Won", **Then** the modal closes and displays a success message indicating the report is awaiting confirmation
3. **Given** user is submitting a match report, **When** the submission is in progress, **Then** all action buttons are disabled and a loading indicator is shown

---

### User Story 2 - Report Match Loss (Priority: P1)

A player who lost a match wants to report the loss accurately through the website, providing match details and acknowledging their defeat.

**Why this priority**: Equally critical as victory reporting - players need to be able to report losses to maintain match integrity and complete records.

**Independent Test**: Can be fully tested by logging into the website, opening the match report modal, selecting an opponent, entering a valid deck URL, choosing turn order, and clicking "I Lost". The system should save the pending match report with the opponent as winner.

**Acceptance Scenarios**:

1. **Given** user is logged into the website, **When** they open the match report modal, select an opponent, enter a valid deck URL, choose "Second" for turn order, and click "I Lost", **Then** the system creates a pending match report marked as a win for the opponent
2. **Given** user has submitted a loss report, **When** the submission completes, **Then** the modal closes and displays a success message indicating the report is awaiting confirmation

---

### User Story 3 - Confirm Opponent's Match Report (Priority: P2)

A player receives notification that their opponent has reported a match result and needs to confirm or deny the accuracy of that report.

**Why this priority**: Essential for match validation and preventing fraudulent reports, but depends on P1 stories existing first.

**Independent Test**: Can be fully tested by having an opponent submit a match report, then logging in to see a pending confirmation request, and clicking either "Confirm" or "Deny". The system should finalize or reject the match accordingly.

**Acceptance Scenarios**:

1. **Given** opponent has submitted a match report claiming they won, **When** user opens the confirmation modal and reviews the details (opponent name, deck, turn order, result), **Then** user can see all submitted match information
2. **Given** user is reviewing a match confirmation request, **When** they click "Confirm", **Then** the match is finalized in the system, ELO ratings are updated, and both players receive confirmation
3. **Given** user is reviewing a match confirmation request, **When** they click "Deny", **Then** the match report is rejected, no ELO changes occur, and both players are notified of the denial
4. **Given** user confirms a match, **When** the confirmation completes, **Then** the modal closes and displays a "Match confirmed!" toast message
5. **Given** user denies a match, **When** the denial completes, **Then** the modal closes and displays a "Match report denied." toast message

---

### User Story 4 - Cancel Match Report (Priority: P3)

A player starts filling out a match report but realizes they need to cancel or made a mistake before submitting.

**Why this priority**: Quality of life feature that prevents accidental submissions, but not critical for core functionality.

**Independent Test**: Can be fully tested by opening the match report modal, partially filling out fields, and clicking either the "Cancel" button or the X close button. No match report should be created.

**Acceptance Scenarios**:

1. **Given** user is filling out a match report, **When** they click the "Cancel" button, **Then** the modal closes without saving any data
2. **Given** user is filling out a match report, **When** they click the X button in the modal header, **Then** the modal closes without saving any data
3. **Given** user has partially filled out the form, **When** they cancel, **Then** no validation errors are shown and form data is discarded

---

### Edge Cases

- What happens when user tries to submit a match report without selecting an opponent?
  - Action buttons ("I Won", "I Lost") are disabled until opponent is selected
- What happens when user enters an invalid deck URL?
  - Action buttons are disabled and validation error is shown below the deck URL field
- What happens when user tries to submit without selecting turn order?
  - Action buttons ("I Won", "I Lost") are disabled until turn order is selected (required field)
- What happens when the opponent never responds to a confirmation request?
  - After 24 hours, system sends a reminder notification to the opponent
  - After 48 hours total, the pending report automatically expires and is marked as void with no ELO changes
- What happens when both players try to report the same match simultaneously?
  - System should detect duplicate pending reports and either merge them or show a warning
- What happens when a user tries to report a match against themselves?
  - System should prevent selecting own name as opponent with validation error
- What happens if the API call fails during submission?
  - Loading state ends, error message is displayed, and user can retry submission

## Requirements *(mandatory)*

### Functional Requirements

**Match Report Modal - UI Components**:

- **FR-001**: System MUST display a Match Report Modal with clearly labeled input fields for opponent selection, deck URL, and turn order
- **FR-002**: System MUST provide a Cancel button (small size, gray color scheme, ghost variant) that closes the modal without saving data
- **FR-003**: System MUST provide an "I Lost" button (small size, red color scheme, solid variant) that submits the match report claiming opponent victory
- **FR-004**: System MUST provide an "I Won" button (small size, green color scheme, solid variant) that submits the match report claiming user victory
- **FR-005**: System MUST provide turn order toggle buttons ("First" and "Second") in a button group, with blue color when selected and gray when not selected
- **FR-006**: System MUST provide a close button (X) in the modal header that closes the modal without saving data
- **FR-007**: System MUST use translation keys for all button text to support internationalization ('cancel', 'matchReportLost', 'matchReportWon', 'matchReportFirst', 'matchReportSecond')

**Match Report Modal - Validation & State Management**:

- **FR-008**: System MUST disable "I Lost" and "I Won" buttons when no opponent is selected
- **FR-009**: System MUST disable "I Lost" and "I Won" buttons when deck URL is invalid
- **FR-010**: System MUST disable "I Lost" and "I Won" buttons when turn order is not selected (required field)
- **FR-011**: System MUST disable "I Lost" and "I Won" buttons when a loading state is active (submission in progress)
- **FR-012**: System MUST validate deck URL format and display appropriate error messages for invalid URLs
- **FR-013**: System MUST show a loading indicator during match report submission
- **FR-014**: System MUST prevent users from selecting themselves as the opponent
- **FR-015**: System MUST require turn order selection (First or Second) before allowing match report submission

**Match Report Submission**:

- **FR-016**: System MUST save match report with the following data: reporter user ID, opponent user ID, result (win/loss from reporter perspective), deck URL, turn order, timestamp
- **FR-017**: System MUST create match reports in a "pending confirmation" state awaiting opponent approval
- **FR-018**: System MUST close the modal and display a success message after successful submission
- **FR-019**: System MUST handle submission failures gracefully with error messages and allow retry

**Match Confirmation Modal - UI Components**:

- **FR-020**: System MUST display a Match Confirmation Modal showing pending match reports requiring user confirmation
- **FR-021**: System MUST display all match details in the confirmation modal: opponent name, reported result, deck URL, turn order
- **FR-022**: System MUST provide a Deny button that rejects the opponent's match report
- **FR-023**: System MUST provide a Confirm/Accept button that approves the opponent's match report
- **FR-024**: System MUST use translation keys for confirmation buttons ('matchConfirmDeny', 'matchConfirmAccept')

**Match Confirmation Processing**:

- **FR-025**: System MUST finalize the match when user confirms, applying ELO rating changes and marking the match as completed
- **FR-026**: System MUST reject the match report when user denies, removing it from pending state with no ELO changes
- **FR-027**: System MUST display "Match confirmed!" toast message after successful confirmation
- **FR-028**: System MUST display "Match report denied." toast message after denial
- **FR-029**: System MUST notify both players of match confirmation or denial outcomes
- **FR-030**: System MUST prevent double-submission of confirmations (disable buttons after first click)

**Pending Report Expiration**:

- **FR-031**: System MUST send a reminder notification to the opponent 24 hours after match report submission if not yet confirmed or denied
- **FR-032**: System MUST automatically expire pending match reports 48 hours after submission if no action is taken
- **FR-033**: System MUST mark expired reports as void with no ELO changes applied
- **FR-034**: System MUST notify both players when a match report expires due to timeout

**Data Integrity**:

- **FR-035**: System MUST detect duplicate match reports for the same game and handle appropriately
- **FR-036**: System MUST ensure atomic operations for ELO updates when matches are confirmed
- **FR-037**: System MUST log all match report submissions, confirmations, denials, and expirations for audit purposes

### Key Entities

- **Match Report**: Represents a submitted match result awaiting confirmation
  - Attributes: reporter, opponent, result (win/loss from reporter perspective), deck URL, turn order (first/second), timestamp, status (pending/confirmed/denied)
  - Relationships: Links to two Player entities (reporter and opponent)

- **Player**: Represents a user who can report and confirm matches
  - Attributes: user ID, username/display name, current ELO rating
  - Relationships: Can have multiple Match Reports as reporter or opponent

- **Match**: Represents a finalized, confirmed match with ELO changes applied
  - Attributes: player 1, player 2, winner, loser, player 1 deck URL, player 2 deck URL, turn order, timestamp, ELO changes
  - Relationships: Created from a confirmed Match Report

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can submit a complete match report in under 60 seconds from opening the modal
- **SC-002**: 95% of match reports include valid deck URLs and all required fields
- **SC-003**: Match confirmation or denial occurs within 24 hours for 80% of submitted reports (before first reminder)
- **SC-003a**: Less than 10% of match reports expire due to timeout (48-hour limit)
- **SC-004**: Zero duplicate or invalid match records are created in the database (data integrity maintained)
- **SC-005**: Users successfully complete the match reporting flow on first attempt 90% of the time
- **SC-006**: All UI components render correctly and are accessible on desktop and mobile devices
- **SC-007**: System handles concurrent match report submissions without race conditions or data corruption
- **SC-008**: Translation keys properly support all UI text in multiple languages

## Assumptions *(mandatory)*

1. Users are already authenticated before accessing the match report modal
2. Deck URL validation follows standard URL format (http/https) and may optionally verify against Curiosa API
3. Turn order is required information for all match reports - users must explicitly select "First" or "Second"
4. Opponent selection is done via dropdown or search field populated from active players
5. The system follows the existing Discord bot match reporting flow but adapts it for web UI
6. ELO rating calculation follows existing system rules when matches are confirmed
7. Users can only have one pending match report with the same opponent at a time
8. The modal uses Chakra UI component library based on the component types mentioned (ButtonGroup, ModalCloseButton, toast)
9. Pending match reports expire after 48 hours if not confirmed or denied, with a reminder sent at 24 hours
10. The notification system can deliver reminders and expiration notices to users

## Out of Scope *(mandatory)*

- Editing or canceling match reports after submission (before confirmation)
- Bulk match reporting (multiple matches at once)
- Automated match result detection or integration with game platforms
- Detailed match statistics beyond winner/loser and turn order
- Spectator or third-party match reporting
- Match replays or game history viewing (this is only for reporting)
- Integration with tournament brackets or event systems
- Admin override or forced match confirmations

## Dependencies

- **Authentication System**: Users must be logged in to report matches
- **Player Database**: Active player list must be available for opponent selection
- **ELO Rating System**: Must integrate with existing ELO calculation service
- **Deck Validation API**: Curiosa API integration for deck URL validation (if required)
- **Notification System**: To alert opponents of pending confirmation requests
- **Translation System**: i18n keys must be available for all UI text
- **Chakra UI Library**: UI components depend on Chakra UI being installed and configured
