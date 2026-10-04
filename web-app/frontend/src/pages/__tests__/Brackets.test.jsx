import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import Brackets from '../Brackets'
import { listBrackets, getBracket, getBracketDecks, getMyBracketMatches } from '@/api/brackets'

vi.mock('@/api/brackets', () => ({
  listBrackets: vi.fn(),
  getBracket: vi.fn(),
  getBracketDecks: vi.fn(),
  getBracketDeck: vi.fn(),
  getMyBracketMatches: vi.fn(),
  submitBracketDeck: vi.fn(),
}))

const mockUser = { value: null }
vi.mock('@/context/AuthContext', async () => {
  const actual = await vi.importActual('@/context/AuthContext')
  return { ...actual, useAuth: () => ({ user: mockUser.value }) }
})

const LIST = [
  { slug: 'spring-cup', name: 'Spring Cup', status: 'complete', entrant_count: 8 },
  { slug: 'season-7', name: 'Season 7 Top Cut', status: 'published', entrant_count: 8 },
]

function detail(slug, name, status) {
  return {
    bracket: { slug, name, status },
    entrants: [],
    rounds: [],
    champion: null,
    decks_missing: 0,
  }
}

describe('Brackets landing page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUser.value = null
    listBrackets.mockResolvedValue({ brackets: LIST })
    getBracketDecks.mockResolvedValue({ submitted: 0, missing: 0, players: [] })
    getBracket.mockImplementation((slug) =>
      Promise.resolve(
        slug === 'season-7'
          ? detail('season-7', 'Season 7 Top Cut', 'published')
          : detail('spring-cup', 'Spring Cup', 'complete'),
      ),
    )
  })

  it('opens straight onto the bracket being played', async () => {
    renderWithRouter(<Brackets />)
    expect(await screen.findByRole('heading', { name: 'Season 7 Top Cut' })).toBeInTheDocument()
    expect(getBracket).toHaveBeenCalledWith('season-7')
    expect(screen.getByRole('link', { name: /Spring Cup/ })).toHaveAttribute(
      'href',
      '/brackets/spring-cup',
    )
  })

  it('falls back to the last finished bracket between events', async () => {
    listBrackets.mockResolvedValue({ brackets: [LIST[0]] })
    renderWithRouter(<Brackets />)
    expect(await screen.findByRole('heading', { name: 'Spring Cup' })).toBeInTheDocument()
  })

  it('says so when nothing has been published', async () => {
    listBrackets.mockResolvedValue({ brackets: [] })
    renderWithRouter(<Brackets />)
    expect(await screen.findByText(/No brackets have been published yet/)).toBeInTheDocument()
  })

  it('points a player at matches waiting in another bracket', async () => {
    mockUser.value = { user_id: 'u1' }
    getMyBracketMatches.mockResolvedValue({
      matches: [
        { slug: 'spring-cup', match_no: 3, bracket_name: 'Spring Cup', round_title: 'Final', needs: 'confirm' },
        { slug: 'season-7', match_no: 1, bracket_name: 'Season 7 Top Cut', round_title: 'Semifinals', needs: 'report' },
      ],
    })
    renderWithRouter(<Brackets />)
    expect(await screen.findByText('Spring Cup — Final')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText('Season 7 Top Cut — Semifinals')).not.toBeInTheDocument())
  })
})
