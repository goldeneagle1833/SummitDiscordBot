/**
 * Deck Stats Page
 * Shows win rates, matchup breakdown, and match history for a specific deck.
 */

const playerId = window.PLAYER_ID;
const deckUrl  = window.DECK_URL;

function show(id)  { document.getElementById(id).classList.remove('hidden'); }
function hide(id)  { document.getElementById(id).classList.add('hidden'); }
function el(id)    { return document.getElementById(id); }

function winRateColor(rate) {
  if (rate >= 60) return 'positive';
  if (rate >= 40) return 'neutral';
  return 'negative';
}

function renderSummary(data) {
  el('ds-wins').textContent    = data.wins;
  el('ds-losses').textContent  = data.losses;
  el('ds-total').textContent   = data.total;

  const wr = el('ds-winrate');
  wr.textContent = `${data.win_rate}%`;
  wr.className   = `ds-stat-value ${winRateColor(data.win_rate)}`;

  function playDrawLabel(bucket) {
    if (bucket.total === 0) return '—';
    return `${bucket.win_rate}% (${bucket.wins}W-${bucket.losses}L)`;
  }
  el('ds-on-play').textContent = playDrawLabel(data.on_play);
  el('ds-on-draw').textContent = playDrawLabel(data.on_draw);

  show('ds-summary');
}

function renderMatchups(matchups) {
  if (!matchups || matchups.length === 0) return;
  const grid = el('ds-matchups-grid');
  grid.innerHTML = '';
  matchups.forEach(m => {
    const colorClass = winRateColor(m.win_rate);
    const card = document.createElement('div');
    card.className = 'ds-matchup-card';
    card.innerHTML = `
      <div class="ds-matchup-avatar">${m.opponent_avatar}</div>
      <div class="ds-matchup-record">${m.wins}W – ${m.losses}L (${m.total} games)</div>
      <div class="ds-matchup-rate ${colorClass}">${m.win_rate}%</div>
    `;
    grid.appendChild(card);
  });
  show('ds-matchups-section');
}

function renderHistory(matches) {
  if (!matches || matches.length === 0) return;
  const tbody = el('ds-history-body');
  tbody.innerHTML = '';
  matches.forEach(m => {
    const date      = m.date ? new Date(m.date).toLocaleDateString() : '—';
    const resultCls = m.result === 'Win' ? 'ds-result-win' : 'ds-result-loss';
    const eloVal    = m.elo_change != null ? m.elo_change : null;
    const eloCls    = eloVal == null ? '' : (eloVal >= 0 ? 'ds-elo-pos' : 'ds-elo-neg');
    const eloText   = eloVal == null ? '—' : (eloVal >= 0 ? `+${eloVal}` : `${eloVal}`);
    const time      = m.match_time ? `${m.match_time}m` : '—';
    const oppLink   = m.opponent_id
      ? `<a href="/player/${m.opponent_id}" style="color:inherit;text-decoration:none">${m.opponent}</a>`
      : m.opponent;

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${date}</td>
      <td class="${resultCls}">${m.result}</td>
      <td>${oppLink}</td>
      <td>${m.opponent_avatar || '—'}</td>
      <td class="${eloCls}">${eloText}</td>
      <td>${time}</td>
    `;
    tbody.appendChild(tr);
  });
  show('ds-history-section');
}

async function loadDeckStats() {
  try {
    const params = new URLSearchParams({ url: deckUrl });
    const res = await fetch(`/api/players/${playerId}/deck-stats?${params}`);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    const data = await res.json();

    // Header
    el('ds-deck-name').textContent  = data.deck_name || 'Unnamed Deck';
    el('ds-avatar').textContent     = data.avatar ? `🎭 ${data.avatar}` : '';
    el('ds-deck-link').href         = data.url;
    document.title                  = `${data.deck_name || 'Deck'} Stats – Sorcerers Summit`;
    show('ds-header');

    renderSummary(data);
    renderMatchups(data.matchups);
    renderHistory(data.matches);

    hide('loading-state');
  } catch (err) {
    hide('loading-state');
    el('error-state').textContent = err.message;
    show('error-state');
  }
}

document.addEventListener('DOMContentLoaded', loadDeckStats);
