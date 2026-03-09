/**
 * Page: Home / Landing Page
 * Template: templates/pages/index.html
 * Description: Handles event leaderboard, YouTube videos, and temporary banners
 */

document.addEventListener('DOMContentLoaded', () => {
  initializeTemporaryNotices();
  initializeEasterEgg();
  fetchEventLeaderboard();

  // Auto-refresh event leaderboard every 30 seconds
  setInterval(fetchEventLeaderboard, 30000);
});

/**
 * Initialize temporary notices with expiry dates
 */
function initializeTemporaryNotices() {
  // Hide temporary notice after expiry (Jan 26, 2026 at 21:37 UTC)
  const notice = document.getElementById('temp-notice');
  if (notice) {
    const expiryDate = new Date('2026-01-26T21:37:00Z');
    if (new Date() > expiryDate) {
      notice.style.display = 'none';
    }
  }

  // Hide community promo banner after expiry (Feb 20, 2026)
  const banner = document.getElementById('community-promo-banner');
  if (banner) {
    const expiryDate = new Date('2026-02-20T23:59:59Z');
    if (new Date() > expiryDate) {
      banner.style.display = 'none';
    }
  }
}

/**
 * Initialize easter egg (triple-click hero title to access secret page)
 */
function initializeEasterEgg() {
  const heroTitle = document.getElementById('hero-secret');
  if (!heroTitle) return;

  let clickCount = 0;
  let clickTimer;

  heroTitle.addEventListener('click', function (e) {
    clickCount++;

    if (clickCount === 3) {
      window.location.href = '/secret-fart-leaderboard';
      clickCount = 0;
      clearTimeout(clickTimer);
      return;
    }

    // Reset click count after 600ms if not triple-clicked
    clearTimeout(clickTimer);
    clickTimer = setTimeout(() => {
      clickCount = 0;
    }, 600);
  });
}

/**
 * Render YouTube videos in grid
 * @param {Object} videos - Object containing video data
 */
function renderYouTubeVideos(videos) {
  const container = document.getElementById('youtube-videos');
  if (!container) return;

  container.innerHTML = '';

  // Display all videos from the API response
  for (const key of Object.keys(videos)) {
    const video = videos[key];
    if (!video) continue;

    const card = document.createElement('div');
    card.className = 'youtube-video-card';
    card.innerHTML = `
      <a href="${video.url}" target="_blank" rel="noopener noreferrer">
        <img src="${video.thumbnail}" alt="${video.title}" class="youtube-video-thumbnail">
      </a>
      <div class="youtube-video-content">
        <p class="youtube-video-channel">
          <a href="${video.channel_url}" target="_blank" rel="noopener noreferrer">
            ${video.channel_display_name}
          </a>
        </p>
        <a href="${video.url}" target="_blank" rel="noopener noreferrer" class="youtube-video-title">
          ${video.title}
        </a>
      </div>
    `;
    container.appendChild(card);
  }
}

/**
 * Fetch YouTube videos from API
 */
async function fetchYouTubeVideos() {
  try {
    const res = await fetch('/api/youtube-videos');
    if (!res.ok) return;
    const data = await res.json();
    renderYouTubeVideos(data);
  } catch (error) {
    console.error('Error fetching YouTube videos:', error);
  }
}

/**
 * Render event leaderboard table
 * @param {Object} eventData - Event data containing event info and leaderboard
 */
function renderEventLeaderboard(eventData) {
  const titleEl = document.getElementById('event-title');
  const subtitleEl = document.getElementById('event-subtitle');
  const tbody = document.getElementById('event-leaderboard-tbody');
  const eventSection = document.getElementById('event-section');
  const noEventSection = document.getElementById('no-event-section');

  if (!eventData.event) {
    // Hide event leaderboard, show no-event content
    eventSection.style.display = 'none';
    noEventSection.style.display = 'block';
    fetchYouTubeVideos();
    return;
  }

  // Show event leaderboard, hide no-event content
  eventSection.style.display = 'block';
  noEventSection.style.display = 'none';

  titleEl.textContent = eventData.event.event_name;
  subtitleEl.textContent = `Started: ${new Date(eventData.event.start_date).toLocaleDateString()} | End: 3/14/2026`;

  tbody.innerHTML = '';

  if (eventData.leaderboard.length === 0) {
    tbody.innerHTML = '<tr><td colspan="3" class="leaderboard-empty-state">No matches played yet</td></tr>';
    return;
  }

  // Render all players
  eventData.leaderboard.forEach((player, index) => {
    const row = document.createElement('tr');
    const rank = index + 1;
    let rankDisplay = rank;
    if (rank <= 3) {
      rankDisplay = `<span class="rank-badge rank-${rank}">${rank}</span>`;
    }

    row.innerHTML = `
      <td>${rankDisplay}</td>
      <td><a href="/player/${player.id}" class="player-link">${player.name}</a></td>
      <td>${player.event_elo}</td>
    `;
    tbody.appendChild(row);
  });
}

/**
 * Fetch event leaderboard from API
 */
async function fetchEventLeaderboard() {
  try {
    const res = await fetch('/api/leaderboard/event');
    if (!res.ok) {
      console.error('Failed to fetch event leaderboard:', res.status);
      return;
    }
    const data = await res.json();
    renderEventLeaderboard(data);
  } catch (error) {
    console.error('Error fetching event leaderboard:', error);
  }
}
