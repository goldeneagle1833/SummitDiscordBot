/**
 * Page: Elemental Win Rates
 * Template: templates/pages/elements.html
 * Description: Handles element statistics charts, win rates, presence analysis, and deck composition
 */

document.addEventListener('DOMContentLoaded', () => {
  fetchElementStats();
  fetchDeckComposition();
});

/**
 * Get element color class for combo labels
 * @param {string} elementName - Element name
 * @returns {string} CSS class name
 */
function getElementColorClass(elementName) {
  const el = elementName.toLowerCase().trim();
  if (el === 'fire') return 'element-fire';
  if (el === 'water') return 'element-water';
  if (el === 'earth') return 'element-earth';
  if (el === 'air') return 'element-air';
  return '';
}

/**
 * Render element bars (used for charts 1 and 3)
 * @param {Array} data - Element data array
 * @param {string} containerId - Target container ID
 * @param {boolean} sortByWinRate - Whether to sort by win rate
 */
function renderElementBars(data, containerId, sortByWinRate = true) {
  const container = document.getElementById(containerId);
  if (!data || data.length === 0) {
    container.innerHTML = '<p class="loading-text">No data available.</p>';
    return;
  }

  const sorted = sortByWinRate
    ? [...data].sort((a, b) => b.win_rate - a.win_rate)
    : data;

  let html = '';
  sorted.forEach((element) => {
    const elementClass = `element-${element.name.toLowerCase()}`;
    html += `
      <div class="element-row ${elementClass}">
        <div class="element-label">${element.name}</div>
        <div class="element-bar-container">
          <div class="element-bar" style="width: ${element.win_rate}%;">
            <span class="element-bar-text">${element.win_rate}%</span>
          </div>
        </div>
        <div class="element-stats">
          ${element.wins}W - ${element.losses}L
        </div>
      </div>
    `;
  });
  container.innerHTML = html;
}

/**
 * Render combo bars (for chart 5)
 * @param {Array} combos - Combination data array
 * @param {string} containerId - Target container ID
 */
function renderComboBars(combos, containerId) {
  const container = document.getElementById(containerId);
  if (!combos || combos.length === 0) {
    container.innerHTML = '<p class="loading-text">No combination data available yet.</p>';
    return;
  }

  // Sort by win rate descending
  const sorted = [...combos].sort((a, b) => b.win_rate - a.win_rate);

  let html = '';
  sorted.forEach((combo) => {
    const elements = combo.name.split(', ');
    // Determine bar color class
    let barElementClass = 'element-multi';
    if (elements.length === 1) {
      barElementClass = getElementColorClass(elements[0]) || 'element-multi';
    }

    // Render element names with individual colors
    const labelHtml = elements
      .map((el) => {
        const colorClass = getElementColorClass(el);
        return `<span class="${colorClass}" style="text-shadow: 0 0 10px currentColor;">${el.trim()}</span>`;
      })
      .join(' / ');

    html += `
      <div class="composition-row ${barElementClass}">
        <div class="composition-label">${labelHtml}</div>
        <div class="composition-bar-container">
          <div class="composition-bar" style="width: ${combo.win_rate}%;"></div>
          <span class="composition-bar-text">${combo.win_rate}%</span>
        </div>
        <div class="composition-stats">
          ${combo.wins}W - ${combo.losses}L (${combo.total})
        </div>
      </div>
    `;
  });
  container.innerHTML = html;
}

/**
 * Fetch and render element statistics
 */
async function fetchElementStats() {
  try {
    const res = await fetch('/api/elements');
    const data = await res.json();

    const container = document.getElementById('element-bars');
    const presenceContainer = document.getElementById('presence-bars');
    const dominantContainer = document.getElementById('dominant-bars');
    const comboContainer = document.getElementById('combo-bars');

    // Handle both old array format and new object format
    const elements = Array.isArray(data) ? data : data.elements;
    const dominant = data.dominant || [];
    const splash = data.splash || [];
    const combinations = data.combinations || [];

    if (!elements || elements.length === 0) {
      container.innerHTML = '<p class="loading-text">No element data available yet. Report matches with decklists to see stats!</p>';
      presenceContainer.innerHTML = '';
      dominantContainer.innerHTML = '';
      comboContainer.innerHTML = '';
      return;
    }

    // Chart 1: Win Rate by Element (with overlap)
    renderElementBars(elements, 'element-bars');

    // Chart 2: Presence - sort by win presence descending
    const sortedByPresence = [...elements].sort(
      (a, b) => b.win_presence - a.win_presence
    );
    let presenceHtml = '';
    sortedByPresence.forEach((element) => {
      const elementClass = `element-${element.name.toLowerCase()}`;
      presenceHtml += `
        <div class="presence-row ${elementClass}">
          <div class="presence-label">${element.name}</div>
          <div class="presence-bar-group">
            <div class="presence-bar-row">
              <div class="presence-bar-label">Wins</div>
              <div class="presence-bar-container">
                <div class="presence-bar wins" style="width: ${element.win_presence}%;">
                  <span class="presence-bar-text">${element.win_presence}%</span>
                </div>
              </div>
            </div>
            <div class="presence-bar-row">
              <div class="presence-bar-label">Losses</div>
              <div class="presence-bar-container">
                <div class="presence-bar losses" style="width: ${element.loss_presence}%;">
                  <span class="presence-bar-text">${element.loss_presence}%</span>
                </div>
              </div>
            </div>
          </div>
          <div class="presence-stats">
            Δ ${(element.win_presence - element.loss_presence).toFixed(1)}%
          </div>
        </div>
      `;
    });
    presenceContainer.innerHTML = presenceHtml;

    // Chart 3: Dominant Element Win Rates (public)
    renderElementBars(dominant, 'dominant-bars');

    // Chart 4: Splash Element Win Rates (admin only)
    if (splash && splash.length > 0) {
      document.getElementById('splash-container').classList.remove('hidden');
      renderElementBars(splash, 'splash-bars');
    }

    // Chart 5: Element Combination Win Rates (admin only)
    if (combinations && combinations.length > 0) {
      document.getElementById('combo-container').classList.remove('hidden');
      renderComboBars(combinations, 'combo-bars');
    }
  } catch (err) {
    console.error('Error fetching element stats', err);
    document.getElementById('element-bars').innerHTML = '<p class="loading-text">Error loading element stats</p>';
    document.getElementById('presence-bars').innerHTML = '';
    document.getElementById('dominant-bars').innerHTML = '';
    document.getElementById('splash-bars').innerHTML = '';
    document.getElementById('combo-bars').innerHTML = '';
  }
}

/**
 * Fetch and render deck composition data (admin only)
 */
async function fetchDeckComposition() {
  try {
    const res = await fetch('/api/deck-composition');

    // Check if user has permission
    if (res.status === 403) {
      // Hide the section if no permission
      document.getElementById('deck-composition-container').classList.add('hidden');
      return;
    }

    if (!res.ok) {
      document.getElementById('composition-bars').innerHTML = '<p class="loading-text">Error loading deck composition</p>';
      return;
    }

    const data = await res.json();
    const container = document.getElementById('composition-bars');

    if (!data || !data.composition || data.composition.length === 0) {
      container.innerHTML = '<p class="loading-text">No deck data available yet.</p>';
      document.getElementById('deck-composition-container').classList.remove('hidden');
      return;
    }

    // Show the section
    document.getElementById('deck-composition-container').classList.remove('hidden');

    // Render composition bars
    let html = '';
    data.composition.forEach((item) => {
      // Determine element class based on composition (for bar color)
      let barElementClass = 'element-multi';
      const elements = item.elements.split(', ');
      if (elements.length === 1) {
        const el = elements[0].toLowerCase();
        if (el === 'fire') barElementClass = 'element-fire';
        else if (el === 'water') barElementClass = 'element-water';
        else if (el === 'earth') barElementClass = 'element-earth';
        else if (el === 'air') barElementClass = 'element-air';
      }

      // Render element names with individual colors
      let labelHtml = elements
        .map((el) => {
          const colorClass = getElementColorClass(el);
          return `<span class="element-name ${colorClass}">${el}</span>`;
        })
        .join(', ');

      html += `
        <div class="composition-row ${barElementClass}">
          <div class="composition-label">${labelHtml}</div>
          <div class="composition-bar-container">
            <div class="composition-bar" style="width: ${item.percent}%;"></div>
            <span class="composition-bar-text">${item.percent}%</span>
          </div>
          <div class="composition-stats">
            ${item.count} deck${item.count !== 1 ? 's' : ''}
          </div>
        </div>
      `;
    });

    container.innerHTML = html;
  } catch (error) {
    console.error('Error fetching deck composition:', error);
    document.getElementById('composition-bars').innerHTML = '<p class="loading-text">Error loading deck composition</p>';
  }
}
