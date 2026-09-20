import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, renderWithRouter, waitFor } from '@/test/test-utils'

vi.mock('@/api/explorer', () => ({
  fetchSeasons: vi.fn(),
  fetchLeaderboard: vi.fn(),
  deleteEvent: vi.fn(),
  deleteSeason: vi.fn(),
  fetchEventsMap: vi.fn(),
}))

vi.mock('@/components/explorer/EventsMap', () => ({
  default: ({ events }) => <div data-testid="events-map">{events.length} events</div>,
}))

vi.mock('@/context/AuthContext', () => ({ useAuth: vi.fn() }))

import { fetchSeasons, fetchLeaderboard, fetchEventsMap } from '@/api/explorer'
import { useAuth } from '@/context/AuthContext'
import ExplorerStandings from '../ExplorerStandings'

const season = {
  id: 1,
  name: 'Explorer Series 2026',
  description: 'A player-run annual circuit. https://exploresorcery.com/',
}

const LEADERBOARD = {
  players: [],
  events: [],
  points_config: null,
  unique_players_1_event: 0,
  unique_players_3_events: 0,
}

const APPLY_LABEL = /Apply to Host Your Own Explorer Event/

describe('ExplorerStandings apply call-to-action', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchSeasons.mockResolvedValue([season])
    fetchLeaderboard.mockResolvedValue(LEADERBOARD)
    fetchEventsMap.mockResolvedValue({ enabled: false, events: [] })
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

describe('ExplorerStandings events map', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuth.mockReturnValue({ user: false, loading: false })
    fetchSeasons.mockResolvedValue([season])
    fetchLeaderboard.mockResolvedValue(LEADERBOARD)
  })

  it('hides the map while admins have the toggle off', async () => {
    fetchEventsMap.mockResolvedValue({ enabled: false, events: [] })
    renderWithRouter(<ExplorerStandings />)
    await screen.findByText('Community Series')
    expect(screen.queryByTestId('events-map')).toBeNull()
  })

  it('shows the map above the standings once the toggle is on', async () => {
    fetchEventsMap.mockResolvedValue({
      enabled: true,
      events: [{ id: 1, latitude: 1, longitude: 2, event_name: 'Cornerstone' }],
    })
    renderWithRouter(<ExplorerStandings />)
    expect(await screen.findByTestId('events-map')).toHaveTextContent('1 events')
    expect(screen.getByText('Where the Series has played')).toBeInTheDocument()
  })

  it('stays quiet when the map request fails', async () => {
    fetchEventsMap.mockRejectedValue(new Error('down'))
    renderWithRouter(<ExplorerStandings />)
    await screen.findByText('Community Series')
    expect(screen.queryByTestId('events-map')).toBeNull()
  })
})
