import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import FeaturedDeck from '../FeaturedDeck'
import { getFeaturedDeck } from '@/api/players'

vi.mock('@/api/players', () => ({ getFeaturedDeck: vi.fn() }))
vi.mock('@/api/cards', () => ({ getAvatarImageFiles: vi.fn(() => Promise.resolve([])) }))

const deck = {
  url: 'https://sorcerytcg.com/decks/abc123',
  source: 'curiosa',
  name: 'Fire Druid',
  avatar: 'Druid',
  avatar_image: null,
  spellbook: [{ name: 'Raging Taurus', quantity: 2, type: 'Minion', image: 'bet-raging_taurus-b-s.webp' }],
  atlas: [],
  sideboard: [],
  auto_update: true,
}

describe('FeaturedDeck', () => {
  beforeEach(() => getFeaturedDeck.mockReset())

  it('shows the deck and a link to it', async () => {
    getFeaturedDeck.mockResolvedValue({ deck, mode: 'manual' })
    renderWithRouter(<FeaturedDeck playerId="100" isOwner={false} />)
    expect(await screen.findByText('Fire Druid')).toBeInTheDocument()
    expect(screen.getByText('Druid')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
    // The tile opens the full list, with a link to the deck site
    fireEvent.click(screen.getByRole('button', { name: /Show the cards in Fire Druid/ }))
    expect(screen.getByRole('dialog', { name: 'Fire Druid' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /View on Curiosa/ })).toHaveAttribute('href', deck.url)
  })

  it('shows nothing to visitors when no deck is set', async () => {
    getFeaturedDeck.mockResolvedValue({ deck: null })
    const { container } = renderWithRouter(<FeaturedDeck playerId="100" isOwner={false} />)
    await vi.waitFor(() => expect(getFeaturedDeck).toHaveBeenCalled())
    await Promise.resolve()
    expect(container).toBeEmptyDOMElement()
  })

  it('invites the owner to add one', async () => {
    getFeaturedDeck.mockResolvedValue({ deck: null, mode: 'auto' })
    const onEdit = vi.fn()
    renderWithRouter(<FeaturedDeck playerId="100" isOwner onEdit={onEdit} />)
    ;(await screen.findByRole('button', { name: 'Choose a deck' })).click()
    expect(onEdit).toHaveBeenCalled()
  })

  it('shows the record when the deck is among the recent decks', async () => {
    getFeaturedDeck.mockResolvedValue({ deck, mode: 'manual' })
    const recent = [{ url: deck.url, wins: 70, losses: 13, win_rate: 84.3, total_games: 83 }]
    renderWithRouter(<FeaturedDeck playerId="100" isOwner={false} recentDecks={recent} />)
    expect(await screen.findByText('84.3%')).toBeInTheDocument()
    expect(screen.getByText('70W · 13L')).toBeInTheDocument()
  })

  it('labels an automatic pick as the most played deck', async () => {
    getFeaturedDeck.mockResolvedValue({ deck: { ...deck, picked: 'auto' }, mode: 'auto' })
    renderWithRouter(<FeaturedDeck playerId="100" isOwner={false} />)
    expect(await screen.findByText(/Most played/)).toBeInTheDocument()
  })

  it('tells the owner when it is turned off', async () => {
    getFeaturedDeck.mockResolvedValue({ deck: null, mode: 'off' })
    renderWithRouter(<FeaturedDeck playerId="100" isOwner onEdit={() => {}} />)
    expect(await screen.findByRole('button', { name: 'Turn on' })).toBeInTheDocument()
  })
})
