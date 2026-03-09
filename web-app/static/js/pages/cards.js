/**
 * Card Win Rates Page
 * Handles card statistics fetching, filtering, and lazy loading
 */

/**
 * Calculate win rate color gradient
 * @param {number} winRate - Win rate percentage (0-100)
 * @returns {string} RGB color string
 */
function getWinRateColor(winRate) {
  const percentage = Math.max(0, Math.min(100, winRate));
  if (percentage <= 50) {
    const ratio = percentage / 50;
    const r = Math.round(231 + (255 - 231) * ratio);
    const g = Math.round(76 + (255 - 76) * ratio);
    const b = Math.round(60 + (255 - 60) * ratio);
    return `rgb(${r}, ${g}, ${b})`;
  } else {
    const ratio = (percentage - 50) / 50;
    const r = Math.round(255 - (255 - 46) * ratio);
    const g = Math.round(255 - (255 - 204) * ratio);
    const b = Math.round(255 - (255 - 113) * ratio);
    return `rgb(${r}, ${g}, ${b})`;
  }
}

// Lazy loading configuration
const CARDS_PER_PAGE = 20;
let allCards = [];
let filteredCards = [];
let renderedCount = 0;
let isLoading = false;

/**
 * Create a card tile element
 * @param {Object} card - Card data object
 * @param {number} idx - Card index for ranking
 * @returns {HTMLElement} Card tile element
 */
function createCardTile(card, idx) {
  const color = getWinRateColor(card.win_rate);
  const cardTile = document.createElement('a');
  cardTile.href = `/card/${encodeURIComponent(card.name)}`;
  cardTile.className = 'avatar-stats-card';
  cardTile.setAttribute('data-type', card.type || 'Unknown');
  cardTile.setAttribute('data-name', card.name.toLowerCase());

  const isSite = (card.type || '').toLowerCase() === 'site';
  const bgImageHtml = card.image
    ? `<div class="card-bg-image" style="background-image: url('/card-images/${
        card.image
      }');${
        isSite
          ? ' transform: rotate(90deg) scale(1.5); background-position: center;'
          : ''
      }"></div>`
    : '';

  cardTile.innerHTML = `
    ${bgImageHtml}
    <div class="avatar-stats-rank">#${idx + 1}</div>
    <div class="avatar-stats-name">
      ${card.name}
      <span class="card-type-badge">${card.type || 'Unknown'}</span>
    </div>
    <div class="avatar-stats-middle"></div>
    <div class="avatar-stats-bottom">
      <div class="avatar-stats-winrate" style="color: ${color};">${
        card.win_rate
      }%</div>
      <div class="avatar-stats-record">
        <span class="match-win">${card.wins}W</span> - <span class="match-loss">${
          card.losses
        }L</span>
      </div>
    </div>
  `;
  return cardTile;
}

/**
 * Render the next batch of cards (lazy loading)
 */
function renderMoreCards() {
  if (isLoading || renderedCount >= filteredCards.length) return;
  isLoading = true;

  const grid = document.getElementById('card-stats-grid');
  const endIdx = Math.min(renderedCount + CARDS_PER_PAGE, filteredCards.length);

  for (let i = renderedCount; i < endIdx; i++) {
    const cardTile = createCardTile(filteredCards[i], i);
    grid.appendChild(cardTile);
  }

  renderedCount = endIdx;
  document.getElementById('visible-count').textContent = renderedCount;
  isLoading = false;
}

/**
 * Apply type and search filters to card list
 */
function applyFilters() {
  const typeFilter = document.getElementById('type-filter');
  const searchInput = document.getElementById('card-search');
  const type = typeFilter.value.toLowerCase();
  const q = searchInput.value.trim().toLowerCase();

  filteredCards = allCards.filter((card) => {
    const cardType = (card.type || '').toLowerCase();
    const name = card.name.toLowerCase();
    const typeMatch = !type || cardType === type;
    const searchMatch = !q || name.includes(q);
    return typeMatch && searchMatch;
  });

  // Reset and re-render
  const grid = document.getElementById('card-stats-grid');
  grid.innerHTML = '';
  renderedCount = 0;
  document.getElementById('total-count').textContent = filteredCards.length;
  renderMoreCards();
}

/**
 * Fetch card statistics from API and initialize page
 */
async function fetchCardStats() {
  try {
    const res = await fetch('/api/cards');
    const data = await res.json();

    const grid = document.getElementById('card-stats-grid');
    grid.innerHTML = '';

    if (!data || data.length === 0) {
      grid.innerHTML =
        '<p class="no-data">No card data available yet. Report matches with decklists to see stats!</p>';
      return;
    }

    // Sort by accuracy score (win_rate × total games)
    data.sort((a, b) => b.win_rate * b.total - a.win_rate * a.total);
    allCards = data;
    filteredCards = data;

    // Update total count
    document.getElementById('total-count').textContent = data.length;

    // Render first batch
    renderMoreCards();

    // Set up filters
    const typeFilter = document.getElementById('type-filter');
    const searchInput = document.getElementById('card-search');
    typeFilter.addEventListener('change', applyFilters);
    searchInput.addEventListener('input', applyFilters);

    // Set up infinite scroll
    window.addEventListener('scroll', () => {
      if (
        window.innerHeight + window.scrollY >=
        document.body.offsetHeight - 500
      ) {
        renderMoreCards();
      }
    });
  } catch (err) {
    console.error('Error fetching card stats', err);
    document.getElementById('card-stats-grid').innerHTML =
      '<p class="no-data">Error loading card stats</p>';
  }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', fetchCardStats);
