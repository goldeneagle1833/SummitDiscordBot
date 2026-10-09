import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, within, fireEvent } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import AnalyticsSection, { dailyActiveRange } from '../AnalyticsSection'

vi.mock('@/api/client', () => ({ get: vi.fn() }))

// recharts measures its container; jsdom reports 0x0 and renders nothing, so
// stand in a minimal shell that exposes the series names and data length.
vi.mock('recharts', () => {
  const Passthrough = ({ children }) => <div>{children}</div>
  return {
    ResponsiveContainer: Passthrough,
    BarChart: ({ data, children }) => (
      <div data-testid="bar-chart" data-points={data.length}>{children}</div>
    ),
    Bar: ({ name }) => <span data-testid="series">{name}</span>,
    XAxis: () => null,
    YAxis: () => null,
    Tooltip: () => null,
    CartesianGrid: () => null,
    Legend: () => null,
    LabelList: () => null,
  }
})

import { get } from '@/api/client'

const STATS = {
  success: true,
  page_views: { total: 1234, top_pages: [], daily: [] },
  banner_clicks: { total: 5, by_type: [] },
  active_users: {
    daily: [
      { date: '2026-10-08', visitors: 42, users: 17 },
      { date: '2026-10-07', visitors: 30, users: 12 },
    ],
    today: { visitors: 42, users: 17 },
    avg_7d: { visitors: 33.4, users: 11.9 },
    avg_30d: { visitors: 28, users: 9.5 },
  },
}

describe('AnalyticsSection — daily active users', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockResolvedValue(STATS)
  })

  it('shows today and rolling averages with the logged-in split', async () => {
    renderWithRouter(<AnalyticsSection />)
    const today = await screen.findByTestId('dau-today')
    expect(today).toHaveTextContent('42')
    expect(today).toHaveTextContent('17 logged in')
    expect(screen.getByTestId('dau-7d')).toHaveTextContent('33.4')
    expect(screen.getByTestId('dau-7d')).toHaveTextContent('11.9 logged in')
    expect(screen.getByTestId('dau-30d')).toHaveTextContent('28')
  })

  it('charts visitors and logged-in users per day, last 30 days by default', async () => {
    renderWithRouter(<AnalyticsSection />)
    await screen.findByText('Active Users (Daily)')
    const chart = screen.getAllByTestId('bar-chart')[0] // DAU chart renders first
    expect(chart).toHaveAttribute('data-points', '30')
    const series = within(chart).getAllByTestId('series').map((el) => el.textContent)
    expect(series).toEqual(['Visitors', 'Logged in'])
  })

  it('switches the daily chart range without refetching', async () => {
    renderWithRouter(<AnalyticsSection />)
    await screen.findByText('Active Users (Daily)')
    fireEvent.click(screen.getByRole('button', { name: 'Last 7 days' }))
    expect(screen.getAllByTestId('bar-chart')[0]).toHaveAttribute('data-points', '7')
    fireEvent.click(screen.getByRole('button', { name: 'Last 90 days' }))
    expect(screen.getAllByTestId('bar-chart')[0]).toHaveAttribute('data-points', '90')
    expect(get).toHaveBeenCalledTimes(1)
  })

  it('still renders when the API has no active_users block (older server)', async () => {
    get.mockResolvedValue({ ...STATS, active_users: undefined })
    renderWithRouter(<AnalyticsSection />)
    await screen.findByText('Page Views')
    expect(screen.queryByText('Daily Active Users')).not.toBeInTheDocument()
  })

  it('says so when there is no traffic yet', async () => {
    get.mockResolvedValue({ ...STATS, active_users: { ...STATS.active_users, daily: [] } })
    renderWithRouter(<AnalyticsSection />)
    await screen.findByText('Active Users (Daily)')
    expect(screen.getAllByText('No data yet.').length).toBeGreaterThan(0)
  })
})

describe('dailyActiveRange', () => {
  const now = new Date('2026-10-09T15:00:00Z')
  const daily = [
    { date: '2026-10-08', visitors: 42, users: 17 },
    { date: '2026-10-05', visitors: 30, users: 12 },
  ]

  it('fills every day in the window oldest first, zeroing quiet days', () => {
    const rows = dailyActiveRange(daily, 7, now)
    expect(rows.map((r) => r.date)).toEqual([
      '2026-10-03', '2026-10-04', '2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08', '2026-10-09',
    ])
    expect(rows[2]).toEqual({ date: '2026-10-05', visitors: 30, users: 12 })
    expect(rows[3]).toEqual({ date: '2026-10-06', visitors: 0, users: 0 })
  })

  it('all time starts at the first recorded day', () => {
    const rows = dailyActiveRange(daily, null, now)
    expect(rows[0].date).toBe('2026-10-05')
    expect(rows).toHaveLength(5)
  })

  it('returns nothing when there is no data', () => {
    expect(dailyActiveRange([], 30, now)).toEqual([])
  })
})
