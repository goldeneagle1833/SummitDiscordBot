import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, renderWithRouter, waitFor } from '@/test/test-utils'

vi.mock('@/api/explorer', () => ({
  fetchSeasons: vi.fn(),
  fetchLeaderboard: vi.fn(),
  deleteEvent: vi.fn(),
  deleteSeason: vi.fn(),
}))

vi.mock('@/context/AuthContext', () => ({ useAuth: vi.fn() }))

import { fetchSeasons, fetchLeaderboard } from '@/api/explorer'
import { useAuth } from '@/context/AuthContext'
import ExplorerStandings from '../ExplorerStandings'

const season = {
  id: 1,
  name: 'Explorer Series 2026',
  description: 'A player-run annual circuit. https://exploresorcery.com/',
}

const APPLY_LABEL = /Apply to Host Your Own Explorer Event/

describe('ExplorerStandings apply call-to-action', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchSeasons.mockResolvedValue([season])
    fetchLeaderboard.mockResolvedValue({ standings: [], events: [], points_config: null })
  })

  it('hides the apply button from signed-out visitors', async () => {
    useAuth.mockReturnValue({ user: false, loading: false })
    renderWithRouter(<ExplorerStandings />)

    await screen.findByText('Community Series')
    expect(screen.queryByRole('link', { name: APPLY_LABEL })).toBeNull()
  })

  it('hides the apply button from ordinary logged-in players', async () => {
    useAuth.mockReturnValue({ user: { id: '1', is_admin: false }, loading: false })
    renderWithRouter(<ExplorerStandings />)

    await screen.findByText('Community Series')
    expect(screen.queryByRole('link', { name: APPLY_LABEL })).toBeNull()
  })

  it('shows the apply button to Explorer admins', async () => {
    useAuth.mockReturnValue({
      user: { id: '2', is_explorer_admin: true, is_admin: false },
      loading: false,
    })
    renderWithRouter(<ExplorerStandings />)

    const link = await screen.findByRole('link', { name: APPLY_LABEL })
    expect(link).toHaveAttribute('href', '/explorer/apply')
  })

  it('shows the apply button to global admins', async () => {
    useAuth.mockReturnValue({ user: { id: '3', is_admin: true }, loading: false })
    renderWithRouter(<ExplorerStandings />)

    await waitFor(() =>
      expect(screen.getByRole('link', { name: APPLY_LABEL })).toBeInTheDocument()
    )
  })
})
