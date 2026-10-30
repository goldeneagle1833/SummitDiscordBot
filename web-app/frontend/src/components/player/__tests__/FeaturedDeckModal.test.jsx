import { describe, it, expect, vi } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import FeaturedDeckModal from '../FeaturedDeckModal'
import { setFeaturedDeck, setFeaturedDeckAuto, clearFeaturedDeck } from '@/api/players'

vi.mock('@/api/players', () => ({
  setFeaturedDeck: vi.fn(() => Promise.resolve({})),
  setFeaturedDeckAuto: vi.fn(() => Promise.resolve({})),
  clearFeaturedDeck: vi.fn(() => Promise.resolve({})),
}))

describe('FeaturedDeckModal', () => {
  it('saves a pasted link', async () => {
    const onClose = vi.fn()
    renderWithRouter(<FeaturedDeckModal playerId="100" current={{ mode: 'auto' }} onClose={onClose} />)
    fireEvent.click(screen.getByLabelText(/A deck I choose/))
    fireEvent.change(screen.getByLabelText('Deck link'), { target: { value: 'https://sorcerytcg.com/decks/abc' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(setFeaturedDeck).toHaveBeenCalledWith('100', 'https://sorcerytcg.com/decks/abc', true)
  })

  it('goes back to the automatic pick', async () => {
    const onClose = vi.fn()
    renderWithRouter(<FeaturedDeckModal playerId="100" current={{ mode: 'manual', deck: { url: 'x' } }} onClose={onClose} />)
    fireEvent.click(screen.getByLabelText(/most-played public deck/))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(setFeaturedDeckAuto).toHaveBeenCalledWith('100'))
  })

  it('turns it off', async () => {
    const onClose = vi.fn()
    renderWithRouter(<FeaturedDeckModal playerId="100" current={{ mode: 'auto' }} onClose={onClose} />)
    fireEvent.click(screen.getByLabelText(/No featured deck/))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(clearFeaturedDeck).toHaveBeenCalledWith('100'))
  })
})
