import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import FeaturedDeck from '../FeaturedDeck'
import { getFeaturedDeck } from '@/api/players'

vi.mock('@/api/players', () => ({ getFeaturedDeck: vi.fn() }))

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
    getFeaturedDeck.mockResolvedValue({ deck })
    renderWithRouter(<FeaturedDeck playerId="100" isOwner={false} />)
    expect(await screen.findByText('Fire Druid')).toBeInTheDocument()
    expect(screen.getByText('Druid')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /View on Curiosa/ })).toHaveAttribute('href', deck.url)
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
  })

  it('shows nothing to visitors when no deck is set', async () => {
    getFeaturedDeck.mockResolvedValue({ deck: null })
    const { container } = renderWithRouter(<FeaturedDeck playerId="100" isOwner={false} />)
    await vi.waitFor(() => expect(getFeaturedDeck).toHaveBeenCalled())
    await Promise.resolve()
    expect(container).toBeEmptyDOMElement()
  })

  it('invites the owner to add one', async () => {
    getFeaturedDeck.mockResolvedValue({ deck: null })
    const onEdit = vi.fn()
    renderWithRouter(<FeaturedDeck playerId="100" isOwner onEdit={onEdit} />)
    ;(await screen.findByRole('button', { name: 'Add featured deck' })).click()
    expect(onEdit).toHaveBeenCalled()
  })
})
