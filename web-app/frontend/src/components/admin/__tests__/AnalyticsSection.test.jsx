import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, within, render } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import {
  DailyActiveUsersChart, ActiveUsersTiles, PageViewsPanel, dailyActiveRange,
  BarValueLabel, MIN_LABEL_BAR_WIDTH,
} from '../AnalyticsSection'

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
    LabelList: () => null,
  }
})

import { get } from '@/api/client'

const ACTIVE_USERS = {
  daily: [
    { date: '2026-10-08', visitors: 42, users: 17 },
    { date: '2026-10-07', visitors: 30, users: 12 },
  ],
  today: { visitors: 42, users: 17 },
  avg_7d: { visitors: 33.4, users: 11.9 },
  avg_30d: { visitors: 28, users: 9.5 },
}

describe('DailyActiveUsersChart', () => {
  it('charts visitors only for every day in the range', () => {
    render(<DailyActiveUsersChart daily={ACTIVE_USERS.daily} days={30} />)
    const chart = screen.getByTestId('bar-chart')
    expect(chart).toHaveAttribute('data-points', '30')
    const series = within(chart).getAllByTestId('series').map((el) => el.textContent)
    expect(series).toEqual(['Visitors'])
  })

  it('follows the range it is given', () => {
    const { rerender } = render(<DailyActiveUsersChart daily={ACTIVE_USERS.daily} days={7} />)
    expect(screen.getByTestId('bar-chart')).toHaveAttribute('data-points', '7')
    rerender(<DailyActiveUsersChart daily={ACTIVE_USERS.daily} days={90} />)
    expect(screen.getByTestId('bar-chart')).toHaveAttribute('data-points', '90')
  })

  it('never wraps the chart in a horizontal scroller', () => {
    const { container } = render(<DailyActiveUsersChart daily={ACTIVE_USERS.daily} days={null} />)
    expect(container.querySelector('.overflow-x-auto')).toBeNull()
    expect(container.querySelector('[style*="min-width"]')).toBeNull()
  })

  it('says so when there is no traffic yet', () => {
    render(<DailyActiveUsersChart daily={[]} days={30} />)
    expect(screen.getByText('No data yet.')).toBeInTheDocument()
  })
})

describe('BarValueLabel', () => {
  const renderLabel = (width) => render(
    <svg><BarValueLabel x={10} y={50} width={width} value={1568} /></svg>,
  )

  it('labels bars wide enough to hold the number', () => {
    renderLabel(MIN_LABEL_BAR_WIDTH)
    expect(screen.getByText('1568')).toBeInTheDocument()
  })

  it('drops the label on skinny bars', () => {
    renderLabel(MIN_LABEL_BAR_WIDTH - 1)
    expect(screen.queryByText('1568')).toBeNull()
  })
})

describe('ActiveUsersTiles', () => {
  it('shows today and rolling averages with the logged-in split', () => {
    render(<ActiveUsersTiles activeUsers={ACTIVE_USERS} />)
    const today = screen.getByTestId('dau-today')
    expect(today).toHaveTextContent('42')
    expect(today).toHaveTextContent('17 logged in')
    expect(screen.getByTestId('dau-7d')).toHaveTextContent('33.4')
    expect(screen.getByTestId('dau-7d')).toHaveTextContent('11.9 logged in')
    expect(screen.getByTestId('dau-30d')).toHaveTextContent('28')
  })

  it('renders nothing without data (older server)', () => {
    const { container } = render(<ActiveUsersTiles activeUsers={undefined} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('PageViewsPanel', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockResolvedValue({
      success: true,
      page_views: { total: 1234, top_pages: [{ path: '/cards', count: 9 }], daily: [] },
      banner_clicks: { total: 5, by_type: [] },
    })
  })

  it('requests the range in hours and shows the totals', async () => {
    renderWithRouter(<PageViewsPanel days={7} />)
    expect(await screen.findByText('1,234')).toBeInTheDocument()
    expect(get).toHaveBeenCalledWith('/api/analytics/stats?hours=168')
    expect(screen.getByText('/cards')).toBeInTheDocument()
  })

  it('requests all time without an hours filter', async () => {
    renderWithRouter(<PageViewsPanel days={null} />)
    await screen.findByText('1,234')
    expect(get).toHaveBeenCalledWith('/api/analytics/stats')
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
