/**
 * Page: Home / Landing Page
 * Template: templates/pages/index.html
 * Description: Handles event leaderboard, YouTube videos, and temporary banners
 */

// ELO source tracking
let currentEloSource = "online"; // 'online' or 'paper' - default to online

document.addEventListener("DOMContentLoaded", () => {
  initializeTemporaryNotices();
  initializeEasterEgg();
  initializeEloSourceToggle();
  initializePlayerSearch();

  // Load saved preference or default to online
  const savedSource = localStorage.getItem("home_elo_source_preference");
  if (savedSource && (savedSource === "online" || savedSource === "paper" || savedSource === "limited")) {
    currentEloSource = savedSource;
    updateToggleButtons(currentEloSource);
  }

  fetchEventLeaderboard();

  // Auto-refresh event leaderboard every 30 seconds
  setInterval(fetchEventLeaderboard, 30000);
});

/**
 * Initialize temporary notices with expiry dates
 */
function initializeTemporaryNotices() {
  // Hide temporary notice after expiry (Jan 26, 2026 at 21:37 UTC)
  const notice = document.getElementById("temp-notice");
  if (notice) {
    const expiryDate = new Date("2026-01-26T21:37:00Z");
    if (new Date() > expiryDate) {
      notice.style.display = "none";
    }
  }

  // Hide community promo banner after expiry (Feb 20, 2026)
  const banner = document.getElementById("community-promo-banner");
  if (banner) {
    const expiryDate = new Date("2026-02-20T23:59:59Z");
    if (new Date() > expiryDate) {
      banner.style.display = "none";
    }
  }
}

/**
 * Initialize easter egg (triple-click hero title to access secret page)
 */
function initializeEasterEgg() {
  const heroTitle = document.getElementById("hero-secret");
  if (!heroTitle) return;

  let clickCount = 0;
  let clickTimer;

  heroTitle.addEventListener("click", function (e) {
    clickCount++;

    if (clickCount === 3) {
      window.location.href = "/secret-fart-leaderboard";
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
  const container = document.getElementById("youtube-videos");
  if (!container) return;

  container.innerHTML = "";

  // Display all videos from the API response
  for (const key of Object.keys(videos)) {
    const video = videos[key];
    if (!video) continue;

    const card = document.createElement("div");
    card.className = "youtube-video-card";
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
    const res = await fetch("/api/youtube-videos");
    if (!res.ok) return;
    const data = await res.json();
    renderYouTubeVideos(data);
  } catch (error) {
    console.error("Error fetching YouTube videos:", error);
  }
}

/**
 * Show or hide the extra W/L and Win% columns used for limited mode
 * @param {boolean} show
 */
function setLimitedColumns(show) {
  const thElo = document.getElementById("th-elo");
  const thWl = document.getElementById("th-wl");
  const thWinPct = document.getElementById("th-winpct");
  if (thElo) thElo.textContent = show ? "Limited ELO" : "Event ELO";
  if (thWl) thWl.style.display = show ? "" : "none";
  if (thWinPct) thWinPct.style.display = show ? "" : "none";
}

/**
 * Render limited leaderboard data into the home page table
 * @param {Object[]} players - Array of player objects with limited stats
 */
function renderLimitedLeaderboard(players) {
  const titleEl = document.getElementById("event-title");
  const subtitleEl = document.getElementById("event-subtitle");
  const tbody = document.getElementById("event-leaderboard-tbody");
  const eventSection = document.getElementById("event-section");
  const noEventSection = document.getElementById("no-event-section");
  const statsBar = document.getElementById("event-stats-bar");

  eventSection.style.display = "block";
  noEventSection.style.display = "none";
  statsBar.style.display = "none";
  setLimitedColumns(true);

  titleEl.textContent = "Limited Format Leaderboard";
  subtitleEl.textContent = "Rankings based on Limited (Arena Draft) matches";

  tbody.innerHTML = "";

  if (!players.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="leaderboard-empty-state">No limited players yet</td></tr>';
    return;
  }

  players.forEach((player, index) => {
    const row = document.createElement("tr");
    const rank = index + 1;
    let rankDisplay = `<span class="rank-display">${rank}</span>`;
    if (rank <= 3) {
      const romanRank = { 1: 'I', 2: 'II', 3: 'III' }[rank];
      rankDisplay = `<span class="rank-badge rank-${rank}">${romanRank}</span>`;
      row.classList.add(`rank-row-${rank}`);
    }

    const totalGames = player.wins + player.losses;
    const winPct = totalGames > 0 ? ((player.wins / totalGames) * 100).toFixed(1) : "0.0";

    row.innerHTML = `
      <td>${rankDisplay}</td>
      <td><a href="/player/${player.id}" class="player-link">${player.name}</a></td>
      <td>${player.elo}</td>
      <td>${player.wins}-${player.losses}</td>
      <td>${winPct}%</td>
    `;
    tbody.appendChild(row);
  });
}

/**
 * Render event leaderboard table
 * @param {Object} eventData - Event data containing event info and leaderboard
 */
function renderEventLeaderboard(eventData) {
  const titleEl = document.getElementById("event-title");
  const subtitleEl = document.getElementById("event-subtitle");
  const tbody = document.getElementById("event-leaderboard-tbody");
  const eventSection = document.getElementById("event-section");
  const noEventSection = document.getElementById("no-event-section");

  setLimitedColumns(false);

  if (!eventData.event) {
    // Hide event leaderboard, show no-event content
    eventSection.style.display = "none";
    noEventSection.style.display = "block";
    fetchYouTubeVideos();
    return;
  }

  // Show event leaderboard, hide no-event content
  eventSection.style.display = "block";
  noEventSection.style.display = "none";

  titleEl.textContent = eventData.event.event_name;
  subtitleEl.textContent = `Started: ${new Date(eventData.event.start_date).toLocaleDateString()} | End: 4/25/2026`;

  tbody.innerHTML = "";

  if (eventData.leaderboard.length === 0) {
    tbody.innerHTML =
      '<tr><td colspan="3" class="leaderboard-empty-state">No matches played yet</td></tr>';
    return;
  }

  // Populate stat bar
  const statsBar = document.getElementById("event-stats-bar");
  const totalPlayers = eventData.leaderboard.length;
  const topElo = eventData.leaderboard[0].event_elo;
  const avgElo = Math.round(eventData.leaderboard.reduce((sum, p) => sum + p.event_elo, 0) / totalPlayers);

  document.getElementById("stat-total-players").textContent = totalPlayers;
  document.getElementById("stat-top-elo").textContent = topElo;
  document.getElementById("stat-avg-elo").textContent = avgElo;
  statsBar.style.display = "";

  // Render all players with staggered animation
  eventData.leaderboard.forEach((player, index) => {
    const row = document.createElement("tr");
    const rank = index + 1;
    let rankDisplay = `<span class="rank-display">${rank}</span>`;
    if (rank <= 3) {
      const romanRank = { 1: 'I', 2: 'II', 3: 'III' }[rank];
      rankDisplay = `<span class="rank-badge rank-${rank}">${romanRank}</span>`;
      row.classList.add(`rank-row-${rank}`);
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
 * Initialize ELO source toggle buttons
 */
function initializeEloSourceToggle() {
  document.querySelectorAll(".elo-source-btn").forEach((btn) => {
    btn.addEventListener("click", async function () {
      if (this.disabled) return;

      const source = this.dataset.source;
      if (source === currentEloSource) return; // Already selected

      // Update state
      currentEloSource = source;
      localStorage.setItem("home_elo_source_preference", source);

      // Update UI
      updateToggleButtons(source);

      // Refetch data with new source
      await fetchEventLeaderboard();
    });
  });
}

/**
 * Update toggle button states
 * @param {string} source - 'online' or 'paper'
 */
function updateToggleButtons(source) {
  document.querySelectorAll(".elo-source-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.source === source);
  });
}

/**
 * Player search autocomplete
 */
function initializePlayerSearch() {
  const input = document.getElementById("player-search-input");
  const dropdown = document.getElementById("player-search-dropdown");
  if (!input || !dropdown) return;

  let debounceTimer = null;
  let activeIndex = -1;
  let currentResults = [];

  function getAvatarUrl(player) {
    if (player.provider === "discord" && player.avatar) {
      return `https://cdn.discordapp.com/avatars/${player.user_id}/${player.avatar}.png?size=32`;
    }
    if (player.provider === "google" && player.avatar) {
      return player.avatar;
    }
    return null;
  }

  function getPlayerUrl(player) {
    return `/player/${encodeURIComponent(player.user_id)}`;
  }

  function renderDropdown(players) {
    currentResults = players;
    activeIndex = -1;
    dropdown.innerHTML = "";

    if (!players.length) {
      const empty = document.createElement("div");
      empty.className = "player-search-empty";
      empty.textContent = "No players found";
      dropdown.appendChild(empty);
      dropdown.hidden = false;
      return;
    }

    players.forEach((player, i) => {
      const a = document.createElement("a");
      a.className = "player-search-item";
      a.href = getPlayerUrl(player);

      const avatarUrl = getAvatarUrl(player);
      const img = document.createElement("img");
      img.className = "player-search-avatar";
      img.alt = "";
      if (avatarUrl) {
        img.src = avatarUrl;
        img.onerror = () => { img.src = ""; img.style.visibility = "hidden"; };
      } else {
        img.style.visibility = "hidden";
      }

      const name = document.createElement("span");
      name.className = "player-search-name";
      name.textContent = player.display_name;

      a.appendChild(img);
      a.appendChild(name);
      dropdown.appendChild(a);
    });

    dropdown.hidden = false;
  }

  function closeDropdown() {
    dropdown.hidden = true;
    activeIndex = -1;
  }

  function setActive(index) {
    const items = dropdown.querySelectorAll(".player-search-item");
    items.forEach((el, i) => el.classList.toggle("active", i === index));
    activeIndex = index;
  }

  async function doSearch(query) {
    if (query.length < 3) { closeDropdown(); return; }
    try {
      const res = await fetch(`/api/players/search?q=${encodeURIComponent(query)}&limit=8`);
      const data = await res.json();
      renderDropdown(data.players || []);
    } catch (_) {
      closeDropdown();
    }
  }

  input.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    const q = input.value.trim();
    if (q.length < 3) { closeDropdown(); return; }
    debounceTimer = setTimeout(() => doSearch(q), 200);
  });

  input.addEventListener("keydown", (e) => {
    const items = dropdown.querySelectorAll(".player-search-item");
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive(Math.min(activeIndex + 1, items.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive(Math.max(activeIndex - 1, 0));
    } else if (e.key === "Enter") {
      if (activeIndex >= 0 && currentResults[activeIndex]) {
        window.location.href = getPlayerUrl(currentResults[activeIndex]);
      } else if (currentResults.length === 1) {
        window.location.href = getPlayerUrl(currentResults[0]);
      }
    } else if (e.key === "Escape") {
      closeDropdown();
    }
  });

  document.addEventListener("click", (e) => {
    if (!document.getElementById("player-search-container").contains(e.target)) {
      closeDropdown();
    }
  });
}

/**
 * Fetch event leaderboard from API
 */
async function fetchEventLeaderboard() {
  try {
    if (currentEloSource === "limited") {
      const res = await fetch("/api/leaderboard/limited");
      if (!res.ok) {
        console.error("Failed to fetch limited leaderboard:", res.status);
        return;
      }
      const data = await res.json();
      renderLimitedLeaderboard(data);
      return;
    }

    // Fetch from different endpoint based on source
    const endpoint =
      currentEloSource === "paper"
        ? "/api/leaderboard/paper-event"
        : "/api/leaderboard/event";

    const res = await fetch(endpoint);
    if (!res.ok) {
      console.error("Failed to fetch event leaderboard:", res.status);
      return;
    }
    const data = await res.json();
    renderEventLeaderboard(data);
  } catch (error) {
    console.error("Error fetching event leaderboard:", error);
  }
}
