/**
 * Life Counter JavaScript - State Management and UI Logic
 * User Story 1: Track Life During Game
 */

// ==================== State Management ====================

const LifeCounterState = {
  /**
   * Load state from sessionStorage or return default state
   */
  load: function () {
    const stored = sessionStorage.getItem("lifeCounterState");
    if (stored) {
      try {
        return JSON.parse(stored);
      } catch (e) {
        console.error("Failed to parse stored state:", e);
        return this.getDefaultState();
      }
    }
    return this.getDefaultState();
  },

  /**
   * Save state to sessionStorage (debounced)
   */
  save: function (state) {
    try {
      sessionStorage.setItem("lifeCounterState", JSON.stringify(state));
    } catch (e) {
      console.error("Failed to save state:", e);
    }
  },

  /**
   * Clear state from sessionStorage
   */
  reset: function () {
    sessionStorage.removeItem("lifeCounterState");
  },

  /**
   * Get default state object
   */
  getDefaultState: function () {
    return {
      version: "1.0",
      timestamp: Date.now(),
      players: {
        player1: {
          name: "Player 1",
          life: 20,
          threshold: {
            water: 0,
            fire: 0,
            earth: 0,
            air: 0,
          },
        },
        player2: {
          name: "Player 2",
          life: 20,
          threshold: {
            water: 0,
            fire: 0,
            earth: 0,
            air: 0,
          },
        },
      },
      lifeHistory: [], // Track life changes over time
      matchStartedAt: Date.now(),
      lastModified: Date.now(),
    };
  },
};

// ==================== Debouncing ====================

let saveTimeout = null;
const SAVE_DEBOUNCE_MS = 500;

function debouncedSave(state) {
  if (saveTimeout) {
    clearTimeout(saveTimeout);
  }
  saveTimeout = setTimeout(() => {
    LifeCounterState.save(state);
  }, SAVE_DEBOUNCE_MS);
}

// ==================== Core State Updates ====================

let currentState = LifeCounterState.load();

function updateLife(player, amount) {
  const oldLife = currentState.players[player].life;
  currentState.players[player].life += amount;

  // Don't allow life to go below 0
  if (currentState.players[player].life < 0) {
    currentState.players[player].life = 0;
  }

  const newLife = currentState.players[player].life;

  // Record life change in history (only if life actually changed)
  if (oldLife !== newLife) {
    if (!currentState.lifeHistory) {
      currentState.lifeHistory = [];
    }
    currentState.lifeHistory.push({
      timestamp: Date.now(),
      player: player,
      oldLife: oldLife,
      newLife: newLife,
      change: amount
    });
  }

  currentState.lastModified = Date.now();
  debouncedSave(currentState);
  renderUI(currentState);
  checkForGameEnd(currentState);

  // Haptic feedback (if supported)
  if (navigator.vibrate) {
    navigator.vibrate(50);
  }
}

function updateThresholdElement(player, element, amount) {
  const oldValue = currentState.players[player].threshold[element];
  currentState.players[player].threshold[element] += amount;

  // Don't allow negative counters
  if (currentState.players[player].threshold[element] < 0) {
    currentState.players[player].threshold[element] = 0;
  }

  const newValue = currentState.players[player].threshold[element];
  console.log(`[LifeCounter] Updated ${player} ${element}: ${oldValue} → ${newValue}`);

  currentState.lastModified = Date.now();
  debouncedSave(currentState);
  renderUI(currentState);

  // Haptic feedback (if supported)
  if (navigator.vibrate) {
    navigator.vibrate(30);
  }
}

function resetCounter() {
  if (confirm("Reset life counter and start a new game?")) {
    LifeCounterState.reset();
    currentState = LifeCounterState.getDefaultState();
    renderUI(currentState);

    // Hide report button if visible
    const reportBtn = document.getElementById("report-match-btn");
    if (reportBtn) {
      reportBtn.classList.add("hidden");
    }
  }
}

// ==================== UI Rendering ====================

function renderUI(state) {
  // Render life values
  ["player1", "player2"].forEach((player) => {
    const lifeValueEl = document.querySelector(
      `.life-value[data-player="${player}"]`
    );
    if (lifeValueEl) {
      const life = state.players[player].life;

      // Show "DD" when life is 0, otherwise show the number
      if (life === 0) {
        lifeValueEl.textContent = "DD";
      } else {
        lifeValueEl.textContent = life;
      }

      // Apply color classes based on life total
      lifeValueEl.classList.remove("critical", "low", "high");
      if (life === 0) {
        lifeValueEl.classList.add("critical");
      } else if (life <= 5) {
        lifeValueEl.classList.add("low");
      } else if (life >= 30) {
        lifeValueEl.classList.add("high");
      }
    }

    // Render threshold element counters - just show the number
    ["water", "fire", "earth", "air"].forEach((element) => {
      const elementCounterEl = document.querySelector(
        `.element-counter-value[data-player="${player}"][data-element="${element}"]`
      );
      if (elementCounterEl) {
        const value = state.players[player].threshold[element];
        elementCounterEl.textContent = value;
      }
    });
  });
}


function checkForGameEnd(state) {
  const reportBtn = document.getElementById("report-match-btn");
  if (!reportBtn) return;

  // Show report button if either player has 0 or less life
  const player1Life = state.players.player1.life;
  const player2Life = state.players.player2.life;

  if (player1Life <= 0 || player2Life <= 0) {
    reportBtn.classList.remove("hidden");
  } else {
    reportBtn.classList.add("hidden");
  }
}

// ==================== Event Handlers ====================

function initializeEventListeners() {
  // Life buttons
  document.querySelectorAll(".life-btn").forEach((btn) => {
    btn.addEventListener("click", function () {
      const player = this.dataset.player;
      const amount = parseInt(this.dataset.amount);
      const isIncrement = this.classList.contains("increment");
      const finalAmount = isIncrement ? amount : -amount;
      updateLife(player, finalAmount);
    });
  });

  // Threshold element counter buttons
  const elementButtons = document.querySelectorAll(".element-decrement, .element-increment");
  console.log(`[LifeCounter] Found ${elementButtons.length} element counter buttons`);

  elementButtons.forEach((btn, index) => {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();

      const player = this.dataset.player;
      const element = this.dataset.element;
      const isIncrement = this.classList.contains("element-increment");
      const amount = isIncrement ? 1 : -1;

      console.log(`[LifeCounter] Button clicked: player=${player}, element=${element}, amount=${amount}`);
      updateThresholdElement(player, element, amount);
    });
  });

  // Reset button
  const resetBtn = document.getElementById("reset-btn");
  if (resetBtn) {
    resetBtn.addEventListener("click", resetCounter);
  }

  // Fullscreen button
  const fullscreenBtn = document.getElementById("fullscreen-btn");
  if (fullscreenBtn) {
    fullscreenBtn.addEventListener("click", toggleFullscreen);
  }

  // Report match button (functionality for US2)
  const reportBtn = document.getElementById("report-match-btn");
  if (reportBtn) {
    reportBtn.addEventListener("click", function () {
      showMatchReportModal();
    });
  }

  // Modal close buttons
  document.querySelectorAll(".modal-close").forEach((btn) => {
    btn.addEventListener("click", function () {
      const modal = this.closest(".modal");
      if (modal) {
        modal.classList.add("hidden");
      }
    });
  });

  // Close modal on background click
  document.querySelectorAll(".modal").forEach((modal) => {
    modal.addEventListener("click", function (e) {
      if (e.target === this) {
        this.classList.add("hidden");
      }
    });
  });
}

// ==================== Match Reporting (US1 & US2) ====================

let opponentSearchTimeout = null;
const SEARCH_DEBOUNCE_MS = 300;

function showMatchReportModal() {
  // Check if user is logged in
  if (!window.LOGGED_IN) {
    alert("You must be logged in to report matches. Please log in with Discord or Google.");
    return;
  }

  const modal = document.getElementById("match-report-modal");
  if (!modal) return;

  // Populate match summary
  const summaryEl = document.getElementById("match-summary-text");
  const player1Life = currentState.players.player1.life;
  const player2Life = currentState.players.player2.life;

  let winner = "";
  if (player1Life <= 0 && player2Life <= 0) {
    winner = "Draw";
  } else if (player1Life <= 0) {
    winner = "You lost";
  } else {
    winner = "You won";
  }

  if (summaryEl) {
    summaryEl.textContent = `${winner}! Your life: ${player1Life}, Opponent's life: ${player2Life}`;
  }

  // Auto-fill final life totals
  document.getElementById("final-life-submitter").value = player1Life;
  document.getElementById("final-life-opponent").value = player2Life;

  // Reset form state
  resetMatchReportForm();

  // Show modal
  modal.classList.remove("hidden");

  // Focus on opponent search
  setTimeout(() => {
    document.getElementById("opponent-search")?.focus();
  }, 100);
}

function resetMatchReportForm() {
  // Reset all form inputs
  document.getElementById("opponent-search").value = "";
  document.getElementById("opponent-user-id").value = "";
  document.getElementById("submitter-deck-url").value = "";
  document.getElementById("went-first").value = "";
  document.getElementById("match-type").value = "ranked";

  // Hide selected opponent display
  document.getElementById("opponent-selected").classList.add("hidden");

  // Hide autocomplete
  document.getElementById("opponent-autocomplete").classList.add("hidden");

  // Reset match type buttons (default to ranked)
  document.querySelectorAll("#match-type-group .btn-toggle").forEach(btn => {
    btn.classList.remove("active");
  });
  document.getElementById("match-type-ranked-btn").classList.add("active");

  // Reset turn order buttons
  document.querySelectorAll("#turn-order-group .btn-toggle").forEach(btn => {
    btn.classList.remove("active");
  });

  // Disable submit buttons
  document.getElementById("report-win-btn").disabled = true;
  document.getElementById("report-loss-btn").disabled = true;

  // Hide alerts
  document.getElementById("match-report-success").classList.add("hidden");
  document.getElementById("match-report-error").classList.add("hidden");
  document.getElementById("match-report-loading").classList.add("hidden");
}

// ==================== Opponent Autocomplete ====================

async function searchOpponents(query) {
  if (!query || query.length < 2) {
    document.getElementById("opponent-autocomplete").classList.add("hidden");
    return;
  }

  try {
    const response = await fetch(`/api/match-report/search-opponents?q=${encodeURIComponent(query)}&limit=10`);
    const data = await response.json();

    if (!response.ok) {
      console.error("Opponent search failed:", data.error);
      return;
    }

    displayOpponentResults(data.opponents);
  } catch (error) {
    console.error("Error searching opponents:", error);
  }
}

function displayOpponentResults(opponents) {
  const dropdown = document.getElementById("opponent-autocomplete");

  if (!opponents || opponents.length === 0) {
    dropdown.innerHTML = '<div class="autocomplete-empty">No opponents found</div>';
    dropdown.classList.remove("hidden");
    return;
  }

  dropdown.innerHTML = opponents.map(opponent => `
    <div class="autocomplete-item" data-user-id="${opponent.user_id}">
      <span class="autocomplete-item-name">${opponent.display_name}</span>
      ${opponent.is_recent ? '<span class="autocomplete-item-badge">Recent</span>' : ''}
    </div>
  `).join('');

  dropdown.classList.remove("hidden");

  // Add click handlers to autocomplete items
  dropdown.querySelectorAll(".autocomplete-item").forEach(item => {
    item.addEventListener("click", function() {
      selectOpponent({
        user_id: this.dataset.userId,
        display_name: this.querySelector(".autocomplete-item-name").textContent
      });
    });
  });
}

function selectOpponent(opponent) {
  // Set hidden field
  document.getElementById("opponent-user-id").value = opponent.user_id;

  // Clear search input
  document.getElementById("opponent-search").value = "";

  // Hide autocomplete
  document.getElementById("opponent-autocomplete").classList.add("hidden");

  // Show selected opponent display
  const selectedDisplay = document.getElementById("opponent-selected");
  document.getElementById("opponent-name").textContent = opponent.display_name;
  selectedDisplay.classList.remove("hidden");

  // Validate form (enable submit buttons if valid)
  validateMatchReportForm();
}

function clearOpponent() {
  document.getElementById("opponent-user-id").value = "";
  document.getElementById("opponent-selected").classList.add("hidden");
  validateMatchReportForm();
}

// ==================== Match Type Toggle ====================

function initializeMatchTypeToggle() {
  const toggleButtons = document.querySelectorAll("#match-type-group .btn-toggle");

  toggleButtons.forEach(btn => {
    btn.addEventListener("click", function() {
      // Remove active class from all buttons
      toggleButtons.forEach(b => b.classList.remove("active"));

      // Add active class to clicked button
      this.classList.add("active");

      // Set hidden field value
      document.getElementById("match-type").value = this.dataset.value;

      // Validate form
      validateMatchReportForm();
    });
  });
}

// ==================== Turn Order Toggle ====================

function initializeTurnOrderToggle() {
  const toggleButtons = document.querySelectorAll("#turn-order-group .btn-toggle");

  toggleButtons.forEach(btn => {
    btn.addEventListener("click", function() {
      // Remove active class from all buttons
      toggleButtons.forEach(b => b.classList.remove("active"));

      // Add active class to clicked button
      this.classList.add("active");

      // Set hidden field value
      document.getElementById("went-first").value = this.dataset.value;

      // Validate form
      validateMatchReportForm();
    });
  });
}

// ==================== Form Validation ====================

function validateMatchReportForm() {
  const opponentSelected = !!document.getElementById("opponent-user-id").value;
  const turnOrderSelected = !!document.getElementById("went-first").value;
  const submitterDeckUrl = document.getElementById("submitter-deck-url").value.trim();

  // Deck URL is now REQUIRED and must match Curiosa.io format (supports http/https, www, query params)
  const deckUrlPattern = /^https?:\/\/(www\.)?curiosa\.io\/decks\/[a-zA-Z0-9_-]+(\?.*)?$/;
  const deckUrlProvided = !!submitterDeckUrl;
  const deckUrlValid = deckUrlProvided && deckUrlPattern.test(submitterDeckUrl);

  // Show/hide deck URL error message
  const deckUrlError = document.getElementById("deck-url-error");
  const deckUrlInput = document.getElementById("submitter-deck-url");

  if (submitterDeckUrl && !deckUrlValid) {
    deckUrlError.classList.remove("hidden");
    deckUrlInput.classList.add("invalid");
  } else {
    deckUrlError.classList.add("hidden");
    deckUrlInput.classList.remove("invalid");
  }

  // Enable submit buttons only if all required fields are valid
  const isValid = opponentSelected && turnOrderSelected && deckUrlValid;

  document.getElementById("report-win-btn").disabled = !isValid;
  document.getElementById("report-loss-btn").disabled = !isValid;

  return isValid;
}

// ==================== Form Submission ====================

async function submitMatchReport(result) {
  // Show loading indicator
  document.getElementById("match-report-loading").classList.remove("hidden");
  document.getElementById("match-report-success").classList.add("hidden");
  document.getElementById("match-report-error").classList.add("hidden");

  // Disable buttons during submission
  document.getElementById("report-win-btn").disabled = true;
  document.getElementById("report-loss-btn").disabled = true;
  document.getElementById("cancel-report-btn").disabled = true;

  // Build request payload
  const payload = {
    opponent_user_id: document.getElementById("opponent-user-id").value,
    result: result,
    went_first: document.getElementById("went-first").value,
    submitter_deck_url: document.getElementById("submitter-deck-url").value || null,
    final_life_submitter: parseInt(document.getElementById("final-life-submitter").value),
    final_life_opponent: parseInt(document.getElementById("final-life-opponent").value),
    match_type: document.getElementById("match-type").value || "ranked"
  };

  try {
    const response = await fetch("/api/match-report/submit", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    const data = await response.json();

    // Hide loading indicator
    document.getElementById("match-report-loading").classList.add("hidden");

    if (!response.ok) {
      // Show error message
      const errorEl = document.getElementById("match-report-error");
      errorEl.textContent = data.error?.message || "Failed to submit match report. Please try again.";
      errorEl.classList.remove("hidden");

      // Re-enable buttons
      document.getElementById("cancel-report-btn").disabled = false;
      validateMatchReportForm();
      return;
    }

    // Success!
    const successEl = document.getElementById("match-report-success");
    const opponentName = document.getElementById("opponent-name").textContent;
    successEl.textContent = `Match report submitted! Waiting for ${opponentName} to confirm. (Expires in 48 hours)`;
    successEl.classList.remove("hidden");

    // Close modal after 3 seconds
    setTimeout(() => {
      document.getElementById("match-report-modal").classList.add("hidden");

      // Reset the life counter state (new game)
      resetCounter();
    }, 3000);

  } catch (error) {
    console.error("Error submitting match report:", error);

    // Hide loading indicator
    document.getElementById("match-report-loading").classList.add("hidden");

    // Show error message
    const errorEl = document.getElementById("match-report-error");
    errorEl.textContent = "Network error. Please check your connection and try again.";
    errorEl.classList.remove("hidden");

    // Re-enable buttons
    document.getElementById("cancel-report-btn").disabled = false;
    validateMatchReportForm();
  }
}

// ==================== Match Report Event Listeners ====================

function initializeMatchReportListeners() {
  // Opponent search autocomplete
  const opponentSearch = document.getElementById("opponent-search");
  if (opponentSearch) {
    opponentSearch.addEventListener("input", function() {
      const query = this.value.trim();

      // Debounce search
      if (opponentSearchTimeout) {
        clearTimeout(opponentSearchTimeout);
      }

      if (query.length < 2) {
        document.getElementById("opponent-autocomplete").classList.add("hidden");
        return;
      }

      opponentSearchTimeout = setTimeout(() => {
        searchOpponents(query);
      }, SEARCH_DEBOUNCE_MS);
    });

    // Hide autocomplete when clicking outside
    document.addEventListener("click", function(e) {
      if (!opponentSearch.contains(e.target) && !document.getElementById("opponent-autocomplete").contains(e.target)) {
        document.getElementById("opponent-autocomplete").classList.add("hidden");
      }
    });
  }

  // Clear opponent button
  const clearOpponentBtn = document.getElementById("opponent-clear");
  if (clearOpponentBtn) {
    clearOpponentBtn.addEventListener("click", clearOpponent);
  }

  // Match type toggle
  initializeMatchTypeToggle();

  // Turn order toggle
  initializeTurnOrderToggle();

  // Deck URL validation (on input)
  const submitterDeckUrl = document.getElementById("submitter-deck-url");

  if (submitterDeckUrl) {
    submitterDeckUrl.addEventListener("input", validateMatchReportForm);
  }

  // Cancel button
  const cancelBtn = document.getElementById("cancel-report-btn");
  if (cancelBtn) {
    cancelBtn.addEventListener("click", function() {
      document.getElementById("match-report-modal").classList.add("hidden");
    });
  }

  // Form submission (I Won / I Lost buttons)
  const matchReportForm = document.getElementById("match-report-form");
  if (matchReportForm) {
    matchReportForm.addEventListener("submit", function(e) {
      e.preventDefault();

      // Determine which button was clicked
      const submitter = document.activeElement;
      const result = submitter.dataset.result;

      if (result) {
        submitMatchReport(result);
      }
    });
  }

  // Direct button click handlers (alternative to form submit)
  const reportWinBtn = document.getElementById("report-win-btn");
  const reportLossBtn = document.getElementById("report-loss-btn");

  if (reportWinBtn) {
    reportWinBtn.addEventListener("click", function(e) {
      e.preventDefault();
      submitMatchReport("won");
    });
  }

  if (reportLossBtn) {
    reportLossBtn.addEventListener("click", function(e) {
      e.preventDefault();
      submitMatchReport("lost");
    });
  }
}

// ==================== Confirmation Modal (US3) ====================

let pendingConfirmations = [];
let currentConfirmation = null;
let pollInterval = null;
const POLL_INTERVAL_MS = 30000; // 30 seconds

async function fetchPendingConfirmations() {
  try {
    const response = await fetch("/api/match-report/pending");
    const data = await response.json();

    if (!response.ok) {
      console.error("Failed to fetch pending confirmations:", data.error);
      return;
    }

    pendingConfirmations = data.pending_confirmations || [];
    displayPendingConfirmationsList();

    // Show modal if there are pending confirmations
    if (pendingConfirmations.length > 0) {
      const modal = document.getElementById("confirmation-modal");
      if (modal && modal.classList.contains("hidden")) {
        modal.classList.remove("hidden");
      }
    }

  } catch (error) {
    console.error("Error fetching pending confirmations:", error);
  }
}

function displayPendingConfirmationsList() {
  const listContainer = document.getElementById("pending-confirmations-list");

  if (!pendingConfirmations || pendingConfirmations.length === 0) {
    listContainer.innerHTML = '<p class="text-muted loading-text">No pending confirmations.</p>';
    return;
  }

  listContainer.innerHTML = pendingConfirmations.map(conf => {
    const submitterName = conf.submitter_display_name || "Unknown Player";
    const expiresIn = formatTimeRemaining(conf.expires_at);

    // Determine who won
    const youWon = conf.winner_discord_id == conf.opponent_discord_id;
    const resultText = youWon ? "You won" : "You lost";

    return `
      <div class="pending-confirmation-item" data-confirmation-id="${conf.id}">
        <div class="pending-confirmation-info">
          <span class="pending-confirmation-name">${submitterName}</span>
          <span class="pending-confirmation-summary">${resultText} • Expires ${expiresIn}</span>
        </div>
        <span class="pending-confirmation-badge">Pending</span>
      </div>
    `;
  }).join('');

  // Add click handlers
  listContainer.querySelectorAll(".pending-confirmation-item").forEach(item => {
    item.addEventListener("click", function() {
      const confirmationId = parseInt(this.dataset.confirmationId);
      showConfirmationDetails(confirmationId);
    });
  });
}

function showConfirmationDetails(confirmationId) {
  const confirmation = pendingConfirmations.find(c => c.id === confirmationId);

  if (!confirmation) {
    console.error("Confirmation not found:", confirmationId);
    return;
  }

  currentConfirmation = confirmation;

  // Populate confirmation details
  const submitterName = confirmation.submitter_display_name || "Unknown Player";

  document.getElementById("confirmation-submitter-name").textContent = submitterName;

  // Determine who won
  const youWon = confirmation.winner_discord_id == confirmation.opponent_discord_id;
  const resultText = youWon
    ? `${submitterName} reported that you won`
    : `${submitterName} reported that they won`;

  document.getElementById("confirmation-result").textContent = resultText;

  // Final life
  document.getElementById("confirmation-final-life").textContent =
    `Winner: ${confirmation.final_life_winner} | Loser: ${confirmation.final_life_loser}`;

  // Who went first
  const wentFirst = confirmation.went_first === "submitter" ? submitterName : "You";
  document.getElementById("confirmation-went-first").textContent = wentFirst;

  // Deck URLs
  const winnerDeckRow = document.getElementById("confirmation-deck-row-winner");
  const loserDeckRow = document.getElementById("confirmation-deck-row-loser");

  if (confirmation.winner_deck_url) {
    document.getElementById("confirmation-deck-winner").href = confirmation.winner_deck_url;
    winnerDeckRow.classList.remove("hidden");
  } else {
    winnerDeckRow.classList.add("hidden");
  }

  if (confirmation.loser_deck_url) {
    document.getElementById("confirmation-deck-loser").href = confirmation.loser_deck_url;
    loserDeckRow.classList.remove("hidden");
  } else {
    loserDeckRow.classList.add("hidden");
  }

  // Expires in
  document.getElementById("confirmation-expires").textContent = formatTimeRemaining(confirmation.expires_at);

  // Hide alerts
  document.getElementById("confirmation-success").classList.add("hidden");
  document.getElementById("confirmation-error").classList.add("hidden");
  document.getElementById("confirmation-loading").classList.add("hidden");

  // Hide list, show details
  document.getElementById("pending-confirmations-list").classList.add("hidden");
  document.getElementById("confirmation-details").classList.remove("hidden");
}

function formatTimeRemaining(expiresAt) {
  const now = Math.floor(Date.now() / 1000);
  const remaining = expiresAt - now;

  if (remaining <= 0) {
    return "expired";
  }

  const hours = Math.floor(remaining / 3600);
  const minutes = Math.floor((remaining % 3600) / 60);

  if (hours > 24) {
    const days = Math.floor(hours / 24);
    return `in ${days} day${days > 1 ? 's' : ''}`;
  } else if (hours > 0) {
    return `in ${hours} hour${hours > 1 ? 's' : ''}`;
  } else {
    return `in ${minutes} minute${minutes > 1 ? 's' : ''}`;
  }
}

async function confirmMatch() {
  if (!currentConfirmation) return;

  // Show loading
  document.getElementById("confirmation-loading").classList.remove("hidden");
  document.getElementById("confirmation-success").classList.add("hidden");
  document.getElementById("confirmation-error").classList.add("hidden");

  // Disable buttons
  document.getElementById("confirm-match-btn").disabled = true;
  document.getElementById("deny-match-btn").disabled = true;
  document.getElementById("back-to-list-btn").disabled = true;

  try {
    // Get deck URL from confirmation form
    const deckUrl = document.getElementById("confirmation-your-deck-url").value || null;

    const response = await fetch(`/api/match-report/confirm/${currentConfirmation.id}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ deck_url: deckUrl })
    });

    const data = await response.json();

    // Hide loading
    document.getElementById("confirmation-loading").classList.add("hidden");

    if (!response.ok) {
      // Show error
      const errorEl = document.getElementById("confirmation-error");
      errorEl.textContent = data.error?.message || "Failed to confirm match. Please try again.";
      errorEl.classList.remove("hidden");

      // Re-enable buttons
      document.getElementById("confirm-match-btn").disabled = false;
      document.getElementById("deny-match-btn").disabled = false;
      document.getElementById("back-to-list-btn").disabled = false;
      return;
    }

    // Success!
    const successEl = document.getElementById("confirmation-success");
    successEl.textContent = data.message || "Match confirmed successfully!";
    successEl.classList.remove("hidden");

    // Close modal after 2 seconds and refresh list
    setTimeout(() => {
      document.getElementById("confirmation-modal").classList.add("hidden");
      backToConfirmationList();
      fetchPendingConfirmations(); // Refresh list
    }, 2000);

  } catch (error) {
    console.error("Error confirming match:", error);

    // Hide loading
    document.getElementById("confirmation-loading").classList.add("hidden");

    // Show error
    const errorEl = document.getElementById("confirmation-error");
    errorEl.textContent = "Network error. Please check your connection and try again.";
    errorEl.classList.remove("hidden");

    // Re-enable buttons
    document.getElementById("confirm-match-btn").disabled = false;
    document.getElementById("deny-match-btn").disabled = false;
    document.getElementById("back-to-list-btn").disabled = false;
  }
}

async function denyMatch() {
  if (!currentConfirmation) return;

  // Show loading
  document.getElementById("confirmation-loading").classList.remove("hidden");
  document.getElementById("confirmation-success").classList.add("hidden");
  document.getElementById("confirmation-error").classList.add("hidden");

  // Disable buttons
  document.getElementById("confirm-match-btn").disabled = true;
  document.getElementById("deny-match-btn").disabled = true;
  document.getElementById("back-to-list-btn").disabled = true;

  try {
    const response = await fetch(`/api/match-report/deny/${currentConfirmation.id}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ reason: null }) // Optional: could add reason input field
    });

    const data = await response.json();

    // Hide loading
    document.getElementById("confirmation-loading").classList.add("hidden");

    if (!response.ok) {
      // Show error
      const errorEl = document.getElementById("confirmation-error");
      errorEl.textContent = data.error?.message || "Failed to deny match. Please try again.";
      errorEl.classList.remove("hidden");

      // Re-enable buttons
      document.getElementById("confirm-match-btn").disabled = false;
      document.getElementById("deny-match-btn").disabled = false;
      document.getElementById("back-to-list-btn").disabled = false;
      return;
    }

    // Success!
    const successEl = document.getElementById("confirmation-success");
    successEl.textContent = data.message || "Match report denied.";
    successEl.classList.remove("hidden");

    // Close modal after 2 seconds and refresh list
    setTimeout(() => {
      document.getElementById("confirmation-modal").classList.add("hidden");
      backToConfirmationList();
      fetchPendingConfirmations(); // Refresh list
    }, 2000);

  } catch (error) {
    console.error("Error denying match:", error);

    // Hide loading
    document.getElementById("confirmation-loading").classList.add("hidden");

    // Show error
    const errorEl = document.getElementById("confirmation-error");
    errorEl.textContent = "Network error. Please check your connection and try again.";
    errorEl.classList.remove("hidden");

    // Re-enable buttons
    document.getElementById("confirm-match-btn").disabled = false;
    document.getElementById("deny-match-btn").disabled = false;
    document.getElementById("back-to-list-btn").disabled = false;
  }
}

function backToConfirmationList() {
  document.getElementById("pending-confirmations-list").classList.remove("hidden");
  document.getElementById("confirmation-details").classList.add("hidden");
  currentConfirmation = null;
}

function initializeConfirmationModalListeners() {
  // Confirm button
  const confirmBtn = document.getElementById("confirm-match-btn");
  if (confirmBtn) {
    confirmBtn.addEventListener("click", confirmMatch);
  }

  // Deny button
  const denyBtn = document.getElementById("deny-match-btn");
  if (denyBtn) {
    denyBtn.addEventListener("click", denyMatch);
  }

  // Back to list button
  const backBtn = document.getElementById("back-to-list-btn");
  if (backBtn) {
    backBtn.addEventListener("click", backToConfirmationList);
  }
}

function startConfirmationPolling() {
  // Initial fetch
  fetchPendingConfirmations();

  // Poll every 30 seconds
  pollInterval = setInterval(fetchPendingConfirmations, POLL_INTERVAL_MS);
}

function stopConfirmationPolling() {
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
}

// ==================== Fullscreen Support ====================

function requestFullscreen() {
  const elem = document.documentElement;

  if (elem.requestFullscreen) {
    elem.requestFullscreen().catch((err) => {
      console.log("Fullscreen request failed:", err);
    });
  } else if (elem.webkitRequestFullscreen) {
    // Safari
    elem.webkitRequestFullscreen();
  } else if (elem.mozRequestFullScreen) {
    // Firefox
    elem.mozRequestFullScreen();
  } else if (elem.msRequestFullscreen) {
    // IE/Edge
    elem.msRequestFullscreen();
  }
}

function exitFullscreen() {
  if (document.exitFullscreen) {
    document.exitFullscreen().catch((err) => {
      console.log("Exit fullscreen failed:", err);
    });
  } else if (document.webkitExitFullscreen) {
    // Safari
    document.webkitExitFullscreen();
  } else if (document.mozCancelFullScreen) {
    // Firefox
    document.mozCancelFullScreen();
  } else if (document.msExitFullscreen) {
    // IE/Edge
    document.msExitFullscreen();
  }
}

function toggleFullscreen() {
  if (isFullscreen()) {
    exitFullscreen();
  } else {
    requestFullscreen();
  }
  updateFullscreenButton();
}

function isFullscreen() {
  return !!(
    document.fullscreenElement ||
    document.webkitFullscreenElement ||
    document.mozFullScreenElement ||
    document.msFullscreenElement
  );
}

function updateFullscreenButton() {
  const fullscreenBtn = document.getElementById("fullscreen-btn");
  if (!fullscreenBtn) return;

  if (isFullscreen()) {
    fullscreenBtn.classList.add("active");
    fullscreenBtn.setAttribute("aria-label", "Exit fullscreen");
  } else {
    fullscreenBtn.classList.remove("active");
    fullscreenBtn.setAttribute("aria-label", "Enter fullscreen");
  }
}

// ==================== Initialization ====================

document.addEventListener("DOMContentLoaded", function () {
  console.log("[LifeCounter] DOM loaded, initializing...");

  // Load and render initial state
  currentState = LifeCounterState.load();
  console.log("[LifeCounter] State loaded:", currentState);

  renderUI(currentState);

  // Initialize event listeners
  initializeEventListeners();

  // Initialize match report modal listeners
  initializeMatchReportListeners();

  // Initialize confirmation modal listeners
  initializeConfirmationModalListeners();

  // Start polling for pending confirmations
  startConfirmationPolling();

  // Check if game already ended (from previous session)
  checkForGameEnd(currentState);

  // Request fullscreen on first user interaction
  let fullscreenRequested = false;
  const requestFullscreenOnce = () => {
    if (!fullscreenRequested && !isFullscreen()) {
      fullscreenRequested = true;
      requestFullscreen();
    }
  };

  // Try to go fullscreen on first tap/click
  document.body.addEventListener("click", requestFullscreenOnce, { once: true });
  document.body.addEventListener("touchstart", requestFullscreenOnce, { once: true });

  // Listen for fullscreen changes to update button state
  document.addEventListener("fullscreenchange", updateFullscreenButton);
  document.addEventListener("webkitfullscreenchange", updateFullscreenButton);
  document.addEventListener("mozfullscreenchange", updateFullscreenButton);
  document.addEventListener("msfullscreenchange", updateFullscreenButton);

  // Update fullscreen button state on load
  updateFullscreenButton();

  console.log("[LifeCounter] Initialization complete");
  console.log("[LifeCounter] Threshold elements:", document.querySelectorAll(".threshold-element").length);
  console.log("[LifeCounter] Element buttons:", document.querySelectorAll(".element-decrement, .element-increment").length);
});

// Cleanup on page unload
window.addEventListener("beforeunload", function () {
  // Force save current state
  if (saveTimeout) {
    clearTimeout(saveTimeout);
    LifeCounterState.save(currentState);
  }

  // Stop confirmation polling
  stopConfirmationPolling();
});
