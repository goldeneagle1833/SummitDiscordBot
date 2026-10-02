import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, renderWithRouter, within, userEvent } from '@/test/test-utils'

vi.mock('@/api/leaderboard', () => ({
  getCombinedLeaderboard: vi.fn(),
  getLeaderboard: vi.fn(),
  getLimitedLeaderboard: vi.fn(),
  getEvents: vi.fn(),
  getArchivedLeaderboard: vi.fn(),
  browseSeasons: vi.fn(),
}))

vi.mock('@/api/brackets', () => ({
  getBracketMarks: vi.fn(() => Promise.resolve({ marks: {} })),
}))

import {
  getCombinedLeaderboard,
  getLimitedLeaderboard,
  getEvents,
  getArchivedLeaderboard,
  browseSeasons,
} from '@/api/leaderboard'
import Leaderboard from '../Leaderboard'

const SEASON_7 = {
  event_id: 7,
  event_name: 'Season 7',
  start_date: '2026-08-30',
  end_date: '2026-09-28',
  is_active: false,
}

const ARCHIVED = {
  event_info: { ...SEASON_7, value_label: 'Event ELO' },
  total_matches: 3,
  leaderboard: [
    { user_id: 1, display_name: 'duckworthy_', event_elo: 1773, rank: 1, wins: 2, losses: 0 },
    { user_id: 3, display_name: 'Seamoose', event_elo: 1492, rank: 2, wins: 0, losses: 2 },
  ],
}

async function renderWithEvents() {
  renderWithRouter(<Leaderboard />)
  // The picker fills once the events request resolves
  await screen.findByRole('option', { name: /Season 7/ })
  return screen.getByLabelText('Select Event:')
}

async function pickSeason7() {
  const select = await renderWithEvents()
  await userEvent.selectOptions(select, '7')
  return select
}

describe('Leaderboard past events', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getCombinedLeaderboard.mockResolvedValue({ lifetime: [], elos: [], event: null })
    getLimitedLeaderboard.mockRejectedValue(new Error('no limited season'))
    getEvents.mockResolvedValue({
      events: [
        { event_id: 8, event_name: 'Season 8', start_date: '2026-09-29', end_date: null, is_active: true },
        SEASON_7,
      ],
      active_event: null,
    })
    getArchivedLeaderboard.mockResolvedValue(ARCHIVED)
    browseSeasons.mockResolvedValue({ seasons: [] })
  })

  it('offers only ended events', async () => {
    const select = await renderWithEvents()
    const options = within(select).getAllByRole('option').map((o) => o.textContent)
    expect(options.some((t) => t.startsWith('Season 7'))).toBe(true)
    expect(options.some((t) => t.startsWith('Season 8'))).toBe(false)
  })

  it('shows the summary, record and event ELO of the chosen event', async () => {
    await pickSeason7()

    expect(getArchivedLeaderboard).toHaveBeenCalledWith('7')
    expect(await screen.findByText('2 players · 3 matches')).toBeInTheDocument()
    expect(screen.getByText('W/L')).toBeInTheDocument()
    expect(screen.getByText('Event ELO')).toBeInTheDocument()

    const seamoose = screen.getByRole('link', { name: 'Seamoose' }).closest('tr')
    expect(seamoose).toHaveTextContent('0-2')
    expect(seamoose).toHaveTextContent('1492')
    expect(screen.getByRole('link', { name: 'duckworthy_' })).toHaveAttribute('href', '/player/1')
  })

  it('labels the value column the way the event rates players', async () => {
    getArchivedLeaderboard.mockResolvedValue({
      ...ARCHIVED,
      event_info: { ...SEASON_7, value_label: 'Wins' },
    })
    await pickSeason7()

    expect(await screen.findByText('Wins')).toBeInTheDocument()
    expect(screen.queryByText('Event ELO')).not.toBeInTheDocument()
  })

  it('says so when an event has no archived standings', async () => {
    getArchivedLeaderboard.mockResolvedValue({ event_info: SEASON_7, total_matches: 0, leaderboard: [] })
    await pickSeason7()

    expect(await screen.findByText(/no standings were archived/i)).toBeInTheDocument()
  })

  it('reports a failed load instead of going blank', async () => {
    getArchivedLeaderboard.mockRejectedValue(new Error('boom'))
    await pickSeason7()

    expect(await screen.findByText(/couldn't load standings/i)).toBeInTheDocument()
  })
})
