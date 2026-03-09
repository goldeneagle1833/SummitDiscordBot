/**
 * Match History Page
 * Handles match history display with date filtering
 */

let availableDates = [];

/**
 * Load available match dates from API
 */
async function loadAvailableDates() {
  try {
    const response = await fetch('/api/match-history/available-dates');
    if (!response.ok) {
      throw new Error('Failed to fetch available dates');
    }

    availableDates = await response.json();
    setupDatePicker();
  } catch (error) {
    console.error('Error loading available dates:', error);
  }
}

/**
 * Setup date picker with available dates
 */
function setupDatePicker() {
  const datePicker = document.getElementById('date-picker');

  if (availableDates.length > 0) {
    // Set min and max dates
    const minDate = availableDates[availableDates.length - 1];
    const maxDate = availableDates[0];
    datePicker.min = minDate;
    datePicker.max = maxDate;
  }

  // Listen for date changes
  datePicker.addEventListener('change', function () {
    const selectedDate = this.value;
    if (selectedDate && availableDates.includes(selectedDate)) {
      loadMatchHistory(selectedDate);
    } else if (selectedDate) {
      // Date has no data, reset
      alert('No match data available for this date');
      this.value = '';
    }
  });

  // Validate on input (for manual typing)
  datePicker.addEventListener('input', function () {
    const selectedDate = this.value;
    if (selectedDate && !availableDates.includes(selectedDate)) {
      this.setCustomValidity('No matches on this date');
    } else {
      this.setCustomValidity('');
    }
  });
}

/**
 * Load match history for a specific date or last 24 hours
 * @param {string|null} date - Date string (YYYY-MM-DD) or null for last 24 hours
 */
async function loadMatchHistory(date = null) {
  try {
    const url = date ? `/api/match-history?date=${date}` : '/api/match-history';
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error('Failed to fetch match history');
    }

    const matches = await response.json();
    const tbody = document.getElementById('match-history-tbody');
    const sectionTitle = document.getElementById('section-title');
    tbody.innerHTML = '';

    // Update section title
    if (date) {
      const dateObj = new Date(date + 'T00:00:00');
      sectionTitle.textContent = `📜 Matches on ${dateObj.toLocaleDateString()}`;
    } else {
      sectionTitle.textContent = '📜 Last 24 Hours';
    }

    if (matches.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7" class="centered-message">
            No matches recorded
          </td>
        </tr>
      `;
      return;
    }

    matches.forEach((match) => {
      const row = document.createElement('tr');
      const date = new Date(match.timestamp).toLocaleDateString();
      const matchTime = match.match_time ? `${match.match_time} min` : '-';
      const matchId = match.match_id ? `#${match.match_id}` : '-';
      const winnerEloSign = match.winner_elo_change >= 0 ? '+' : '';
      const loserEloSign = match.loser_elo_change >= 0 ? '+' : '';

      row.innerHTML = `
        <td class="match-id">${matchId}</td>
        <td><a href="/player/${match.winner_id}" class="opponent-link">${match.winner}</a></td>
        <td class="elo-positive">${winnerEloSign}${match.winner_elo_change}</td>
        <td><a href="/player/${match.loser_id}" class="opponent-link">${match.loser}</a></td>
        <td class="elo-negative">${loserEloSign}${match.loser_elo_change}</td>
        <td>${matchTime}</td>
        <td>${date}</td>
      `;
      tbody.appendChild(row);
    });
  } catch (error) {
    console.error('Error loading match history:', error);
    const tbody = document.getElementById('match-history-tbody');
    tbody.innerHTML = `
      <tr>
        <td colspan="7" class="error-message-cell">
          Error loading match history
        </td>
      </tr>
    `;
  }
}

/**
 * Clear date filter and show last 24 hours
 */
function clearDateFilter() {
  document.getElementById('date-picker').value = '';
  loadMatchHistory();
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  loadAvailableDates();
  loadMatchHistory();

  // Setup clear button
  const clearButton = document.querySelector('.date-picker-container button');
  if (clearButton) {
    clearButton.addEventListener('click', clearDateFilter);
  }
});
