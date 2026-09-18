import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithRouter } from '@/test/test-utils'
import Bracket from '../Bracket'
import { getBracket, reportBracketMatch, confirmBracketMatch } from '@/api/brackets'

vi.mock('@/api/brackets', () => ({
  getBracket: vi.fn(),
  reportBracketMatch: vi.fn(),
  confirmBracketMatch: vi.fn(),
  adminSetMatchResult: vi.fn(),
  adminResetMatch: vi.fn(),
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
    expect(await screen.findByText('Winner')).toBeInTheDocument()
    expect(screen.getByText(/\(seed 1\)/)).toBeInTheDocument()
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
