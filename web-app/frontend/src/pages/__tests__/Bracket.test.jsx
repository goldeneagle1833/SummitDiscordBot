import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, fireEvent, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithRouter } from '@/test/test-utils'
import Bracket from '../Bracket'
import {
  getBracket,
  getBracketDecks,
  reportBracketMatch,
  confirmBracketMatch,
  adminSwapBracketPlayers,
  adminPublishBracketToTop8,
} from '@/api/brackets'

vi.mock('@/api/brackets', () => ({
  listBrackets: vi.fn(() => Promise.resolve({ brackets: [] })),
  getBracket: vi.fn(),
  getBracketDecks: vi.fn(),
  getBracketDeck: vi.fn(),
  submitBracketDeck: vi.fn(),
  adminSubmitBracketDeck: vi.fn(),
  adminDeleteBracketDeck: vi.fn(),
  reportBracketMatch: vi.fn(),
  confirmBracketMatch: vi.fn(),
  adminSetMatchResult: vi.fn(),
  adminResetMatch: vi.fn(),
  adminSwapBracketPlayers: vi.fn(),
  adminPublishBracketToTop8: vi.fn(),
}))

const mockUser = { value: { user_id: 'u1', is_admin: false } }
vi.mock('@/context/AuthContext', async () => {
  const actual = await vi.importActual('@/context/AuthContext')
  return { ...actual, useAuth: () => ({ user: mockUser.value }) }
})

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useParams: () => ({ slug: 'season-7' }) }
})

function bracketData(overrides = {}) {
  return {
    bracket: {
      slug: 'season-7',
      name: 'Season 7 Postseason',
      status: 'published',
      elo_event_name: 'Season 7',
    },
    entrants: [
      { seed: 1, display_name: 'One', user_id: 'u1' },
      { seed: 2, display_name: 'Two', user_id: 'u2' },
    ],
    rounds: [
      {
        round: 1,
        title: 'Finals',
        matches: [
          {
            match_no: 1,
            round: 1,
            round_title: 'Finals',
            state: 'pending',
            playable: true,
            p1_seed: 1,
            p1_name: 'One',
            p1_user_id: 'u1',
            p2_seed: 2,
            p2_name: 'Two',
            p2_user_id: 'u2',
            viewer_is_player: true,
            viewer_can_report: true,
            viewer_can_confirm: false,
          },
        ],
      },
    ],
    champion: null,
    ...overrides,
  }
}

describe('Bracket page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUser.value = { user_id: 'u1', is_admin: false }
    getBracket.mockResolvedValue(bracketData())
    getBracketDecks.mockResolvedValue({
      bracket: { slug: 'season-7', name: 'Season 7 Postseason', status: 'published' },
      submitted: 1,
      missing: 1,
      players: [
        {
          seed: 1,
          user_id: 'u1',
          display_name: 'One',
          eliminated: false,
          has_deck: true,
          deck_visible: false,
          can_submit: true,
        },
        {
          seed: 2,
          user_id: 'u2',
          display_name: 'Two',
          eliminated: false,
          has_deck: false,
          deck_visible: false,
          can_submit: false,
        },
      ],
    })
    reportBracketMatch.mockResolvedValue({ success: true, awaiting: 'Two' })
    confirmBracketMatch.mockResolvedValue({ success: true, state: 'complete' })
  })

  it('shows the bracket name and field size', async () => {
    renderWithRouter(<Bracket />)
    expect(await screen.findByText('Season 7 Postseason')).toBeInTheDocument()
    expect(screen.getByText(/2 players/)).toBeInTheDocument()
    expect(screen.getByText(/seeded from Season 7/)).toBeInTheDocument()
  })

  it('tells a player when a match is waiting on them', async () => {
    renderWithRouter(<Bracket />)
    expect(await screen.findByText(/1 match waiting on you/i)).toBeInTheDocument()
  })

  it('reports a result through the modal', async () => {
    renderWithRouter(<Bracket />)
    await userEvent.click(await screen.findByRole('button', { name: /report result/i }))

    expect(screen.getByText('Report your result')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /One won/ }))

    await waitFor(() => expect(reportBracketMatch).toHaveBeenCalledWith('season-7', 1, 'u1'))
    expect(await screen.findByText(/opponent has been asked to confirm/i)).toBeInTheDocument()
  })

  it('surfaces a rejected report', async () => {
    reportBracketMatch.mockRejectedValue(new Error('This match has already been reported'))
    renderWithRouter(<Bracket />)
    await userEvent.click(await screen.findByRole('button', { name: /report result/i }))
    await userEvent.click(screen.getByRole('button', { name: /Two won/ }))

    expect(await screen.findByText(/already been reported/)).toBeInTheDocument()
  })

  it('confirms an opponent’s report', async () => {
    getBracket.mockResolvedValue(
      bracketData({
        rounds: [
          {
            round: 1,
            title: 'Finals',
            matches: [
              {
                match_no: 1,
                round_title: 'Finals',
                state: 'reported',
                playable: true,
                p1_seed: 1,
                p1_name: 'One',
                p1_user_id: 'u1',
                p2_seed: 2,
                p2_name: 'Two',
                p2_user_id: 'u2',
                reported_by: 'u2',
                reported_winner_id: 'u2',
                viewer_can_confirm: true,
              },
            ],
          },
        ],
      }),
    )
    renderWithRouter(<Bracket />)
    await userEvent.click(await screen.findByRole('button', { name: 'Confirm' }))

    await waitFor(() => expect(confirmBracketMatch).toHaveBeenCalledWith('season-7', 1, true))
    expect(await screen.findByText('Result confirmed.')).toBeInTheDocument()
  })

  it('disputes a report', async () => {
    getBracket.mockResolvedValue(
      bracketData({
        rounds: [
          {
            round: 1,
            title: 'Finals',
            matches: [
              {
                match_no: 1,
                state: 'reported',
                playable: true,
                p1_seed: 1,
                p1_name: 'One',
                p1_user_id: 'u1',
                p2_seed: 2,
                p2_name: 'Two',
                p2_user_id: 'u2',
                reported_by: 'u2',
                reported_winner_id: 'u2',
                viewer_can_confirm: true,
              },
            ],
          },
        ],
      }),
    )
    renderWithRouter(<Bracket />)
    await userEvent.click(await screen.findByRole('button', { name: 'Dispute' }))

    await waitFor(() => expect(confirmBracketMatch).toHaveBeenCalledWith('season-7', 1, false))
    expect(await screen.findByText(/the match is open again/i)).toBeInTheDocument()
  })

  it('shows the winner once the bracket is finished', async () => {
    getBracket.mockResolvedValue(
      bracketData({
        bracket: { slug: 'season-7', name: 'Season 7 Postseason', status: 'complete' },
        champion: { display_name: 'One', seed: 1, user_id: 'u1' },
      }),
    )
    renderWithRouter(<Bracket />)
    expect(await screen.findByText('Champion')).toBeInTheDocument()
    expect(screen.getByText('Seed 1')).toBeInTheDocument()
  })

  it('hides the bracket from players until every decklist is in', async () => {
    getBracket.mockResolvedValue(bracketData({ decks_missing: 1 }))
    renderWithRouter(<Bracket />)

    expect(
      await screen.findByText(/revealed once every decklist is in/i),
    ).toBeInTheDocument()
    expect(screen.getByText(/1 of 2 players still needs to submit a deck/i)).toBeInTheDocument()
    expect(screen.getByText(/waiting on decklists/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /report result/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/match waiting on you/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/matches played/)).not.toBeInTheDocument()
    // The decklist panel stays so the stragglers can still submit.
    expect(screen.getByText('Decklists')).toBeInTheDocument()
  })

  it('reveals the bracket once the last decklist arrives', async () => {
    getBracket.mockResolvedValue(bracketData({ decks_missing: 0 }))
    renderWithRouter(<Bracket />)

    expect(await screen.findByRole('button', { name: /report result/i })).toBeInTheDocument()
    expect(screen.queryByText(/revealed once every decklist is in/i)).not.toBeInTheDocument()
  })

  it('still shows admins the bracket while decklists are outstanding', async () => {
    mockUser.value = { user_id: 'admin', is_admin: true }
    getBracket.mockResolvedValue(bracketData({ decks_missing: 2 }))
    renderWithRouter(<Bracket />)

    expect(await screen.findByText(/players can’t see the bracket yet/i)).toBeInTheDocument()
    expect(screen.getByText(/2 decklists are still to come/i)).toBeInTheDocument()
    expect(screen.getByText('Finals')).toBeInTheDocument()
    expect(screen.queryByText(/revealed once every decklist is in/i)).not.toBeInTheDocument()
  })

  it('does not hold back a finished bracket', async () => {
    getBracket.mockResolvedValue(
      bracketData({
        bracket: { slug: 'season-7', name: 'Season 7 Postseason', status: 'complete' },
        champion: { display_name: 'One', seed: 1, user_id: 'u1' },
        decks_missing: 1,
      }),
    )
    renderWithRouter(<Bracket />)

    expect(await screen.findByText('Champion')).toBeInTheDocument()
    expect(screen.queryByText(/revealed once every decklist is in/i)).not.toBeInTheDocument()
  })

  it('lists the decklists under the bracket', async () => {
    renderWithRouter(<Bracket />)
    expect(await screen.findByText('Decklists')).toBeInTheDocument()
    expect(screen.getByText(/1 of 2 submitted/)).toBeInTheDocument()
  })

  it('shows the champion with their profile picture', async () => {
    getBracket.mockResolvedValue(
      bracketData({
        bracket: { slug: 'season-7', name: 'Season 7 Postseason', status: 'complete' },
        entrants: [
          { seed: 1, display_name: 'One', user_id: 'u1', avatar: 'hash1', provider: 'discord' },
          { seed: 2, display_name: 'Two', user_id: 'u2' },
        ],
        champion: { display_name: 'One', seed: 1, user_id: 'u1' },
      }),
    )
    const { container } = renderWithRouter(<Bracket />)

    expect(await screen.findByText('Champion')).toBeInTheDocument()
    const avatar = [...container.querySelectorAll('img')].find((img) =>
      img.src.includes('/avatars/u1/hash1.png'),
    )
    expect(avatar).toBeTruthy()
  })

  it('lets an admin re-pair seats that have not been played', async () => {
    mockUser.value = { user_id: 'admin', is_admin: true }
    const first = bracketData().rounds[0].matches[0]
    const second = {
      ...first,
      match_no: 2,
      p1_seed: 3,
      p1_name: 'Three',
      p1_user_id: 'u3',
      p2_seed: 4,
      p2_name: 'Four',
      p2_user_id: 'u4',
    }
    getBracket.mockResolvedValue(
      bracketData({
        rounds: [
          {
            round: 1,
            title: 'Semifinals',
            matches: [
              { ...first, p1_movable: true, p2_movable: true },
              { ...second, p1_movable: true, p2_movable: true },
            ],
          },
        ],
      }),
    )
    adminSwapBracketPlayers.mockResolvedValue({ swapped: ['Two', 'Three'] })
    renderWithRouter(<Bracket />)

    // The tree comes before the deck list, so its seats are the first matches.
    const seat = (name) => screen.getAllByText(name)[0]

    // Names stay profile links until the admin asks to edit.
    await screen.findByText('Season 7 Postseason')
    expect(seat('Two').closest('a')).toHaveAttribute('href', '/player/u2')
    await userEvent.click(screen.getByRole('button', { name: 'Edit pairings' }))
    expect(seat('Two').closest('a')).toBeNull()

    const store = {}
    const dataTransfer = {
      setData: (_, value) => {
        store.value = value
      },
      getData: () => store.value,
    }
    fireEvent.dragStart(seat('Two'), { dataTransfer })
    fireEvent.drop(seat('Three'), { dataTransfer })

    await waitFor(() => expect(adminSwapBracketPlayers).toHaveBeenCalledWith('season-7', 2, 3))
    expect(await screen.findByText('Swapped Two and Three.')).toBeInTheDocument()
  })

  it('offers no pairing editor to players', async () => {
    getBracket.mockResolvedValue(bracketData())
    renderWithRouter(<Bracket />)
    await screen.findByText('Season 7 Postseason')
    expect(screen.queryByRole('button', { name: 'Edit pairings' })).toBeNull()
  })

  it('links a finished bracket to its Top 8 event', async () => {
    getBracket.mockResolvedValue(
      bracketData({
        bracket: {
          slug: 'season-7',
          name: 'Season 7 Postseason',
          status: 'complete',
          event_folder: 'Season 7 Postseason 10-2-2026',
        },
        champion: { display_name: 'One', seed: 1, user_id: 'u1' },
      }),
    )
    renderWithRouter(<Bracket />)

    const link = await screen.findByRole('link', { name: 'Decklists on the Top 8 page' })
    expect(link).toHaveAttribute('href', '/top-8/Season%207%20Postseason%2010-2-2026')
    // Only admins get to rebuild it.
    expect(screen.queryByRole('button', { name: 'Rebuild Top 8 event' })).toBeNull()
  })

  it('lets an admin add a finished bracket to the Top 8 page', async () => {
    mockUser.value = { user_id: 'admin', is_admin: true }
    getBracket.mockResolvedValue(
      bracketData({
        bracket: { slug: 'season-7', name: 'Season 7 Postseason', status: 'complete' },
        champion: { display_name: 'One', seed: 1, user_id: 'u1' },
      }),
    )
    adminPublishBracketToTop8.mockResolvedValue({ folder: 'x', top8: 2, rest: 0 })
    renderWithRouter(<Bracket />)

    await userEvent.click(await screen.findByRole('button', { name: 'Add to Top 8 page' }))
    expect(adminPublishBracketToTop8).toHaveBeenCalledWith('season-7')
    expect(await screen.findByText('Top 8 page updated with 2 decklists.')).toBeInTheDocument()
  })

  it('asks a logged-out visitor to log in', async () => {
    mockUser.value = null
    renderWithRouter(<Bracket />)
    expect(await screen.findByText('Log in')).toHaveAttribute('href', '/login')
  })

  it('handles a missing bracket', async () => {
    const error = new Error('Not found')
    error.status = 404
    getBracket.mockRejectedValue(error)
    renderWithRouter(<Bracket />)
    expect(await screen.findByText('Bracket not found.')).toBeInTheDocument()
  })
})

describe('Bracket page switcher', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUser.value = null
    getBracket.mockResolvedValue(bracketData())
    getBracketDecks.mockResolvedValue({ submitted: 2, missing: 0, players: [] })
  })

  it('shows a tab for every bracket, marking the one on screen', async () => {
    renderWithRouter(
      <Bracket
        brackets={[
          { slug: 'season-7', name: 'Season 7 Postseason', status: 'published' },
          { slug: 'season-6', name: 'Season 6 Postseason', status: 'complete' },
        ]}
      />,
    )
    const tabs = await screen.findByRole('navigation', { name: 'Brackets' })
    const current = within(tabs).getByRole('link', { name: /Season 7 Postseason/ })
    expect(current).toHaveAttribute('aria-current', 'page')
    expect(current).toHaveTextContent('Live')
    const other = within(tabs).getByRole('link', { name: /Season 6 Postseason/ })
    expect(other).toHaveAttribute('href', '/brackets/season-6')
    expect(other).toHaveTextContent('Final')
  })

  it('hides the tabs when there is only one bracket', async () => {
    renderWithRouter(
      <Bracket brackets={[{ slug: 'season-7', name: 'Season 7 Postseason', status: 'published' }]} />,
    )
    await screen.findByRole('heading', { name: 'Season 7 Postseason' })
    expect(screen.queryByRole('navigation', { name: 'Brackets' })).not.toBeInTheDocument()
  })
})

describe('Bracket page set filter', () => {
  const SETS = [
    { slug: 'season-7', name: 'Season 7 Postseason', status: 'published', set_name: 'Gothic' },
    { slug: 'season-6', name: 'Season 6 Postseason', status: 'complete', set_name: 'Gothic' },
    { slug: 'beta-open', name: 'Beta Open', status: 'complete', set_name: 'Beta' },
  ]

  beforeEach(() => {
    vi.clearAllMocks()
    mockUser.value = null
    getBracket.mockResolvedValue(bracketData())
    getBracketDecks.mockResolvedValue({ submitted: 2, missing: 0, players: [] })
  })

  it('shows only the current set until another is picked', async () => {
    renderWithRouter(<Bracket brackets={SETS} />)
    const filter = await screen.findByRole('group', { name: 'Filter by set' })
    expect(within(filter).getByRole('button', { name: /Gothic/ })).toHaveAttribute('aria-pressed', 'true')

    const tabs = screen.getByRole('navigation', { name: 'Brackets' })
    expect(within(tabs).getAllByRole('link')).toHaveLength(2)
    expect(within(tabs).queryByRole('link', { name: /Beta Open/ })).not.toBeInTheDocument()

    await userEvent.click(within(filter).getByRole('button', { name: 'All' }))
    expect(within(tabs).getAllByRole('link')).toHaveLength(3)
  })

  it('hides the set filter when no bracket has a set', async () => {
    renderWithRouter(
      <Bracket brackets={SETS.map(({ set_name: _unused, ...rest }) => rest)} />,
    )
    await screen.findByRole('navigation', { name: 'Brackets' })
    expect(screen.queryByRole('group', { name: 'Filter by set' })).not.toBeInTheDocument()
  })
})
