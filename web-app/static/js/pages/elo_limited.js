/**
 * Page: Limited Format Leaderboard
 * Template: templates/pages/elo_limited.html
 * Description: Fetches and renders the limited format ELO leaderboard
 */

let limitedData = [];

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('limited-count-select').addEventListener('change', function () {
    renderLimitedLeaderboard(limitedData);
  });

  fetchLimitedLeaderboard();

  // Auto-refresh every 30 seconds
  setInterval(fetchLimitedLeaderboard, 30000);
});

/**
 * Fetch limited leaderboard data from the API
 */
async function fetchLimitedLeaderboard() {
  try {
    const res = await fetch('/api/leaderboard/limited');
    if (!res.ok) {
      console.error('Failed to fetch limited leaderboard:', res.status);
      return;
    }
    limitedData = await res.json();
    renderLimitedLeaderboard(limitedData);
  } catch (error) {
    console.error('Error fetching limited leaderboard:', error);
  }
}

/**
 * Render limited leaderboard table
 * @param {Object[]} players - Array of player objects with limited stats
 */
function renderLimitedLeaderboard(players) {
  const tbody = document.getElementById('limited-leaderboard-body');
  tbody.innerHTML = '';

  const countSelect = document.getElementById('limited-count-select');
  const countValue = countSelect.value;
  const displayCount = countValue === 'all' ? players.length : parseInt(countValue);

  players.slice(0, displayCount).forEach((player, index) => {
    const row = document.createElement('tr');
    const rankDisplay = index < 3 ? ['\u{1F947}', '\u{1F948}', '\u{1F949}'][index] : `#${index + 1}`;

    const totalGames = player.wins + player.losses;
    const winPct = totalGames > 0 ? ((player.wins / totalGames) * 100).toFixed(1) : '0.0';

    row.innerHTML = `
      <td class="rank-display">${rankDisplay}</td>
      <td><a href="/player/${player.id}" class="player-link">${player.name}</a></td>
      <td class="col-align-right lifetime-elo">${player.elo}</td>
      <td class="col-align-right win-loss">${player.wins}-${player.losses}</td>
      <td class="col-align-right win-pct">${winPct}%</td>
    `;
    tbody.appendChild(row);
  });

  if (players.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No limited players yet</td></tr>';
  }
}
