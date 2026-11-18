import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, renderWithRouter } from '@/test/test-utils'
import { waitFor, fireEvent } from '@testing-library/react'

vi.mock('@/api/admin', () => ({
  getBotTraffic: vi.fn(),
  blockClient: vi.fn(),
  unblockClient: vi.fn(),
}))

import { getBotTraffic, blockClient, unblockClient } from '@/api/admin'
import BotTraffic, { shortAgent, suggestPattern } from '../BotTraffic'

const now = Math.floor(Date.now() / 1000)
const CHROME = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36'

const payload = {
  hours: 24,
  totals: { requests: 50000, data_requests: 20000, blocked: 2043, bot_requests: 9000, bot_clients: 3, suspects: 1 },
  thresholds: { suspect_data_per_hour: 300 },
  clients: [
    { user_agent: 'Harvester/1.0', kind: 'script', kind_label: 'Script', suspect: true, block_id: null,
      requests: 2100, data_requests: 2000, peak_data_hour: 2000, ips: 1, blocked: 0, last_seen: now },
    { user_agent: 'SorceryRec competitive archive/1.0', kind: 'bot', kind_label: 'Bot', suspect: false, block_id: 1,
      requests: 2043, data_requests: 0, peak_data_hour: 0, ips: 1, blocked: 2043, last_seen: now },
    { user_agent: CHROME, kind: 'browser', kind_label: 'Browser', suspect: false, block_id: null,
      requests: 40000, data_requests: 15000, peak_data_hour: 200, ips: 400, blocked: 0, last_seen: now },
  ],
  ips: [
    { ip: '203.0.113.2', data_requests: 2000, peak_data_hour: 2000, agents: 1, top_agent: 'Harvester/1.0',
      keyed_requests: 0, suspect: true, block_id: null, last_seen: now },
  ],
  blocks: [
    { id: 1, kind: 'agent', pattern: 'sorceryrec', reason: 'Scraped Top 8', active: 1, created_by: 'system', created_at: now },
  ],
}

describe('shortAgent', () => {
  it('names bots and browsers readably', () => {
    expect(shortAgent('Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)')).toBe('AhrefsBot/7.0')
    expect(shortAgent(CHROME)).toBe('Chrome 157 on Windows')
    expect(shortAgent('SorceryRec competitive archive/1.0')).toBe('SorceryRec competitive archive/1.0')
    expect(suggestPattern('SorceryRec competitive archive/1.0')).toBe('sorceryrec')
    expect(suggestPattern('Mozilla/5.0 (compatible; AhrefsBot/7.0)')).toBe('ahrefsbot')
  })
})

describe('BotTraffic page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getBotTraffic.mockResolvedValue(payload)
  })

  it('lists bots, hides ordinary browsers by default, and shows the block list', async () => {
    renderWithRouter(<BotTraffic />)
    await waitFor(() => expect(screen.getByText('Harvester/1.0')).toBeInTheDocument())
    expect(screen.queryByText('Chrome 157 on Windows')).not.toBeInTheDocument()
    expect(screen.getAllByText('Looks like scraping').length).toBeGreaterThan(0)
    expect(screen.getByText('sorceryrec')).toBeInTheDocument()
  })

  it('blocks a client after confirming the name', async () => {
    blockClient.mockResolvedValue({ success: true })
    vi.spyOn(window, 'prompt').mockReturnValueOnce('harvester').mockReturnValueOnce('pulls every deck')
    renderWithRouter(<BotTraffic />)
    await waitFor(() => expect(screen.getByText('Harvester/1.0')).toBeInTheDocument())
    fireEvent.click(screen.getAllByRole('button', { name: 'Block' })[0])
    await waitFor(() => expect(blockClient).toHaveBeenCalledWith('agent', 'harvester', 'pulls every deck'))
  })

  it('unblocks from the block list', async () => {
    unblockClient.mockResolvedValue({ success: true })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderWithRouter(<BotTraffic />)
    await waitFor(() => expect(screen.getByText('sorceryrec')).toBeInTheDocument())
    fireEvent.click(screen.getAllByRole('button', { name: 'Unblock' })[0])
    await waitFor(() => expect(unblockClient).toHaveBeenCalledWith(1))
  })
})
