import { describe, it, expect, vi } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import FeaturedDeckModal from '../FeaturedDeckModal'
import { setFeaturedDeck, clearFeaturedDeck } from '@/api/players'

vi.mock('@/api/players', () => ({
  setFeaturedDeck: vi.fn(() => Promise.resolve({})),
  clearFeaturedDeck: vi.fn(() => Promise.resolve({})),
}))

describe('FeaturedDeckModal', () => {
  it('saves a pasted link', async () => {
    const onClose = vi.fn()
    renderWithRouter(<FeaturedDeckModal playerId="100" current={{ deck: null }} onClose={onClose} />)
    expect(screen.queryByRole('button', { name: 'Remove' })).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Deck link'), { target: { value: 'https://sorcerytcg.com/decks/abc' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(setFeaturedDeck).toHaveBeenCalledWith('100', 'https://sorcerytcg.com/decks/abc', true)
  })

  it('removes the chosen deck', async () => {
    const onClose = vi.fn()
    renderWithRouter(
      <FeaturedDeckModal playerId="100" current={{ deck: { url: 'https://sorcerytcg.com/decks/abc', auto_update: false } }} onClose={onClose} />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Remove' }))
    await waitFor(() => expect(clearFeaturedDeck).toHaveBeenCalledWith('100'))
  })

  it('fills the link from a recent deck', async () => {
    const onClose = vi.fn()
    const recent = [
      { url: 'https://sorcerytcg.com/decks/one', deck_name: 'Dancing in the mist', avatar: 'Necromancer', wins: 70, losses: 13 },
      { url: 'https://sorcerytcg.com/decks/two', deck_name: 'Rock', avatar: 'Geomancer', wins: 2, losses: 1 },
    ]
    renderWithRouter(
      <FeaturedDeckModal playerId="100" current={{ deck: null }} recentDecks={recent} onClose={onClose} />,
    )
    expect(screen.getByRole('option', { name: /Dancing in the mist · Necromancer \(70W 13L\)/ })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Pick from your recent decks'), { target: { value: 'https://sorcerytcg.com/decks/two' } })
    expect(screen.getByLabelText(/Or paste a deck link/)).toHaveValue('https://sorcerytcg.com/decks/two')
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(setFeaturedDeck).toHaveBeenCalledWith('100', 'https://sorcerytcg.com/decks/two', true))
  })
})
