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
  document.getElementById("opponent-deck-url").value = "";
  document.getElementById("went-first").value = "";

  // Hide selected opponent display
  document.getElementById("opponent-selected").classList.add("hidden");

  // Hide autocomplete
  document.getElementById("opponent-autocomplete").classList.add("hidden");

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
      <img src="${opponent.avatar || '/static/images/default-avatar.png'}" alt="${opponent.display_name}">
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
        display_name: this.querySelector(".autocomplete-item-name").textContent,
        avatar: this.querySelector("img").src
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
  document.getElementById("opponent-avatar").src = opponent.avatar;
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
  const submitterDeckUrl = document.getElementById("submitter-deck-url").value;
  const opponentDeckUrl = document.getElementById("opponent-deck-url").value;

  // Validate deck URLs if provided
  const deckUrlPattern = /^https?:\/\/(www\.)?curiosa\.io\/decks\/[a-zA-Z0-9_-]+$/;
  const submitterDeckValid = !submitterDeckUrl || deckUrlPattern.test(submitterDeckUrl);
  const opponentDeckValid = !opponentDeckUrl || deckUrlPattern.test(opponentDeckUrl);

  // Enable submit buttons only if all required fields are valid
  const isValid = opponentSelected && turnOrderSelected && submitterDeckValid && opponentDeckValid;

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
    opponent_deck_url: document.getElementById("opponent-deck-url").value || null,
    final_life_submitter: parseInt(document.getElementById("final-life-submitter").value),
    final_life_opponent: parseInt(document.getElementById("final-life-opponent").value)
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

  // Turn order toggle
  initializeTurnOrderToggle();

  // Deck URL validation (on input)
  const submitterDeckUrl = document.getElementById("submitter-deck-url");
  const opponentDeckUrl = document.getElementById("opponent-deck-url");

  if (submitterDeckUrl) {
    submitterDeckUrl.addEventListener("input", validateMatchReportForm);
  }

  if (opponentDeckUrl) {
    opponentDeckUrl.addEventListener("input", validateMatchReportForm);
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

// ==================== SSE Notification Client (US3 - Stub) ====================

let eventSource = null;

function connectSSE() {
  // Stub for User Story 3 - SSE notifications
  console.log("SSE connection not yet implemented (User Story 3)");
}

function disconnectSSE() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
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

function isFullscreen() {
  return !!(
    document.fullscreenElement ||
    document.webkitFullscreenElement ||
    document.mozFullScreenElement ||
    document.msFullscreenElement
  );
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

  disconnectSSE();
});
