import { describe, it, expect, vi } from 'vitest'
import { screen, waitFor, fireEvent } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import McpUsageSection from '../McpUsageSection'
import { get } from '@/api/client'

vi.mock('@/api/client', () => ({ get: vi.fn() }))

const day = (d, pub, acc, players) => ({ day: d, calls: pub + acc, public: pub, account: acc, players, ok: pub + acc, no_result: 0, error: 0, limited: 0, signin: 0 })
const body = {
  days: 7,
  retention_days: 90,
  totals: { calls: 30, public: 20, account: 10, players: 3, visitors: 7, ok: 26, no_result: 2, error: 1, limited: 1, signin: 0, last_seen: '2026-11-28T12:00:00+00:00' },
  by_day: [day('2026-11-27', 10, 4, 2), day('2026-11-28', 10, 6, 3)],
  by_tool: [
    { tool: 'meta_report', calls: 12, public: 12, account: 0, visitors: 5, players: 0, ok: 11, no_result: 0, error: 1, limited: 0, signin: 0, avg_ms: 240, last_seen: '2026-11-28T12:00:00+00:00' },
    { tool: 'my_match_review', calls: 6, public: 0, account: 6, visitors: 0, players: 3, ok: 6, no_result: 0, error: 0, limited: 0, signin: 0, avg_ms: 1800, last_seen: '2026-11-28T11:00:00+00:00' },
  ],
}

describe('McpUsageSection', () => {
  it('shows calls, players and each tool', async () => {
    get.mockResolvedValue(body)
    renderWithRouter(<McpUsageSection />)
    await waitFor(() => expect(screen.getByText('Tool calls')).toBeInTheDocument())
    expect(screen.getByText('Signed-in players')).toBeInTheDocument()
    expect(screen.getByText('meta_report')).toBeInTheDocument()
    expect(screen.getByText('my_match_review')).toBeInTheDocument()
    expect(screen.getByText('6 signed in (3 players)')).toBeInTheDocument()
    expect(screen.getByText(/avg 1.8 s/)).toBeInTheDocument()
    expect(screen.getByText('12 public (5 visitors)')).toBeInTheDocument()
  })

  it('changes the time range', async () => {
    get.mockResolvedValue(body)
    renderWithRouter(<McpUsageSection />)
    await waitFor(() => expect(get).toHaveBeenCalledWith('/api/admin/mcp-usage?days=7'))
    fireEvent.click(screen.getByRole('button', { name: '30 days' }))
    await waitFor(() => expect(get).toHaveBeenCalledWith('/api/admin/mcp-usage?days=30'))
  })

  it('says when nothing was called', async () => {
    get.mockResolvedValue({ ...body, totals: { ...body.totals, calls: 0 }, by_tool: [] })
    renderWithRouter(<McpUsageSection />)
    await waitFor(() => expect(screen.getByText('No AI app calls in this range.')).toBeInTheDocument())
  })
})
