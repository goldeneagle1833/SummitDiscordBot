import { describe, it, expect } from 'vitest'
import { layoutBracket, describeProgress, visibleRounds } from '../bracketCanvas'

const match = (position, extra = {}) => ({
  match_no: position,
  position,
  state: 'pending',
  p1_name: `A${position}`,
  p2_name: `B${position}`,
  p1_seed: position,
  p2_seed: 9 - position,
  ...extra,
})

// An 8-player tree: 4 quarterfinals, 2 semis, a final.
const ROUNDS = [
  { round: 1, title: 'Quarterfinals', matches: [1, 2, 3, 4].map((p) => match(p, { playable: true })) },
  { round: 2, title: 'Semifinals', matches: [1, 2].map((p) => match(p, { p1_name: null, p2_name: null })) },
  { round: 3, title: 'Final', matches: [match(1, { p1_name: null, p2_name: null })] },
]

describe('layoutBracket', () => {
  it('lays rounds out left to right with a champion column', () => {
    const layout = layoutBracket(ROUNDS, { format: 'landscape' })
    expect(layout.cards).toHaveLength(7)
    const xs = (round) => [...new Set(layout.cards.filter((c) => c.round === round).map((c) => c.x))]
    expect(xs(1)).toHaveLength(1)
    expect(xs(1)[0]).toBeLessThan(xs(2)[0])
    expect(xs(2)[0]).toBeLessThan(xs(3)[0])
    expect(layout.champion.x).toBeGreaterThan(xs(3)[0])
    // Six feeder connectors plus the line to the champion.
    expect(layout.lines).toHaveLength(7)
  })

  it('keeps every card inside the canvas', () => {
    for (const format of ['landscape', 'square', 'portrait', 'story']) {
      const layout = layoutBracket(ROUNDS, { format })
      for (const card of layout.cards) {
        expect(card.x).toBeGreaterThanOrEqual(0)
        expect(card.y).toBeGreaterThanOrEqual(0)
        expect(card.x + card.width).toBeLessThanOrEqual(layout.width)
        expect(card.y + card.height).toBeLessThanOrEqual(layout.height)
      }
    }
  })

  it('places a match by its position so byes leave a gap', () => {
    const rounds = [
      { round: 1, title: 'Round 1', matches: [match(2)] },
      { round: 2, title: 'Final', matches: [match(1)] },
    ]
    const layout = layoutBracket(rounds, {})
    const first = layout.cards.find((c) => c.round === 1)
    const final = layout.cards.find((c) => c.round === 2)
    // Position 2 of 2 sits in the lower half.
    expect(first.y + first.height / 2).toBeGreaterThan(final.y + final.height / 2)
  })

  it('can start from a later round', () => {
    const layout = layoutBracket(ROUNDS, { startRound: 2, showChampion: false })
    expect(layout.cards.map((c) => c.round)).toEqual([2, 2, 3])
    expect(layout.labels.map((l) => l.text)).toEqual(['Semifinals', 'Final'])
  })

  it('returns nothing to draw for an empty bracket', () => {
    expect(layoutBracket([], {}).cards).toEqual([])
  })
})

describe('visibleRounds', () => {
  it('falls back to every round when the start is past the end', () => {
    expect(visibleRounds(ROUNDS, 9)).toBe(ROUNDS)
  })
})

describe('describeProgress', () => {
  it('names the live round', () => {
    expect(
      describeProgress({ bracket: { status: 'published' }, entrants: new Array(8), rounds: ROUNDS }),
    ).toBe('8 players · Quarterfinals in progress · 0/7 matches played')
  })

  it('says when a bracket is done', () => {
    expect(
      describeProgress({
        bracket: { status: 'complete' },
        entrants: new Array(8),
        rounds: ROUNDS,
        champion: { display_name: 'A1' },
      }),
    ).toBe('8 players · final results')
  })
})
