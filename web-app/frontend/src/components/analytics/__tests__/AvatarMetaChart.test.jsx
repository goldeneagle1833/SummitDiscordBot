import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import AvatarMetaChart, { buildCumulative, countsAt } from '../AvatarMetaChart'

vi.mock('@/api/client', () => ({ get: vi.fn() }))
vi.mock('@/api/cards', () => ({ getAvatarImageFiles: vi.fn(() => Promise.resolve([])) }))

import { get } from '@/api/client'

const DATES = ['2026-09-01', '2026-09-02', '2026-09-03']
const AVATARS = {
  Sorcerer: { '2026-09-01': 2, '2026-09-03': 1 },
  Druid: { '2026-09-03': 4 },
}

describe('countsAt', () => {
  const cum = buildCumulative(DATES, AVATARS)

  it('sums everything up to the day for all time', () => {
    expect(countsAt(cum, 1, null)).toEqual([{ name: 'Sorcerer', count: 2 }])
    expect(countsAt(cum, 2, null)).toEqual([{ name: 'Druid', count: 4 }, { name: 'Sorcerer', count: 3 }])
  })

  it('only counts the trailing window', () => {
    expect(countsAt(cum, 2, 1)).toEqual([{ name: 'Druid', count: 4 }, { name: 'Sorcerer', count: 1 }])
    expect(countsAt(cum, 1, 1)).toEqual([])
  })
})

describe('AvatarMetaChart', () => {
  beforeEach(() => {
    get.mockResolvedValue({ dates: DATES, avatars: AVATARS, daily_totals: {} })
  })

  it('shows the latest day and moves with the slider', async () => {
    render(<AvatarMetaChart />)
    await waitFor(() => expect(screen.getAllByTestId('meta-row')).toHaveLength(2))
    expect(screen.getAllByTestId('meta-row')[0]).toHaveTextContent('Druid')

    fireEvent.click(screen.getByText('All time'))
    fireEvent.change(screen.getByLabelText('Date'), { target: { value: '0' } })
    const rows = screen.getAllByTestId('meta-row')
    expect(rows).toHaveLength(1)
    expect(rows[0]).toHaveTextContent('Sorcerer')
    expect(rows[0]).toHaveTextContent('100.0%')
  })

  it('says so when there is no data', async () => {
    get.mockResolvedValue({ dates: [], avatars: {}, daily_totals: {} })
    render(<AvatarMetaChart />)
    expect(await screen.findByText('No avatar data yet.')).toBeInTheDocument()
  })
})
