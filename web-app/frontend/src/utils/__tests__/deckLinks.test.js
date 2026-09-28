import { describe, it, expect } from 'vitest'
import { getPsoDeckId, getDeckSource, getDeckSourceLabel, psoDeckUrl } from '../deckLinks'

describe('deckLinks', () => {
  it('reads the deck id out of a Play Sorcery Online link', () => {
    expect(getPsoDeckId('https://playsorceryonline.com/?deck=pD-1gXa3cg8c')).toBe('pD-1gXa3cg8c')
    expect(getPsoDeckId('https://www.playsorceryonline.com/?foo=1&deck=pD-1gXa3cg8c')).toBe('pD-1gXa3cg8c')
  })

  it('rejects PSO links that are not deck links', () => {
    expect(getPsoDeckId('https://playsorceryonline.com/?table=abc123')).toBeNull()
    expect(getPsoDeckId('https://playsorceryonline.com/?deck=')).toBeNull()
    expect(getPsoDeckId('https://sorcerytcg.com/?deck=pD-1gXa3cg8c')).toBeNull()
    expect(getPsoDeckId('not a url')).toBeNull()
    expect(getPsoDeckId(null)).toBeNull()
  })

  it('tells Curiosa and Sorcery Online links apart', () => {
    expect(getDeckSource('https://sorcerytcg.com/decks/clx1abc23')).toBe('curiosa')
    expect(getDeckSource('https://curiosa.io/decks/clx1abc23?tab=view')).toBe('curiosa')
    expect(getDeckSource('https://playsorceryonline.com/?deck=pD-1gXa3cg8c')).toBe('sorcery_online')
    expect(getDeckSource('https://draftsorcery.com/?deck=xyz')).toBeNull()
  })

  it('labels the View link by where the deck lives', () => {
    expect(getDeckSourceLabel('https://sorcerytcg.com/decks/clx1abc23')).toBe('Curiosa')
    expect(getDeckSourceLabel('https://playsorceryonline.com/?deck=pD-1gXa3cg8c')).toBe('Sorcery Online')
    expect(getDeckSourceLabel('https://example.com/deck')).toBe('deck site')
  })

  it('builds the canonical PSO share link', () => {
    expect(psoDeckUrl('pD-1gXa3cg8c')).toBe('https://playsorceryonline.com/?deck=pD-1gXa3cg8c')
  })
})
