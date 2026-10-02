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

const SEASON_8 = { event_id: 8, event_name: 'Season 8', start_date: '2026-09-29', end_date: null, is_active: true }

const SEASON_7 = {
  event_id: 7,
  event_name: 'Season 7',
  start_date: '2026-08-30',
  end_date: '2026-09-28',
  is_active: false,
  players: 48,
  matches: 312,
  champion: 'duckworthy_',
  champion_id: 1,
}

const GOTHIC = {
  event_id: 'season_gothic_1',
  event_name: 'Gothic Season 1',
  start_date: '2026-01-03',
  end_date: '2026-02-03',
  is_active: false,
}

const ARCHIVED = {
  event_info: { ...SEASON_7, value_label: 'Event ELO' },
  total_matches: 312,
  leaderboard: [
    { user_id: 1, display_name: 'duckworthy_', event_elo: 1773, rank: 1, wins: 21, losses: 6 },
    { user_id: 3, display_name: 'Seamoose', event_elo: 1492, rank: 2, wins: 9, losses: 11 },
  ],
}

const COMBINED = {
  lifetime: [
    { id: '1', name: 'duckworthy_', elo: 1812, wins: 120, losses: 60 },
    { id: '3', name: 'Seamoose', elo: 1540, wins: 50, losses: 48 },
  ],
  elos: [1812, 1540],
  event: {
    info: SEASON_8,
    leaderboard: [
      { id: '1', entry_id: '1', name: 'duckworthy_', event_elo: 1530, wins: 2, losses: 0, voice_games: 0 },
      { id: '3', entry_id: '3', name: 'Seamoose', event_elo: 1470, wins: 0, losses: 2, voice_games: 0 },
    ],
    voice_requirement: null,
  },
}

function sidebar() {
  return within(screen.getByRole('navigation', { name: 'Leaderboards' }))
}

async function renderPage(route = '/elo') {
  renderWithRouter(<Leaderboard />, { route })
  await screen.findByRole('navigation', { name: 'Leaderboards' })
}

describe('Leaderboard page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getCombinedLeaderboard.mockResolvedValue(COMBINED)
    getLimitedLeaderboard.mockRejectedValue(new Error('no limited season'))
    getEvents.mockResolvedValue({ events: [SEASON_8, SEASON_7, GOTHIC], active_event: SEASON_8 })
    getArchivedLeaderboard.mockResolvedValue(ARCHIVED)
    browseSeasons.mockResolvedValue({ seasons: [] })
  })

  it('opens on the live event with every board in the sidebar', async () => {
    await renderPage()

    expect(screen.getByRole('heading', { level: 2, name: 'Season 8' })).toBeInTheDocument()
    expect(screen.getByText('Started 9/29/2026 · 2 players · 2 matches')).toBeInTheDocument()
    expect(screen.getByText('W/L')).toBeInTheDocument()

    const nav = sidebar()
    expect(nav.getByRole('button', { name: /Season 8/ })).toHaveAttribute('aria-current', 'true')
    expect(nav.getByRole('button', { name: /Lifetime ELO/ })).toBeInTheDocument()
    expect(nav.queryByRole('button', { name: /Limited format/ })).not.toBeInTheDocument()
    expect(nav.getByRole('button', { name: /Season 7/ })).toHaveTextContent('48 players · 312 matches')
    expect(nav.getByRole('button', { name: /Season 7/ })).toHaveTextContent('duckworthy_')
    expect(nav.getByRole('button', { name: /Gothic Season 1/ })).toHaveTextContent('ranked by wins')
    expect(nav.getByRole('button', { name: /Season leaderboards/ })).toBeInTheDocument()
  })

  it('shows a past event with its summary, records and ELO when picked', async () => {
    await renderPage()
    await userEvent.click(sidebar().getByRole('button', { name: /Season 7/ }))

    expect(getArchivedLeaderboard).toHaveBeenCalledWith(7)
    expect(await screen.findByText('8/30/2026 - 9/28/2026 · 2 players · 312 matches')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Season 7' })).toBeInTheDocument()
    expect(screen.getByText('Event ELO')).toBeInTheDocument()

    const seamoose = screen.getByRole('link', { name: 'Seamoose' }).closest('tr')
    expect(seamoose).toHaveTextContent('9-11')
    expect(seamoose).toHaveTextContent('1492')
    expect(screen.getByRole('link', { name: 'duckworthy_' })).toHaveAttribute('href', '/player/1')
    expect(sidebar().getByRole('button', { name: /Season 7/ })).toHaveAttribute('aria-current', 'true')
  })

  it('opens the board named in the URL', async () => {
    await renderPage('/elo?board=lifetime')

    expect(screen.getByRole('heading', { level: 2, name: 'Lifetime ELO Leaderboard' })).toBeInTheDocument()
    expect(screen.getByText('ELO Distribution')).toBeInTheDocument()
    expect(screen.getByText('1812')).toBeInTheDocument()
  })

  it('falls back to the live event for an unknown board', async () => {
    await renderPage('/elo?board=event:999')

    expect(screen.getByRole('heading', { level: 2, name: 'Season 8' })).toBeInTheDocument()
  })

  it('switches boards from the phone picker', async () => {
    await renderPage()
    await userEvent.selectOptions(screen.getByLabelText('Leaderboard'), 'seasons')

    expect(await screen.findByRole('heading', { level: 2, name: 'Season Leaderboards' })).toBeInTheDocument()
    expect(browseSeasons).toHaveBeenCalled()
  })

  it('labels a wins-ranked season and keeps it in the sidebar', async () => {
    getArchivedLeaderboard.mockResolvedValue({
      event_info: { ...GOTHIC, value_label: 'Wins' },
      total_matches: 3,
      leaderboard: [{ user_id: '1', display_name: 'Ann', event_elo: 2, rank: 1, wins: 2, losses: 0 }],
    })
    await renderPage()
    await userEvent.click(sidebar().getByRole('button', { name: /Gothic Season 1/ }))

    expect(await screen.findByText('Wins')).toBeInTheDocument()
    expect(getArchivedLeaderboard).toHaveBeenCalledWith('season_gothic_1')
    expect(screen.queryByText('Event ELO')).not.toBeInTheDocument()
  })

  it('says so when an event has no archived standings', async () => {
    getArchivedLeaderboard.mockResolvedValue({ event_info: SEASON_7, total_matches: 0, leaderboard: [] })
    await renderPage()
    await userEvent.click(sidebar().getByRole('button', { name: /Season 7/ }))

    expect(await screen.findByText(/no standings were archived/i)).toBeInTheDocument()
  })

  it('reports a failed load instead of going blank', async () => {
    getArchivedLeaderboard.mockRejectedValue(new Error('boom'))
    await renderPage()
    await userEvent.click(sidebar().getByRole('button', { name: /Season 7/ }))

    expect(await screen.findByText(/couldn't load standings/i)).toBeInTheDocument()
  })

  it('explains the pause when no event is active', async () => {
    getCombinedLeaderboard.mockResolvedValue({ ...COMBINED, event: null })
    await renderPage()

    expect(screen.getByRole('heading', { level: 2, name: 'No Active Event' })).toBeInTheDocument()
    expect(sidebar().getByRole('button', { name: /No active event/ })).toHaveAttribute('aria-current', 'true')
  })

  it('offers the limited board when a limited season exists', async () => {
    getLimitedLeaderboard.mockResolvedValue({
      leaderboard: [],
      trophy_runs: [],
      stats: { unique_players: 12, total_runs: 30, total_matches: 100, trophy_runs: 4 },
    })
    await renderPage('/elo?board=limited')

    expect(screen.getByRole('heading', { level: 2, name: 'Limited Format Leaderboard' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Full limited page' })).toHaveAttribute('href', '/elo/limited')
    expect(sidebar().getByRole('button', { name: /Limited format/ })).toHaveTextContent('12 players')
  })
})
