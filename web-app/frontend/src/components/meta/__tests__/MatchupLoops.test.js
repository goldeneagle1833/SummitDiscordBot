import { describe, it, expect } from 'vitest'
import { deckGraph, findLoops, deckMatchups } from '@/components/meta/MatchupLoops'

const g = (w, l, n) => ({ winner: w, loser: l, n })
const NECRO = ['Necromancer', 'Air / Water']
const SORC = ['Sorcerer', 'Air / Earth']
const PATH = ['Pathfinder', 'Fire']
const FLAME = ['Flamecaller', 'Fire']

// Necro beats Sorcerer 60%, Sorcerer beats Pathfinder 65%, Pathfinder beats Necro 55%
const games = [
  g(NECRO, SORC, 12), g(SORC, NECRO, 8),
  g(SORC, PATH, 13), g(PATH, SORC, 7),
  g(PATH, NECRO, 11), g(NECRO, PATH, 9),
  g(FLAME, NECRO, 3), g(NECRO, NECRO, 50), // too few games / mirror
]

describe('matchup loops', () => {
  it('builds decks with enough games and no mirrors', () => {
    const graph = deckGraph(games)
    expect(graph.decks.map((d) => d.key).sort()).toEqual(['Necromancer|Air / Water', 'Pathfinder|Fire', 'Sorcerer|Air / Earth'])
    expect(graph.edges.get('Necromancer|Air / Water>Sorcerer|Air / Earth')).toEqual({ games: 20, winRate: 60 })
  })

  it('finds the loop once, in winning order, with its weakest arrow', () => {
    const loops = findLoops(deckGraph(games), 55)
    expect(loops).toHaveLength(1)
    const [l] = loops
    const order = l.decks.map((k) => k.split('|')[0])
    // rotation can differ; check each deck beats the next
    for (let i = 0; i < 3; i++) {
      expect(['Necromancer>Sorcerer', 'Sorcerer>Pathfinder', 'Pathfinder>Necromancer']).toContain(`${order[i]}>${order[(i + 1) % 3]}`)
    }
    expect(l.strength).toBe(55)
    expect(l.games).toBe(60)
  })

  it('drops a loop when an arrow is below the threshold or has too few games', () => {
    expect(findLoops(deckGraph(games), 60)).toHaveLength(0)
    expect(findLoops(deckGraph(games), 52, 25)).toHaveLength(0)
  })

  it('lists what a deck beats and loses to', () => {
    const m = deckMatchups(deckGraph(games), 'Necromancer|Air / Water')
    expect(m.beats.map((r) => r.avatar)).toEqual(['Sorcerer'])
    expect(m.losesTo.map((r) => [r.avatar, r.vs.winRate])).toEqual([['Pathfinder', 45]])
  })
})
