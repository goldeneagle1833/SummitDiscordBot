import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import DeckSnapshot from '../DeckSnapshot'

vi.mock('@/api/client', () => ({
  get: vi.fn(),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useParams: () => ({ matchId: '1000013521', playerId: '296846802924208130' }) }
})

import { get } from '@/api/client'

function snapshot(deck) {
  return {
    match_id: 1000013521,
    player_name: 'Alice',
    opponent_name: 'Bob',
    result: 'Win',
    date: '2026-09-01 12:00:00',
    deck,
  }
}

const CARDS = {
  avatar: [{ name: 'Imposter' }],
  spellbook: [{ name: 'Vile Imp', quantity: 3, type: 'Minion' }],
  atlas: [{ name: 'Oasis', quantity: 3, type: 'Site' }],
  sideboard: [],
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('DeckSnapshot', () => {
  it('offers Try this Deck when the snapshot kept its Curiosa deck id', async () => {
    get.mockResolvedValue(snapshot({ ...CARDS, id: 'cmnncgiyj00pa04jvcvmdwtkc', name: 'Steamed Imposter' }))

    renderWithRouter(<DeckSnapshot />)

    expect(await screen.findByRole('button', { name: /Try this Deck/i })).toBeInTheDocument()
  })

  it('hides the button for decks with no usable deck id', async () => {
    // Sorcery Online / DraftSorcery snapshots carry no id — there is no URL to
    // hand Sorcery Online, so the button must not appear.
    get.mockResolvedValue(snapshot({ ...CARDS, name: 'Drafted Deck' }))

    renderWithRouter(<DeckSnapshot />)

    await waitFor(() => expect(screen.getByText('Drafted Deck')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /Try this Deck/i })).not.toBeInTheDocument()
  })
})
