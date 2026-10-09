import { describe, it, expect } from 'vitest'
import {
  mergeDates, buildCumulative, windowSum, countsAt, flattenElementDays, elementStatsAt,
} from '../elementTimeline'

describe('mergeDates', () => {
  it('fills every day across both lists', () => {
    expect(mergeDates(['2026-02-27'], ['2026-03-02'])).toEqual(
      ['2026-02-27', '2026-02-28', '2026-03-01', '2026-03-02'],
    )
    expect(mergeDates([], [])).toEqual([])
  })
})

describe('windows', () => {
  const dates = ['2026-09-01', '2026-09-02', '2026-09-03']
  const cum = buildCumulative(dates, { A: { '2026-09-01': 2, '2026-09-03': 1 }, B: { '2026-09-03': 4 } })

  it('sums a trailing window or everything so far', () => {
    expect(windowSum(cum.A, 2, null)).toBe(3)
    expect(windowSum(cum.A, 2, 2)).toBe(1)
    expect(windowSum(cum.A, 2, 3)).toBe(3)
  })

  it('ranks and drops zeros', () => {
    expect(countsAt(cum, 2, null)).toEqual([{ name: 'B', count: 4 }, { name: 'A', count: 3 }])
    expect(countsAt(cum, 1, 1)).toEqual([])
  })
})

describe('elementStatsAt', () => {
  const days = {
    '2026-09-01': {
      el: { Fire: [3, 1], Water: [1, 0] },
      dom: { Fire: [3, 1] },
      spl: { Water: [1, 0] },
      combo: { 'Fire, Water': [2, 1], Fire: [1, 0] },
    },
    '2026-09-02': { el: { Earth: [0, 2] }, dom: { Earth: [0, 2] } },
  }
  const dates = ['2026-09-01', '2026-09-02']
  const cum = buildCumulative(dates, flattenElementDays(days))

  it('rebuilds the /api/elements shape for all time', () => {
    const s = elementStatsAt(cum, 1, null)
    expect(s.elements.find((e) => e.name === 'Fire')).toEqual({
      name: 'Fire', wins: 3, losses: 1, total: 4, win_rate: 75, win_presence: 75, loss_presence: 33.3,
    })
    expect(s.elements.find((e) => e.name === 'Air')).toMatchObject({ total: 0, win_rate: 50 })
    expect(s.dominant.find((e) => e.name === 'Earth')).toMatchObject({ wins: 0, losses: 2 })
    expect(s.splash.find((e) => e.name === 'Water')).toMatchObject({ wins: 1, total: 1 })
    expect(s.combinations).toEqual([{ name: 'Fire, Water', wins: 2, losses: 1, total: 3, win_rate: 66.7 }])
    expect(s.composition).toEqual([
      { elements: 'Fire, Water', count: 3, percent: 75 },
      { elements: 'Fire', count: 1, percent: 25 },
    ])
  })

  it('only counts the window', () => {
    const s = elementStatsAt(cum, 1, 1)
    expect(s.elements.find((e) => e.name === 'Fire').total).toBe(0)
    expect(s.elements.find((e) => e.name === 'Earth').losses).toBe(2)
    expect(s.combinations).toEqual([])
  })

  it('has no splash or combos for non-admin data', () => {
    const pub = buildCumulative(dates, flattenElementDays({ '2026-09-01': { el: { Fire: [1, 0] }, dom: {} } }))
    const s = elementStatsAt(pub, 1, null)
    expect(s.splash).toEqual([])
    expect(s.composition).toEqual([])
  })
})
