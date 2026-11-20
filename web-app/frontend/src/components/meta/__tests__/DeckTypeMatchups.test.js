import { describe, it, expect } from 'vitest'
import { deckTypeMatchups } from '@/components/meta/DeckTypeMatchups'

// Same games as tests/test_meta_report.py, so the page and the server agree.
const g = (w, l, n) => ({ winner: w, loser: l, n })

describe('deckTypeMatchups', () => {
  it('matches the Meta Report numbers', () => {
    const dt = deckTypeMatchups([
      g(['B', 'Water'], ['A', 'Fire'], 8),
      g(['A', 'Fire'], ['B', 'Water'], 4),
      g(['A', 'Fire'], ['C', 'Air / Earth'], 9),
      g(['C', 'Air / Earth'], ['A', 'Fire'], 1),
      g(['D', 'Fire'], ['A', 'Fire'], 30),
    ], 20)
    const keys = dt.options.map((o) => o.key)
    expect(keys[0]).toBe('Fire')
    expect(keys).toContain('any:Fire')
    expect(keys).not.toContain('Water')
    const mono = dt.picks['Fire|']
    expect(mono.games).toBe(22)
    expect(mono.winRate).toBe(59.1)
    expect(mono.deckType[0]).toEqual({ elements: 'Water', games: 12, winRate: 33.3 })
    expect(dt.picks['Fire|A'].games).toBe(52)
    expect(dt.picks['Fire|A'].both).toContainEqual({ avatar: 'D', elements: 'Fire', games: 30, winRate: 0 })
  })

  it('uses max(20, 1% of deck-games) when no minimum is given', () => {
    const dt = deckTypeMatchups([g(['A', 'Fire'], ['B', 'Water'], 1500)])
    expect(dt.minDeckGames).toBe(30)
    expect(deckTypeMatchups([g(['A', 'Fire'], ['B', 'Water'], 15)]).options).toEqual([])
  })
})
