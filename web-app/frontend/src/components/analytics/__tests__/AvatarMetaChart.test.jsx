import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import AvatarMetaChart from '../AvatarMetaChart'
import { buildCumulative } from '@/utils/elementTimeline'

const DATES = ['2026-09-01', '2026-09-02', '2026-09-03']
const CUM = buildCumulative(DATES, {
  Sorcerer: { '2026-09-01': 2, '2026-09-03': 1 },
  Druid: { '2026-09-03': 4 },
})

describe('AvatarMetaChart', () => {
  it('ranks avatars for the window with share and change', () => {
    render(<AvatarMetaChart cumulative={CUM} endIdx={2} days={1} />)
    const rows = screen.getAllByTestId('meta-row')
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent('Druid')
    expect(rows[0]).toHaveTextContent('4 · 80.0%▲4')
    expect(rows[1]).toHaveTextContent('Sorcerer')
  })

  it('counts everything so far for all time', () => {
    render(<AvatarMetaChart cumulative={CUM} endIdx={0} days={null} />)
    const rows = screen.getAllByTestId('meta-row')
    expect(rows).toHaveLength(1)
    expect(rows[0]).toHaveTextContent('100.0%')
  })

  it('says so when the window is empty', () => {
    render(<AvatarMetaChart cumulative={CUM} endIdx={1} days={1} />)
    expect(screen.getByText('No decks reported in this window.')).toBeInTheDocument()
  })
})
