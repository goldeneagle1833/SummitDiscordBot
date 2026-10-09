import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import DashboardSection, { weeksInRange } from '../DashboardSection'

vi.mock('@/api/client', () => ({ get: vi.fn() }))

vi.mock('recharts', () => {
  const Passthrough = ({ children }) => <div>{children}</div>
  const Chart = ({ data, children }) => (
    <div data-testid="chart" data-points={data.length}>{children}</div>
  )
  return {
    ResponsiveContainer: Passthrough,
    BarChart: Chart,
    LineChart: Chart,
    Bar: () => null,
    Line: () => null,
    XAxis: () => null,
    YAxis: () => null,
    Tooltip: () => null,
    CartesianGrid: () => null,
    Legend: () => null,
    LabelList: () => null,
  }
})

import { get } from '@/api/client'

const DASHBOARD = {
  success: true,
  summary: { total_players: 321, total_matches: 4000, total_logins: 50 },
  games_over_time: [{ week: '2020-01', bot: 1, web: 1 }],
  players_over_time: [],
  new_players_per_week: [],
  avg_games_per_player: [],
  dominance: {},
  heatmap: [],
}

function mockApi() {
  get.mockImplementation((url) => {
    if (url.startsWith('/api/admin/dashboard-stats')) return Promise.resolve(DASHBOARD)
    if (url.startsWith('/api/admin/voice-stats')) return Promise.resolve({ success: true, queues: {}, days: [] })
    if (url.startsWith('/api/analytics/stats')) {
      return Promise.resolve({
        success: true,
        page_views: { total: 77, top_pages: [], daily: [] },
        banner_clicks: { total: 0, by_type: [] },
        active_users: {
          daily: [{ date: '2026-10-08', visitors: 4, users: 2 }],
          today: { visitors: 4, users: 2 },
          avg_7d: { visitors: 1, users: 1 },
          avg_30d: { visitors: 1, users: 1 },
        },
      })
    }
    return Promise.resolve({ success: false })
  })
}

describe('DashboardSection', () => {
  beforeEach(() => {
    localStorage.clear()
    get.mockReset()
    mockApi()
  })

  it('puts the daily users chart on top, driven by the shared range (30 days default)', async () => {
    renderWithRouter(<DashboardSection />)
    await screen.findByText('Active Users (Daily)')
    expect(screen.getAllByTestId('chart')[0]).toHaveAttribute('data-points', '30')
    fireEvent.click(screen.getByRole('button', { name: 'Last 7 days' }))
    expect(screen.getAllByTestId('chart')[0]).toHaveAttribute('data-points', '7')
  })

  it('passes the shared range to the site traffic panel', async () => {
    renderWithRouter(<DashboardSection />)
    await screen.findByText('77')
    fireEvent.click(screen.getByRole('button', { name: 'Last 90 days' }))
    await vi.waitFor(() => expect(get).toHaveBeenCalledWith('/api/analytics/stats?hours=2160'))
  })

  it('switches between tabs', async () => {
    renderWithRouter(<DashboardSection />)
    expect(screen.getByRole('tab', { name: 'Site Traffic' })).toHaveAttribute('aria-selected', 'true')
    fireEvent.click(screen.getByRole('tab', { name: 'Matches' }))
    expect(await screen.findByText('Total Matches')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Players' }))
    expect(await screen.findByText('Total Players (all time)')).toBeInTheDocument()
    expect(screen.getByText('321')).toBeInTheDocument()
  })

  it('remembers the tab and range', async () => {
    const { unmount } = renderWithRouter(<DashboardSection />)
    fireEvent.click(screen.getByRole('tab', { name: 'Players' }))
    fireEvent.click(screen.getByRole('button', { name: 'All Time' }))
    unmount()
    renderWithRouter(<DashboardSection />)
    expect(screen.getByRole('tab', { name: 'Players' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('button', { name: 'All Time' })).toHaveAttribute('aria-pressed', 'true')
  })
})

describe('weeksInRange', () => {
  const now = new Date('2026-10-09T12:00:00')
  const rows = [{ week: '2026-01' }, { week: '2026-39' }, { week: '2026-40' }]

  it('keeps only weeks overlapping the range', () => {
    expect(weeksInRange(rows, 3, now).map(r => r.week)).toEqual(['2026-40'])
    expect(weeksInRange(rows, 7, now).map(r => r.week)).toEqual(['2026-39', '2026-40'])
  })

  it('keeps everything for all time and adds axis labels', () => {
    const out = weeksInRange(rows, null, now)
    expect(out).toHaveLength(3)
    expect(out[0].label).toBeTruthy()
  })
})
