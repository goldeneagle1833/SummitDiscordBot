import { get, post, del } from './client'

// Deck Rec endpoints (prefix: /api/deck-rec)
export const getDeckRecList = () => get('/api/deck-rec/decks')
export const getDeckInfo = (deckId) =>
  get(`/api/deck-rec/${encodeURIComponent(deckId)}/info`)
export const getDeckRecommendations = (deckId) =>
  get(`/api/deck-rec/${encodeURIComponent(deckId)}/recommendations`)

// Admin deck management
export const adminAddDeck = (body) => post('/api/deck-rec/admin/add-deck', body)
export const adminUpdateDeck = (deckId, body) =>
  fetch(`/api/deck-rec/admin/update-deck/${encodeURIComponent(deckId)}`, {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then((r) => r.json())
export const adminRemoveDeck = (deckId) =>
  del(`/api/deck-rec/admin/remove-deck/${encodeURIComponent(deckId)}`)

// Card detail (existing)
export const getDeck = (deckId) => get(`/api/cards/${deckId}`)
export const extractDeckId = (curiosaUrl) => {
  const match = curiosaUrl?.match(/\/decks\/([^/?]+)/)
  return match ? match[1] : null
}
