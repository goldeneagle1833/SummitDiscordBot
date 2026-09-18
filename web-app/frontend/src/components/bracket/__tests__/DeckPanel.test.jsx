import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithRouter } from '@/test/test-utils'
import DeckPanel from '../DeckPanel'
import {
  getBracketDeck,
  submitBracketDeck,
  adminSubmitBracketDeck,
  adminDeleteBracketDeck,
} from '@/api/brackets'

vi.mock('@/api/brackets', () => ({
  getBracketDeck: vi.fn(),
  submitBracketDeck: vi.fn(),
  adminSubmitBracketDeck: vi.fn(),
  adminDeleteBracketDeck: vi.fn(),
}))

vi.mock('@/components/deck/DeckVisualizer', () => ({
  default: ({ spellbook }) => <div data-testid="deck-visualizer">{spellbook?.length} cards</div>,
}))

function roster(overrides = {}) {
  return {
    bracket: { slug: 'cup', name: 'Cup', status: 'published' },
    submitted: 2,
    missing: 1,
    players: [
      {
        seed: 1,
        user_id: 'u1',
        display_name: 'Still In',
        avatar: 'hash1',
        provider: 'discord',
        eliminated: false,
        has_deck: true,
        deck_visible: false,
        visibility: 'hidden',
        deck_url: null,
        avatar_name: null,
        can_submit: false,
      },
      {
        seed: 2,
        user_id: 'u2',
        display_name: 'Knocked Out',
        eliminated: true,
        has_deck: true,
        deck_visible: true,
        visibility: 'public',
        deck_url: 'https://curiosa.io/decks/abc',
        avatar_name: 'Necromancer',
        can_submit: false,
      },
      {
        seed: 3,
        user_id: 'u3',
        display_name: 'No Deck',
        eliminated: false,
        has_deck: false,
        deck_visible: false,
        can_submit: false,
      },
    ],
    ...overrides,
  }
}

describe('DeckPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getBracketDeck.mockResolvedValue({
      deck: { name: 'Dead Cant Swim', avatar: [{ name: 'Necromancer' }], spellbook: [{}, {}] },
    })
    submitBracketDeck.mockResolvedValue({ success: true })
    adminSubmitBracketDeck.mockResolvedValue({ success: true })
    adminDeleteBracketDeck.mockResolvedValue({ success: true })
  })

  it('summarises how many decks are in', () => {
    renderWithRouter(<DeckPanel slug="cup" roster={roster()} onChanged={vi.fn()} />)
    expect(screen.getByText(/2 of 3 submitted/)).toBeInTheDocument()
    expect(screen.getByText(/1 still to come/)).toBeInTheDocument()
  })

  it('keeps a live players deck hidden', () => {
    renderWithRouter(<DeckPanel slug="cup" roster={roster()} onChanged={vi.fn()} />)
    const row = screen.getByText('Still In').closest('li')
    expect(within(row).getByText(/Submitted · hidden/)).toBeInTheDocument()
    expect(within(row).queryByText('View deck')).not.toBeInTheDocument()
  })

  it('tells the owner that only they can see their own deck', () => {
    const mine = roster()
    mine.players[0].visibility = 'owner'
    mine.players[0].deck_visible = true
    mine.players[0].can_submit = true
    renderWithRouter(<DeckPanel slug="cup" roster={mine} onChanged={vi.fn()} />)

    const row = screen.getByText('Still In').closest('li')
    // "Revealed" here would read as if the whole server could see it.
    expect(within(row).getByText('Only you can see this')).toBeInTheDocument()
    expect(within(row).queryByText('Revealed to everyone')).not.toBeInTheDocument()
  })

  it('marks a knocked-out deck as revealed to everyone', () => {
    renderWithRouter(<DeckPanel slug="cup" roster={roster()} onChanged={vi.fn()} />)
    const row = screen.getByText('Knocked Out').closest('li')
    expect(within(row).getByText('Revealed to everyone')).toBeInTheDocument()
  })

  it('flags an admin peek as an admin view', () => {
    const asAdmin = roster()
    asAdmin.players[0].visibility = 'admin'
    asAdmin.players[0].deck_visible = true
    renderWithRouter(<DeckPanel slug="cup" roster={asAdmin} isAdmin onChanged={vi.fn()} />)

    const row = screen.getByText('Still In').closest('li')
    expect(within(row).getByText(/Hidden · admin view/)).toBeInTheDocument()
  })

  it('reveals the deck of a knocked-out player', async () => {
    renderWithRouter(<DeckPanel slug="cup" roster={roster()} onChanged={vi.fn()} />)
    const row = screen.getByText('Knocked Out').closest('li')
    expect(within(row).getByText('Revealed to everyone')).toBeInTheDocument()

    await userEvent.click(within(row).getByText('View deck'))

    await waitFor(() => expect(getBracketDeck).toHaveBeenCalledWith('cup', 2))
    expect(await screen.findByTestId('deck-visualizer')).toHaveTextContent('2 cards')
    expect(screen.getByText('Open on Curiosa')).toHaveAttribute(
      'href',
      'https://curiosa.io/decks/abc',
    )
  })

  it('marks players with nothing submitted', () => {
    renderWithRouter(<DeckPanel slug="cup" roster={roster()} onChanged={vi.fn()} />)
    const row = screen.getByText('No Deck').closest('li')
    expect(within(row).getByText('No deck yet')).toBeInTheDocument()
  })

  it('offers the submit form to the viewer who is in the bracket', async () => {
    const onChanged = vi.fn()
    const mine = roster()
    mine.players[2].can_submit = true
    renderWithRouter(<DeckPanel slug="cup" roster={mine} onChanged={onChanged} />)

    expect(screen.getByText(/Only you can see it until you are knocked out/)).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Your deck link'), 'https://curiosa.io/decks/mine')
    await userEvent.click(screen.getByRole('button', { name: /save deck/i }))

    await waitFor(() =>
      expect(submitBracketDeck).toHaveBeenCalledWith('cup', 'https://curiosa.io/decks/mine'),
    )
    expect(onChanged).toHaveBeenCalled()
  })

  it('tells the owner their deck is already saved', () => {
    const mine = roster()
    mine.players[0].can_submit = true
    renderWithRouter(<DeckPanel slug="cup" roster={mine} onChanged={vi.fn()} />)
    expect(screen.getByText(/Your deck is saved/)).toBeInTheDocument()
  })

  it('surfaces a rejected deck link', async () => {
    submitBracketDeck.mockRejectedValue(new Error('Could not read that deck'))
    const mine = roster()
    mine.players[2].can_submit = true
    renderWithRouter(<DeckPanel slug="cup" roster={mine} onChanged={vi.fn()} />)

    await userEvent.type(screen.getByLabelText('Your deck link'), 'https://example.com/nope')
    await userEvent.click(screen.getByRole('button', { name: /save deck/i }))

    expect(await screen.findByText('Could not read that deck')).toBeInTheDocument()
  })

  it('shows no submit form to a viewer who is not in the bracket', () => {
    renderWithRouter(<DeckPanel slug="cup" roster={roster()} onChanged={vi.fn()} />)
    expect(screen.queryByLabelText('Your deck link')).not.toBeInTheDocument()
  })

  it('lets an admin add a deck for a player', async () => {
    const onChanged = vi.fn()
    renderWithRouter(<DeckPanel slug="cup" roster={roster()} isAdmin onChanged={onChanged} />)

    const row = screen.getByText('No Deck').closest('li')
    await userEvent.click(within(row).getByText('Add deck'))

    await userEvent.type(
      screen.getByLabelText('Deck link for seed 3'),
      'https://curiosa.io/decks/theirs',
    )
    await userEvent.click(within(row).getByRole('button', { name: /save deck/i }))

    await waitFor(() =>
      expect(adminSubmitBracketDeck).toHaveBeenCalledWith(
        'cup',
        3,
        'https://curiosa.io/decks/theirs',
      ),
    )
  })

  it('lets an admin replace or remove a deck', async () => {
    const onChanged = vi.fn()
    renderWithRouter(<DeckPanel slug="cup" roster={roster()} isAdmin onChanged={onChanged} />)

    const row = screen.getByText('Still In').closest('li')
    expect(within(row).getByText('Replace')).toBeInTheDocument()

    await userEvent.click(within(row).getByText('Remove'))
    await waitFor(() => expect(adminDeleteBracketDeck).toHaveBeenCalledWith('cup', 1))
    expect(onChanged).toHaveBeenCalled()
  })

  it('an admin can open a deck that is still hidden from players', async () => {
    renderWithRouter(
      <DeckPanel
        slug="cup"
        roster={roster({
          players: [
            {
              seed: 1,
              user_id: 'u1',
              display_name: 'Still In',
              eliminated: false,
              has_deck: true,
              // The API marks it visible for admins.
              deck_visible: true,
              deck_url: 'https://curiosa.io/decks/abc',
              can_submit: false,
            },
          ],
        })}
        isAdmin
        onChanged={vi.fn()}
      />,
    )
    await userEvent.click(screen.getByText('View deck'))
    expect(await screen.findByTestId('deck-visualizer')).toBeInTheDocument()
  })

  it('renders nothing without a roster', () => {
    const { container } = renderWithRouter(<DeckPanel slug="cup" roster={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})
