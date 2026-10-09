import { get } from './client'

// Archetypes are built on the server from Top 8 tournament decks and every
// ranked match deck. source: 'all' (default) or 'tournament'.
// filters: { from, to } (YYYY-MM-DD) and minEventDecks; empty values are left out.
function query(source, filters = {}) {
  const params = { source }
  if (filters.from) params.from = filters.from
  if (filters.to) params.to = filters.to
  if (filters.minEventDecks) params.min_event_decks = String(filters.minEventDecks)
  return new URLSearchParams(params)
}

export const getDeckArchetypes = (source = 'all', filters) =>
  get(`/api/deck-archetypes?${query(source, filters)}`)

export const getDeckArchetype = (groupId, source = 'all', filters) =>
  get(`/api/deck-archetypes/${encodeURIComponent(groupId)}?${query(source, filters)}`)
