import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import Standings from '../Standings'
import { getStandingsHub } from '@/api/standings'

vi.mock('@/api/standings', () => ({ getStandingsHub: vi.fn() }))

const mockUser = { value: null }
vi.mock('@/context/AuthContext', async () => {
  const actual = await vi.importActual('@/context/AuthContext')
  return { ...actual, useAuth: () => ({ user: mockUser.value }) }
})

const SEASON = {
  key: 'season', title: 'Season 9', group: 'Ladders', status: 'live', blurb: 'Ranked online games.',
  link: '/elo', links: [{ to: '/brackets', label: 'Season Top Cut' }], facts: [{ label: 'Players', value: 40 }],
  top: [{ rank: 1, name: 'Ace', value: 1800, unit: 'ELO' }],
}
const PRECON = {
  key: 'precon', title: 'Precon Ladder: Lavamancer vs Frostmage', group: 'Ladders', status: 'coming_soon',
  blurb: '4 weeks', link: null, links: [], facts: [], top: [],
}
const BRACKETS = {
  key: 'brackets', title: 'Brackets', group: 'Brackets', status: 'live', blurb: 'All brackets', link: '/brackets',
  links: [], facts: [], top: [],
  live: [{ slug: 'cup', name: 'Friday Cup', format: 'constructed', community: true, entrants: 8, open_matches: 2 }],
  recent: [],
}

describe('Event Standings hub', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUser.value = null
  })

  it('lists every system and asks logged-out visitors to log in', async () => {
    getStandingsHub.mockResolvedValue({ systems: [SEASON, PRECON, BRACKETS], logged_in: false })
    renderWithRouter(<Standings />)
    expect(await screen.findByText('Season 9')).toBeInTheDocument()
    expect(screen.getByText('Precon Ladder: Lavamancer vs Frostmage')).toBeInTheDocument()
    expect(screen.getByText('Coming soon')).toBeInTheDocument()
    expect(screen.getByText('Friday Cup')).toBeInTheDocument()
    expect(screen.getByText(/to see where you stand/)).toBeInTheDocument()
  })

  it('shows a logged-in player where they stand and what is waiting on them', async () => {
    mockUser.value = { id: 'u1' }
    getStandingsHub.mockResolvedValue({
      logged_in: true,
      systems: [
        { ...SEASON, you: { state: 'in', headline: 'In the top cut · #3 of 32', detail: '#3 on the ladder' } },
        {
          ...BRACKETS,
          you: {
            state: 'in', headline: 'Still in 1 bracket', brackets: [{ slug: 'cup', name: 'Friday Cup', seed: 2, label: 'Still in' }],
            todo: [{ slug: 'cup', bracket_name: 'Friday Cup', round_title: 'Semifinal', opponent: 'Bo', needs: 'report' }],
          },
        },
      ],
    })
    renderWithRouter(<Standings />)
    expect((await screen.findAllByText('In the top cut · #3 of 32')).length).toBeGreaterThan(0)
    expect(screen.getByText('Waiting on you')).toBeInTheDocument()
    expect(screen.getByText(/vs Bo/)).toBeInTheDocument()
  })
})
