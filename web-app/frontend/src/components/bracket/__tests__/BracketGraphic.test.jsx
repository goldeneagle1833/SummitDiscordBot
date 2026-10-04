import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithRouter } from '@/test/test-utils'
import BracketGraphic, { pickActiveBracket } from '../BracketGraphic'
import { adminGetBracket, adminPreviewBracket } from '@/api/brackets'

vi.mock('@/api/brackets', () => ({
  adminGetBracket: vi.fn(),
  adminPreviewBracket: vi.fn(),
}))

const BRACKETS = [
  { slug: 'old-cup', name: 'Old Cup', status: 'complete' },
  { slug: 'season-7', name: 'Season 7 Top Cut', status: 'published' },
  { slug: 'next', name: 'Next Cup', status: 'draft' },
]

const ROUNDS = [
  {
    round: 1,
    title: 'Semifinals',
    matches: [
      { match_no: 1, position: 1, state: 'pending', playable: true, p1_name: 'One', p2_name: 'Four' },
      { match_no: 2, position: 2, state: 'pending', playable: true, p1_name: 'Two', p2_name: 'Three' },
    ],
  },
  { round: 2, title: 'Final', matches: [{ match_no: 3, position: 1, state: 'pending' }] },
]

describe('pickActiveBracket', () => {
  it('prefers the bracket being played', () => {
    expect(pickActiveBracket(BRACKETS).slug).toBe('season-7')
  })

  it('falls back to the last finished one', () => {
    expect(pickActiveBracket([BRACKETS[2], BRACKETS[0]]).slug).toBe('old-cup')
  })

  it('handles no brackets', () => {
    expect(pickActiveBracket([])).toBeNull()
  })
})

describe('BracketGraphic', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // jsdom has no 2D canvas; the drawing itself is covered in bracketCanvas.test.js.
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
    adminGetBracket.mockImplementation((slug) =>
      Promise.resolve({
        bracket: { slug, name: slug === 'next' ? 'Next Cup' : 'Season 7 Top Cut', status: slug === 'next' ? 'draft' : 'published' },
        entrants: [],
        rounds: slug === 'next' ? [] : ROUNDS,
        decks_missing: 0,
      }),
    )
    adminPreviewBracket.mockResolvedValue({ rounds: ROUNDS })
  })

  it('opens on the active top cut', async () => {
    renderWithRouter(<BracketGraphic brackets={BRACKETS} selectedSlug={null} onSelect={() => {}} />)
    await waitFor(() => expect(adminGetBracket).toHaveBeenCalledWith('season-7'))
    expect(screen.getByLabelText('Bracket')).toHaveValue('season-7')
    expect(await screen.findByLabelText(/Bracket graphic for Season 7 Top Cut/)).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Final on' })).toBeInTheDocument()
  })

  it('switches to the bracket the admin picks', async () => {
    const onSelect = vi.fn()
    renderWithRouter(<BracketGraphic brackets={BRACKETS} selectedSlug={null} onSelect={onSelect} />)
    await userEvent.selectOptions(screen.getByLabelText('Bracket'), 'old-cup')
    expect(onSelect).toHaveBeenCalledWith('old-cup')
  })

  it('draws a draft from its preview seeding', async () => {
    renderWithRouter(<BracketGraphic brackets={BRACKETS} selectedSlug="next" onSelect={() => {}} />)
    await waitFor(() => expect(adminPreviewBracket).toHaveBeenCalledWith('next'))
    expect(await screen.findByLabelText(/Bracket graphic for Next Cup/)).toBeInTheDocument()
  })

  it('warns when the draw is still hidden from players', async () => {
    adminGetBracket.mockResolvedValue({
      bracket: { slug: 'season-7', name: 'Season 7 Top Cut', status: 'published' },
      entrants: [],
      rounds: ROUNDS,
      decks_missing: 2,
    })
    renderWithRouter(<BracketGraphic brackets={BRACKETS} selectedSlug={null} onSelect={() => {}} />)
    expect(await screen.findByText(/Posting this graphic reveals the draw/)).toBeInTheDocument()
  })
})
