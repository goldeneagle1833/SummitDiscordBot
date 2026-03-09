/**
 * Deck Snapshot Page
 * Displays a player's deck from a specific match
 */

const matchId = window.MATCH_ID;
const playerId = window.PLAYER_ID;

/**
 * Get mana cost from various possible field names
 * @param {Object} card - Card object
 * @returns {number} Mana cost value
 */
function getManaCost(card) {
  return card.threshold || card.cost || card.mana || card.mana_cost || 0;
}

/**
 * Normalize and determine card type
 * @param {Object} card - Card object
 * @returns {string} Normalized card type
 */
function getCardType(card) {
  const type = (card.type || '').toLowerCase();
  if (type.includes('minion')) return 'Minion';
  if (type.includes('magic')) return 'Magic';
  if (type.includes('artifact')) return 'Artifact';
  if (type.includes('aura')) return 'Aura';
  if (type.includes('site')) return 'Site';
  return 'Other';
}

/**
 * Render a list of cards sorted by mana cost
 * @param {Array} cards - Array of card objects
 * @param {string} listId - ID of the list element
 * @param {string} sectionId - ID of the section container
 */
function renderCardList(cards, listId, sectionId) {
  const list = document.getElementById(listId);
  const section = document.getElementById(sectionId);

  if (!cards || cards.length === 0) {
    section.classList.add('hidden');
    return;
  }

  list.innerHTML = '';

  // Sort cards by mana cost (lowest first)
  const sortedCards = [...cards].sort((a, b) => {
    return getManaCost(a) - getManaCost(b);
  });

  // Render each card with its quantity
  sortedCards.forEach((card) => {
    const li = document.createElement('li');
    li.className = 'card-list-item';
    const cost = getManaCost(card);
    const quantity = card.quantity || 1;
    const costDisplay = cost > 0 ? `<span class="card-cost">${cost}</span>` : '';
    li.innerHTML = `<span class="card-count">${quantity}x</span> <span class="card-name">${card.name}</span>${costDisplay}`;
    list.appendChild(li);
  });

  section.classList.remove('hidden');
}

/**
 * Filter cards by type
 * @param {Array} cards - Array of card objects
 * @param {string} type - Card type to filter by
 * @returns {Array} Filtered cards
 */
function filterByType(cards, type) {
  if (!cards) return [];
  return cards.filter((card) => getCardType(card) === type);
}

/**
 * Fetch and display deck data from the API
 */
async function fetchDeckData() {
  try {
    const res = await fetch(`/api/deck-snapshot/${matchId}/${playerId}`);

    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.error || 'Failed to load deck data');
    }

    const data = await res.json();

    // Update header
    const deckName = data.deck.name || 'Unnamed Deck';
    document.getElementById('deck-title').textContent = deckName;
    document.title = `${deckName} - Deck Snapshot - Sorcerers Summit`;

    // Update avatar (compact display)
    if (data.deck.avatar && data.deck.avatar.length > 0) {
      const avatarName = data.deck.avatar[0].name || 'Unknown Avatar';
      document.getElementById('deck-avatar').textContent = avatarName;
    }

    // Update match info
    const date = new Date(data.date).toLocaleDateString();
    const resultClass = data.result === 'Win' ? 'match-win' : 'match-loss';
    document.getElementById('match-info').innerHTML = `
      <span class="${resultClass}">${data.result}</span> vs ${data.opponent_name} on ${date}
    `;

    // Split spellbook by card type
    const spellbook = data.deck.spellbook || [];
    const minions = filterByType(spellbook, 'Minion');
    const magic = filterByType(spellbook, 'Magic');
    const artifacts = filterByType(spellbook, 'Artifact');
    const auras = filterByType(spellbook, 'Aura');

    // Render spellbook sections
    renderCardList(minions, 'minions-list', 'minions-section');
    renderCardList(magic, 'magic-list', 'magic-section');
    renderCardList(artifacts, 'artifacts-list', 'artifacts-section');
    renderCardList(auras, 'auras-list', 'auras-section');

    // Render other sections
    renderCardList(data.deck.atlas, 'sites-list', 'sites-section');
    renderCardList(data.deck.sideboard, 'collection-list', 'collection-section');

    // Show content
    document.getElementById('deck-content').classList.remove('hidden');
  } catch (error) {
    document.getElementById('deck-title').textContent = 'Error';
    document.getElementById('error-message').textContent = error.message;
    document.getElementById('error-message').classList.remove('hidden');
    console.error(error);
  }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', fetchDeckData);
