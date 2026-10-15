import { describe, it, expect } from 'vitest'
import { compareNewest, compareOldest } from '../DeckRecommendations'

// event_rank = position on the Top 8 page (0 = newest)
const decks = [
  { deck_name: 'a', event_rank: 2, cluster_size: 9 },
  { deck_name: 'b', event_rank: 0, cluster_size: 1 },
  { deck_name: 'c', event_rank: null, cluster_size: 50 },
  { deck_name: 'd', event_rank: 5, cluster_size: 3 },
  { deck_name: 'e', event_rank: 0, cluster_size: 4 },
]

describe('Deck Rec sorting', () => {
  it('follows the Top 8 page order, bigger archetype first within an event, unlisted last', () => {
    expect([...decks].sort(compareNewest).map((d) => d.deck_name)).toEqual(['e', 'b', 'a', 'd', 'c'])
  })

  it('oldest first reverses the events but still leaves unlisted decks at the end', () => {
    expect([...decks].sort(compareOldest).map((d) => d.deck_name)).toEqual(['d', 'a', 'e', 'b', 'c'])
  })
})
