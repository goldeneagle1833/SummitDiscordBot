import { cloneElement } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

// jsdom has no layout: give the chart a fixed size so it actually draws
vi.mock('recharts', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, ResponsiveContainer: ({ children }) => cloneElement(children, { width: 600, height: 220 }) }
})
import EloHistory, { buildEloChartData, LEGACY_LABEL } from '../EloHistory'

// Lifetime moved to Glicko-2 at Season 9 and restarted at 1500; the old Elo
// lifetime is kept as Legacy ELO. Points carry their era.
const legacy = [
  { date: '2026-09-01T12:00:00', elo_after: 1780, elo_change: 12, result: 'Win', opponent: 'B', era: 'legacy' },
  { date: '2026-09-02T12:00:00', elo_after: 1792, elo_change: 12, result: 'Win', opponent: 'B', era: 'legacy' },
]
const glicko = [
  { date: '2027-01-05T12:00:00', elo_after: 1540, elo_change: 9, result: 'Win', opponent: 'C', era: 'glicko2' },
  { date: '2027-01-06T12:00:00', elo_after: 1528, elo_change: -12, result: 'Loss', opponent: 'C', era: 'glicko2' },
]

describe('buildEloChartData', () => {
  it('splits the eras into separate series with the switch marked', () => {
    const { chartData, hasGlicko, hasLegacy, switchIndex } = buildEloChartData([...legacy, ...glicko], 30)
    expect(hasGlicko).toBe(true)
    expect(hasLegacy).toBe(true)
    expect(chartData.map((d) => d.legacy)).toEqual([1780, 1792, null, null])
    expect(chartData.map((d) => d.lifetime)).toEqual([null, null, 1540, 1528])
    expect(switchIndex).toBe(2)
    expect(chartData[3].change).toBe(-12)
  })

  it('draws one line, as before, when there is no Glicko-2 lifetime yet', () => {
    const old = legacy.map(({ era, ...p }) => p)
    const { chartData, hasLegacy, switchIndex } = buildEloChartData(old, 30)
    expect(hasLegacy).toBe(false)
    expect(switchIndex).toBeNull()
    expect(chartData.map((d) => d.lifetime)).toEqual([1780, 1792])
  })

  it('has no marker when the window holds only Glicko-2 games', () => {
    const { hasLegacy, switchIndex } = buildEloChartData([...legacy, ...glicko], 2)
    expect(hasLegacy).toBe(false)
    expect(switchIndex).toBeNull()
  })
})

describe('EloHistory legend', () => {
  it('labels the Legacy ELO and Lifetime lines when both eras are shown', () => {
    render(<EloHistory eloHistory={[...legacy, ...glicko]} open onToggle={() => {}} />)
    expect(screen.getByText(LEGACY_LABEL)).toBeInTheDocument()
    expect(screen.getByText(/Lifetime \(Glicko-2, from 1500\)/)).toBeInTheDocument()
  })

  it('draws each era as its own line with a Glicko-2 marker between them', () => {
    const { container } = render(<EloHistory eloHistory={[...legacy, ...glicko]} open onToggle={() => {}} />)
    const lines = container.querySelectorAll('.recharts-area-curve')
    expect(lines).toHaveLength(2)
    expect(container.querySelectorAll('.recharts-reference-line')).toHaveLength(2) // 1500 line + switch
    expect(screen.getByText('Glicko-2')).toBeInTheDocument()
  })

  it('shows no era labels before the switch', () => {
    render(<EloHistory eloHistory={legacy.map(({ era, ...p }) => p)} open onToggle={() => {}} />)
    expect(screen.queryByText(LEGACY_LABEL)).not.toBeInTheDocument()
  })

  it('skips provisional (hidden) points', () => {
    const hidden = { date: '2027-01-04T12:00:00', elo_after: null, elo_after_hidden: true, era: 'glicko2' }
    const { chartData } = buildEloChartData([...legacy, ...glicko].filter((m) => m.elo_after != null), 30)
    render(<EloHistory eloHistory={[...legacy, hidden, ...glicko]} open onToggle={() => {}} />)
    expect(screen.getByText(`Games: ${chartData.length}`)).toBeInTheDocument()
  })
})
