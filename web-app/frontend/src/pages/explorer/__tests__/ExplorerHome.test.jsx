import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, renderWithRouter } from '@/test/test-utils'

vi.mock('@/api/explorer', () => ({
  fetchSeasons: vi.fn(),
  fetchLeaderboard: vi.fn(),
  fetchSeasonEvents: vi.fn(),
  fetchEventsMap: vi.fn(),
}))
vi.mock('@/components/explorer/EventsMap', () => ({
  default: ({ events }) => <div data-testid="events-map">{events.length} events</div>,
}))

import { fetchSeasons, fetchLeaderboard, fetchSeasonEvents, fetchEventsMap } from '@/api/explorer'
import ExplorerHome from '../ExplorerHome'
import ExplorerEvents from '../ExplorerEvents'

const LEADERBOARD = {
  points_config: {
    participation: 10,
    bonus_pathfinder: { 0: 5, 1: 4, 2: 3 },
    persecutor: { 1: 10, 2: 5, 3: 4, 4: 4, 5: 3, 6: 3, 7: 2, 8: 2 },
    trials_threshold: 10,
  },
  players: [
    { cardeio_user_id: 'a', rank: 1, display_name: 'Ada', grand_explorer: 42, events_played: 3 },
    { cardeio_user_id: 'b', rank: 2, display_name: 'Bo', grand_explorer: 30, events_played: 2 },
  ],
  unique_players_1_event: 25,
  unique_players_3_events: 6,
}
const EVENTS = [
  { id: 1, event_name: 'Explorer March', event_date: '2026-03-14', venue_name: 'Example Games', total_players: 20 },
  { id: 2, event_name: 'Explorer April', event_date: '2026-04-11', venue_name: 'Sample Cards', total_players: 14, source_url: 'https://example.com/e/2' },
]

beforeEach(() => {
  fetchSeasons.mockResolvedValue([{ id: 7, name: 'Explorer Series 2026' }])
  fetchLeaderboard.mockResolvedValue(LEADERBOARD)
  fetchSeasonEvents.mockResolvedValue(EVENTS)
  fetchEventsMap.mockResolvedValue({ enabled: false, events: [] })
})

describe('Explorer Series home', () => {
  it('shows the newest series, its leaders, recent events and the points guide', async () => {
    renderWithRouter(<ExplorerHome />)
    expect(await screen.findByText('Ada')).toBeInTheDocument()
    expect(fetchLeaderboard).toHaveBeenCalledWith(7)
    expect(screen.getByText('Explorer Series 2026')).toBeInTheDocument()
    expect(screen.getByText('Sample Cards')).toBeInTheDocument()
    expect(screen.getByText('3rd – 4th in any event')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Full standings →' })).toHaveAttribute('href', '/explorer-series/standings')
    expect(screen.getAllByRole('link', { name: /host an event|Apply to host/i })[0]).toHaveAttribute('href', '/explorer-series/host')
    expect(screen.queryByTestId('events-map')).toBeNull()
  })

  it('shows the map once admins switch it on', async () => {
    fetchEventsMap.mockResolvedValue({ enabled: true, events: [{ id: 1, latitude: 40, longitude: -83 }] })
    renderWithRouter(<ExplorerHome />)
    expect(await screen.findByTestId('events-map')).toHaveTextContent('1 events')
  })
})

describe('Explorer Series events page', () => {
  it('lists events month by month with result links', async () => {
    renderWithRouter(<ExplorerEvents />)
    expect(await screen.findByText('March 2026')).toBeInTheDocument()
    expect(screen.getByText('April 2026')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Results/ })).toHaveAttribute('href', 'https://example.com/e/2')
  })
})
