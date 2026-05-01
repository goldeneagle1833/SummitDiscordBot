import { get } from './client'

export const getDeck = (deckId) => get(`/api/cards/${deckId}`)
export const extractDeckId = (curiosaUrl) => {
  const match = curiosaUrl?.match(/\/decks\/([^/?]+)/)
  return match ? match[1] : null
}
