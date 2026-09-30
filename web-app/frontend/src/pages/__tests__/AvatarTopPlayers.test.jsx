import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, renderWithRouter, waitFor } from '@/test/test-utils'
import AvatarTopPlayers from '../AvatarTopPlayers'
import { getAvatarFilters, getAvatarTopPlayers } from '@/api/cards'

vi.mock('@/api/cards', () => ({
  getAvatarFilters: vi.fn(),
  getAvatarTopPlayers: vi.fn(),
}))

const SEASONS = [
  { event_id: 1, event_name: 'Alpha Season', is_active: false },
  { event_id: 3, event_name: 'Summit Gothic Season 4', is_active: true },
]

describe('AvatarTopPlayers season filter', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getAvatarTopPlayers.mockResolvedValue({ avatars: [] })
  })

  it('opens on the running season, listed first', async () => {
    getAvatarFilters.mockResolvedValue({ events: SEASONS })
    renderWithRouter(<AvatarTopPlayers />)

    const season = await screen.findByRole('option', { name: 'Summit Gothic Season 4 (current)' })
    expect(season.selected).toBe(true)
    expect(getAvatarFilters).toHaveBeenCalledWith({ include_active: 1 })
    expect(getAvatarTopPlayers).toHaveBeenCalledWith(expect.objectContaining({ event: 'current' }))
    const options = screen.getAllByRole('option').map((o) => o.textContent)
    expect(options.indexOf('Summit Gothic Season 4 (current)')).toBeLessThan(options.indexOf('Alpha Season'))
  })

  it('falls back to all seasons between seasons', async () => {
    getAvatarFilters.mockResolvedValue({ events: [SEASONS[0]] })
    renderWithRouter(<AvatarTopPlayers />)

    await waitFor(() =>
      expect(getAvatarTopPlayers).toHaveBeenLastCalledWith(expect.objectContaining({ event: 'all' })),
    )
    expect(screen.getByRole('option', { name: 'All Seasons' }).selected).toBe(true)
  })
})
