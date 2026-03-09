/**
 * Page: Global ELO Leaderboard
 * Template: templates/pages/elo_global.html
 * Description: Handles global leaderboard fetching and rendering with auto-refresh
 */

/**
 * Fetch and render the global ELO leaderboard
 */
async function fetchLeaderboard() {
  try {
    const res = await fetch('/api/leaderboard');
    const data = await res.json();
    const tbody = document.getElementById('leaderboard-tbody');
    tbody.innerHTML = '';

    data.forEach((player, i) => {
      const rank = i + 1;
      let rankDisplay = rank;

      // Add rank badge for top 3
      if (rank <= 3) {
        rankDisplay = `<span class="rank-badge rank-${rank}">${rank}</span>`;
      }

      const row = document.createElement('tr');
      row.innerHTML = `
        <td>${rankDisplay}</td>
        <td><a href="/player/${player.id}" class="player-link">${player.name}</a></td>
        <td><span class="match-win">${player.wins}</span> / <span class="match-loss">${player.losses}</span></td>
        <td>${player.elo}</td>
      `;
      tbody.appendChild(row);
    });
  } catch (error) {
    console.error('Error fetching leaderboard:', error);
  }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  fetchLeaderboard();
  // Auto-refresh every 30 seconds
  setInterval(fetchLeaderboard, 30000);
});
