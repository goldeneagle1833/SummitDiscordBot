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
    if (card.image) {
      li.dataset.cardImage = card.image;
      li.style.cursor = 'pointer';
    }
    const cost = getManaCost(card);
    const quantity = card.quantity || 1;
    const costDisplay = cost > 0 ? `<span class="card-cost">${cost}</span>` : '';
    li.innerHTML = `<span class="card-count">${quantity}x</span> <span class="card-name">${card.name}</span>${costDisplay}`;

    if (card.image) {
      li.addEventListener('mouseenter', () => showCardPreview(card.image, li));
      li.addEventListener('mouseleave', hideCardPreview);
      li.addEventListener('wheel', (e) => {
        if (!_preview || !_preview.classList.contains('visible')) return;
        e.preventDefault();
        const delta = e.deltaY > 0 ? -0.1 : 0.1;
        _previewScale = Math.min(3.0, Math.max(0.4, _previewScale + delta));
        _preview.querySelector('img').style.width = `${Math.round(_BASE_WIDTH * _previewScale)}px`;
      }, { passive: false });
    }

    list.appendChild(li);
  });

  section.classList.remove('hidden');
}

// ---------------------------------------------------------------------------
// Card image preview popup
// ---------------------------------------------------------------------------

let _preview = null;
let _previewScale = 1.0;
const _BASE_WIDTH = 220;
let _hideTimeout = null;

function _cancelHide() {
  if (_hideTimeout) {
    clearTimeout(_hideTimeout);
    _hideTimeout = null;
  }
}

function _scheduleHide() {
  _cancelHide();
  _hideTimeout = setTimeout(() => {
    if (_preview) _preview.classList.remove('visible');
  }, 80);
}

function _getOrCreatePreview() {
  if (!_preview) {
    _preview = document.createElement('div');
    _preview.id = 'deck-card-preview';
    _preview.innerHTML = `
      <button class="deck-card-preview__close" aria-label="Close preview">✕</button>
      <img alt="Card preview">
    `;
    document.body.appendChild(_preview);

    // Keep visible while mouse is over the popup itself
    _preview.addEventListener('mouseenter', _cancelHide);
    _preview.addEventListener('mouseleave', _scheduleHide);

    // Close button
    _preview.querySelector('.deck-card-preview__close').addEventListener('click', (e) => {
      e.stopPropagation();
      _cancelHide();
      _preview.classList.remove('visible');
    });

    // Scroll wheel to resize
    _preview.addEventListener('wheel', (e) => {
      e.preventDefault();
      const delta = e.deltaY > 0 ? -0.1 : 0.1;
      _previewScale = Math.min(3.0, Math.max(0.4, _previewScale + delta));
      _preview.querySelector('img').style.width = `${Math.round(_BASE_WIDTH * _previewScale)}px`;
    }, { passive: false });
  }
  return _preview;
}

function showCardPreview(imageFile, anchorEl) {
  _cancelHide();
  const popup = _getOrCreatePreview();
  popup.querySelector('img').src = `/card-images/${imageFile}`;
  popup.querySelector('img').style.width = `${Math.round(_BASE_WIDTH * _previewScale)}px`;
  _positionPreview(popup, anchorEl);
  popup.classList.add('visible');
}

function hideCardPreview() {
  _scheduleHide();
}

function _forceHidePreview() {
  _cancelHide();
  if (_preview) _preview.classList.remove('visible');
}

function _positionPreview(popup, anchorEl) {
  const rect = anchorEl.getBoundingClientRect();
  const popupW = Math.round(_BASE_WIDTH * _previewScale);
  const spaceRight = window.innerWidth - rect.right;
  const left = spaceRight >= popupW + 12
    ? rect.right + 8
    : rect.left - popupW - 8;
  const maxTop = window.innerHeight - 340;
  const top = Math.min(rect.top, Math.max(0, maxTop));
  popup.style.left = `${Math.max(4, left)}px`;
  popup.style.top = `${top}px`;
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
