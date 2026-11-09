import { describe, it, expect, vi } from 'vitest'
import { screen, waitFor, fireEvent } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import DataExportsSection, { formatBytes } from '../DataExportsSection'
import { get } from '@/api/client'

vi.mock('@/api/client', () => ({ get: vi.fn() }))

const now = new Date().toISOString()
const body = {
  days: 30,
  summary: { downloads: 2, players: 1, bytes: 2 * 1536, failed: 1, all_time_downloads: 5 },
  top_players: [{ user_id: '111', name: 'Golden Eagle', downloads: 2, bytes: 3072 }],
  entries: [
    { user_id: '111', name: 'Golden Eagle', timestamp: now, ok: false, bytes: null, matches: null, sections: [] },
    { user_id: '111', name: 'Golden Eagle', timestamp: now, ok: true, bytes: 1536, matches: 42, sections: ['matches', 'profile'] },
  ],
}

describe('DataExportsSection', () => {
  it('shows who downloaded and how much', async () => {
    get.mockResolvedValue(body)
    renderWithRouter(<DataExportsSection />)
    await waitFor(() => expect(screen.getByText('Downloads (30 days)')).toBeInTheDocument())
    expect(screen.getByText('3.0 KB')).toBeInTheDocument()
    expect(screen.getByText('1.5 KB')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
    expect(screen.getAllByText('Failed').length).toBeGreaterThan(1)
    expect(screen.getByText(/5 downloads all time/)).toBeInTheDocument()
  })

  it('changes the time range', async () => {
    get.mockResolvedValue(body)
    renderWithRouter(<DataExportsSection />)
    await waitFor(() => expect(get).toHaveBeenCalledWith('/api/admin/data-exports?days=30'))
    fireEvent.click(screen.getByRole('button', { name: '7 days' }))
    await waitFor(() => expect(get).toHaveBeenCalledWith('/api/admin/data-exports?days=7'))
  })

  it('formats sizes', () => {
    expect(formatBytes(null)).toBe('-')
    expect(formatBytes(500)).toBe('500 B')
    expect(formatBytes(3 * 1024 * 1024)).toBe('3.0 MB')
  })
})
