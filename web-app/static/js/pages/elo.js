/**
 * Page: ELO Leaderboards
 * Template: templates/pages/elo.html
 * Description: Handles ELO distribution grouping, lifetime leaderboard, and event leaderboard rendering
 */

// Store all ELO data and leaderboard data for re-rendering
let allElos = [];
let lifetimeData = [];
let eventData = null;

document.addEventListener('DOMContentLoaded', () => {
  initializeEventListeners();
  fetchDistribution();
  fetchLeaderboards();

  // Auto-refresh every 30 seconds
  setInterval(fetchDistribution, 30000);
  setInterval(fetchLeaderboards, 30000);
});

/**
 * Initialize all event listeners using event delegation
 */
function initializeEventListeners() {
  // Show/hide custom inputs based on grouping selection
  document.getElementById('grouping-select').addEventListener('change', function () {
    const customInputs = document.getElementById('custom-inputs');
    if (this.value === 'custom') {
      customInputs.classList.add('visible');
    } else {
      customInputs.classList.remove('visible');
      fetchDistribution();
    }
  });

  // Listen for Apply button clicks (using event delegation)
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action="apply-custom-grouping"]');
    if (!btn) return;
    fetchDistribution();
  });

  // Listen for count select changes
  document.getElementById('lifetime-count-select').addEventListener('change', function () {
    renderLifetimeLeaderboard(lifetimeData);
  });

  document.getElementById('event-count-select').addEventListener('change', function () {
    if (eventData) renderEventLeaderboard(eventData);
  });
}

/**
 * Calculate ELO distribution based on grouping settings
 * @param {number[]} elos - Array of ELO ratings
 * @param {number} startValue - Starting ELO value for first band
 * @param {number} bandSize - Size of each ELO band
 * @returns {Object[]} Array of band objects with range, count, and percentage
 */
function calculateDistribution(elos, startValue, bandSize) {
  const total = elos.length;
  if (total === 0) return [];

  const bands = [];
  const minElo = Math.min(...elos);
  const maxElo = Math.max(...elos);

  // Create bands from start value up to max ELO
  for (let lower = startValue; lower <= maxElo + bandSize; lower += bandSize) {
    const upper = lower + bandSize - 1;
    const count = elos.filter((elo) => elo >= lower && elo <= upper).length;
    const percentage = (count / total) * 100;

    bands.push({
      range: `${lower}-${upper}`,
      count: count,
      percentage: percentage.toFixed(2),
    });
  }

  // Filter and reverse to show highest ELO ranges first
  return bands
    .filter((b) => b.count > 0 || parseInt(b.range.split('-')[0]) <= 1600)
    .reverse();
}

/**
 * Render the distribution table with band data
 * @param {Object[]} bands - Array of band objects
 * @param {number} totalPlayers - Total number of players
 */
function renderDistribution(bands, totalPlayers) {
  document.getElementById('total-players').textContent = totalPlayers;

  const tbody = document.getElementById('distribution-body');
  tbody.innerHTML = '';

  bands.forEach((band) => {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td class="elo-range">${band.range}</td>
      <td class="player-count">${band.count}</td>
      <td>${band.percentage}%</td>
    `;
    tbody.appendChild(row);
  });
}

/**
 * Fetch ELO data and render distribution with current grouping settings
 */
async function fetchDistribution() {
  try {
    const res = await fetch('/api/leaderboard');
    if (!res.ok) {
      console.error('Failed to fetch leaderboard:', res.status);
      return;
    }
    const data = await res.json();
    allElos = data.map((p) => p.elo);

    // Get grouping settings
    const grouping = document.getElementById('grouping-select').value;
    let startValue, bandSize;

    switch (grouping) {
      case '100-standard':
        startValue = 1100;
        bandSize = 100;
        break;
      case '100-offset':
        startValue = 1050;
        bandSize = 100;
        break;
      case '50-standard':
        startValue = 1100;
        bandSize = 50;
        break;
      case 'custom':
        startValue = parseInt(document.getElementById('custom-start').value) || 1100;
        bandSize = parseInt(document.getElementById('custom-size').value) || 100;
        break;
      default:
        startValue = 1100;
        bandSize = 100;
    }

    const bands = calculateDistribution(allElos, startValue, bandSize);
    renderDistribution(bands, allElos.length);
  } catch (error) {
    console.error('Error fetching distribution:', error);
  }
}

/**
 * Fetch combined leaderboard data (lifetime + event)
 */
async function fetchLeaderboards() {
  try {
    const res = await fetch('/api/leaderboard/combined');
    if (!res.ok) {
      console.error('Failed to fetch leaderboards:', res.status);
      return;
    }
    const data = await res.json();

    // Store data for re-rendering
    lifetimeData = data.lifetime;
    eventData = data.event;

    // Render both leaderboards
    renderLifetimeLeaderboard(lifetimeData);
    renderEventLeaderboard(eventData);
  } catch (error) {
    console.error('Error fetching leaderboards:', error);
  }
}

/**
 * Render lifetime leaderboard table
 * @param {Object[]} players - Array of player objects with lifetime stats
 */
function renderLifetimeLeaderboard(players) {
  const tbody = document.getElementById('lifetime-leaderboard-body');
  tbody.innerHTML = '';

  // Get display count from select
  const countSelect = document.getElementById('lifetime-count-select');
  const countValue = countSelect.value;
  const displayCount = countValue === 'all' ? players.length : parseInt(countValue);

  // Show players based on selected count
  players.slice(0, displayCount).forEach((player, index) => {
    const row = document.createElement('tr');
    const rankDisplay = index < 3 ? ['🥇', '🥈', '🥉'][index] : `#${index + 1}`;

    row.innerHTML = `
      <td class="rank-display">${rankDisplay}</td>
      <td><a href="/player/${player.id}" class="player-link">${player.name}</a></td>
      <td class="col-align-right lifetime-elo">${player.elo}</td>
      <td class="col-align-right win-loss">${player.wins}-${player.losses}</td>
    `;
    tbody.appendChild(row);
  });

  if (players.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty-state">No players yet</td></tr>';
  }
}

/**
 * Render event leaderboard table
 * @param {Object} eventData - Object containing event info and leaderboard
 */
function renderEventLeaderboard(eventData) {
  const titleEl = document.getElementById('event-title');
  const subtitleEl = document.getElementById('event-subtitle');
  const tbody = document.getElementById('event-leaderboard-body');

  if (!eventData.info) {
    titleEl.textContent = 'No Active Event';
    subtitleEl.textContent = 'ELO tracking is paused between events';
    tbody.innerHTML = '<tr><td colspan="3" class="empty-state">No active event</td></tr>';
    return;
  }

  titleEl.textContent = eventData.info.event_name;
  subtitleEl.textContent = `Started: ${new Date(eventData.info.start_date).toLocaleDateString()}`;

  tbody.innerHTML = '';

  if (eventData.leaderboard.length === 0) {
    tbody.innerHTML = '<tr><td colspan="3" class="empty-state">No matches played yet</td></tr>';
    return;
  }

  // Get display count from select
  const countSelect = document.getElementById('event-count-select');
  const countValue = countSelect.value;
  const displayCount =
    countValue === 'all' ? eventData.leaderboard.length : parseInt(countValue);

  // Show players based on selected count
  eventData.leaderboard.slice(0, displayCount).forEach((player, index) => {
    const row = document.createElement('tr');
    const rankDisplay = index < 3 ? ['🥇', '🥈', '🥉'][index] : `#${index + 1}`;

    row.innerHTML = `
      <td class="rank-display">${rankDisplay}</td>
      <td><a href="/player/${player.id}" class="player-link">${player.name}</a></td>
      <td class="col-align-right event-elo">${player.event_elo}</td>
    `;
    tbody.appendChild(row);
  });
}
