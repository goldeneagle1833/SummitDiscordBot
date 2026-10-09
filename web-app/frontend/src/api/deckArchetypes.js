import { get } from './client'

// Archetypes are built on the server from Top 8 tournament decks and every
// ranked match deck. source: 'all' (default) or 'tournament'.
export const getDeckArchetypes = (source = 'all') =>
  get(`/api/deck-archetypes?${new URLSearchParams({ source })}`)

export const getDeckArchetype = (groupId, source = 'all') =>
  get(`/api/deck-archetypes/${encodeURIComponent(groupId)}?${new URLSearchParams({ source })}`)
