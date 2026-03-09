/**
 * Page: Community Links
 * Template: templates/pages/community.html
 * Description: Handles YouTube channel fetching and Discord server filtering
 */

/**
 * Fetch and render YouTube channels
 */
async function loadYouTubeChannels() {
  const container = document.getElementById('youtube-channels');
  try {
    const res = await fetch('/api/youtube-videos');
    if (!res.ok) throw new Error('Failed to fetch');
    const videos = await res.json();

    container.innerHTML = '';

    for (const key of Object.keys(videos)) {
      const video = videos[key];
      if (!video) continue;

      const card = document.createElement('div');
      card.className = 'link-card youtube-card';
      card.innerHTML = `
        <a href="${video.url}" target="_blank" rel="noopener noreferrer">
          <img src="${video.thumbnail}" alt="${video.title}" class="thumbnail">
        </a>
        <h3>${video.channel_display_name}</h3>
        <p class="video-title-truncate">
          Latest: ${video.title}
        </p>
        <a href="${video.channel_url}" target="_blank" rel="noopener noreferrer">
          Visit Channel &rarr;
        </a>
      `;
      container.appendChild(card);
    }

    if (container.children.length === 0) {
      container.innerHTML =
        '<div class="link-card"><p>No channels available</p></div>';
    }
  } catch (error) {
    console.error('Error loading YouTube channels:', error);
    container.innerHTML =
      '<div class="link-card"><p>Failed to load channels</p></div>';
  }
}

/**
 * Initialize state filter for Discord servers
 */
function initializeStateFilter() {
  const stateFilter = document.getElementById('state-filter');
  if (!stateFilter) return;

  stateFilter.addEventListener('input', function () {
    const query = this.value.toLowerCase().trim();
    const cards = document.querySelectorAll('.discord-card');
    const noResults = document.getElementById('discord-no-results');
    let visible = 0;

    cards.forEach(function (card) {
      const state = card.getAttribute('data-state').toLowerCase();
      if (!query || state.includes(query)) {
        card.classList.remove('hidden');
        visible++;
      } else {
        card.classList.add('hidden');
      }
    });

    if (visible === 0) {
      noResults.classList.remove('hidden');
    } else {
      noResults.classList.add('hidden');
    }
  });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  loadYouTubeChannels();
  initializeStateFilter();
});
