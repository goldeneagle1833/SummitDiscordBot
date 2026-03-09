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

// ==================== Match Reporting (US2 - Stub) ====================

function showMatchReportModal() {
  const modal = document.getElementById("match-report-modal");
  if (modal) {
    // Populate modal with match summary
    const summaryEl = modal.querySelector(".match-summary");
    const player1Life = currentState.players.player1.life;
    const player2Life = currentState.players.player2.life;

    let winner = "";
    if (player1Life <= 0 && player2Life <= 0) {
      winner = "Draw";
    } else if (player1Life <= 0) {
      winner = "Player 2 wins";
    } else {
      winner = "Player 1 wins";
    }

    if (summaryEl) {
      summaryEl.textContent = `${winner}! Final life: Player 1 (${player1Life}) vs Player 2 (${player2Life})`;
    }

    modal.classList.remove("hidden");
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
