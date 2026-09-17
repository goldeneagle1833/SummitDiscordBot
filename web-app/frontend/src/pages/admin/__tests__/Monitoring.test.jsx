import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, renderWithRouter } from '@/test/test-utils'
import { waitFor } from '@testing-library/react'

vi.mock('@/api/admin', () => ({ getMonitoring: vi.fn() }))

// recharts' ResponsiveContainer needs real layout; jsdom has none
vi.mock('recharts', async () => {
  const actual = await vi.importActual('recharts')
  return { ...actual, ResponsiveContainer: ({ children }) => <div>{children}</div> }
})

import { getMonitoring } from '@/api/admin'
import Monitoring, { formatMs, formatUptime } from '../Monitoring'

const payload = {
  hours: 24,
  health: {
    status: 'degraded',
    version: '1.2.3',
    uptime_s: 3700,
    checks: {
      'db:elo': { ok: true, detail: 'ok', ms: 1.2 },
      bot_api: { ok: false, detail: 'ConnectionError', ms: null },
    },
  },
  totals: { count: 1234, errors_4xx: 10, errors_5xx: 2, error_rate_5xx: 0.16, avg_ms: 80, max_ms: 4000, p95_ms: 250 },
  endpoints: [
    { method: 'GET', endpoint: '/api/leaderboard', count: 900, total_s: 50, errors_4xx: 0, errors_5xx: 0, avg_ms: 55, max_ms: 900, p95_ms: 100 },
    { method: 'GET', endpoint: '/api/player/<user_id>', count: 300, total_s: 90, errors_4xx: 10, errors_5xx: 2, avg_ms: 300, max_ms: 4000, p95_ms: 2500 },
  ],
  external: [{ service: 'curiosa', count: 40, errors: 1, error_rate: 2.5, avg_ms: 600, max_ms: 15000, p95_ms: 2500 }],
  traffic: [],
  resources: [],
  resources_now: {
    ts: 0, total_rss_mb: 312.4, sys_mem_percent: 61, sys_mem_available_mb: 1500,
    disk_percent: 72, disk_free_gb: 12.5, load_1m: 0.4,
    workers: [{ pid: 101, rss_mb: 156.2, cpu_percent: 1.5, threads: 4, open_fds: 20 }],
  },
  errors: [{ ts: 1700000000, request_id: 'abc123', method: 'GET', endpoint: '/api/player/<user_id>', path: '/api/player/9', status: 500, error_type: 'KeyError', message: "'elo'" }],
  databases: [{ name: 'elo', size_mb: 1.5, exists: true }],
  slow_request_ms: 1000,
}

describe('Monitoring page', () => {
  beforeEach(() => {
    getMonitoring.mockReset()
  })

  it('shows health status and failing checks', async () => {
    getMonitoring.mockResolvedValue(payload)
    renderWithRouter(<Monitoring />)
    expect(await screen.findByText('DEGRADED')).toBeInTheDocument()
    expect(screen.getByText(/bot_api \(ConnectionError\)/)).toBeInTheDocument()
    expect(screen.getByText('1,234')).toBeInTheDocument()
  })

  it('defaults endpoint table to total time, slowest first', async () => {
    getMonitoring.mockResolvedValue(payload)
    renderWithRouter(<Monitoring />)
    await screen.findByText('DEGRADED')
    const rows = screen.getAllByText(/\/api\/(leaderboard|player)/, { selector: 'td' })
    expect(rows[0].textContent).toContain('/api/player/<user_id>')
  })

  it('renders outbound services and recent errors', async () => {
    getMonitoring.mockResolvedValue(payload)
    renderWithRouter(<Monitoring />)
    await screen.findByText('curiosa')
    expect(screen.getByText('KeyError')).toBeInTheDocument()
    expect(screen.getByText('abc123')).toBeInTheDocument()
  })

  it('shows an error when the request fails', async () => {
    getMonitoring.mockRejectedValue(new Error('Admin access required'))
    renderWithRouter(<Monitoring />)
    await waitFor(() => expect(screen.getByText('Admin access required')).toBeInTheDocument())
  })
})

describe('formatters', () => {
  it('formats latency including overflow', () => {
    expect(formatMs(250)).toBe('250ms')
    expect(formatMs(2500)).toBe('2.5s')
    expect(formatMs(null, 5)).toBe('> 30s')
    expect(formatMs(null, 0)).toBe('—')
  })

  it('formats uptime', () => {
    expect(formatUptime(90)).toBe('1m')
    expect(formatUptime(3700)).toBe('1h 1m')
    expect(formatUptime(90000)).toBe('1d 1h')
  })
})
