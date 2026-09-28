import { get } from './client'

// Server-side proxy to Play Sorcery Online's Summit ranked analytics.
// The shared partner key lives on the Flask side; see routes/api/ranked_analytics.py.
export const RANKED_ANALYTICS_ENDPOINT = '/api/ranked-analytics'

const withQuery = (path, params) => {
  const query = params ? new URLSearchParams(params).toString() : ''
  return `${RANKED_ANALYTICS_ENDPOINT}${path}${query ? `?${query}` : ''}`
}

export const getRankedCards = (params) => get(withQuery('/cards', params))
export const getRankedCardReplays = (cardKey, params) =>
  get(withQuery(`/cards/${encodeURIComponent(cardKey)}/replays`, params))
export const getRankedCatalog = () => get(withQuery('/catalog'))
