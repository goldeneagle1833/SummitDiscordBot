import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@/test/test-utils'
import userEvent from '@testing-library/user-event'
import TryDeckButton from '../TryDeckButton'

vi.mock('@/api/decks', () => ({
  createPsoTable: vi.fn(),
}))

import { createPsoTable } from '@/api/decks'

const GAME_URL = 'https://playsorceryonline.com/?m=seat-token'

function mockTab() {
  return { closed: false, location: { replace: vi.fn() }, close: vi.fn() }
}

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('TryDeckButton', () => {
  it('renders the Try this Deck label', () => {
    render(<TryDeckButton deckId="deck123" />)
    expect(screen.getByRole('button', { name: /Try this Deck/i })).toBeInTheDocument()
  })

  it('opens a new tab and sends it to the provisioned table', async () => {
    const tab = mockTab()
    vi.spyOn(window, 'open').mockReturnValue(tab)
    createPsoTable.mockResolvedValue({ game_url: GAME_URL })

    render(<TryDeckButton deckId="deck123" />)
    await userEvent.click(screen.getByRole('button', { name: /Try this Deck/i }))

    expect(window.open).toHaveBeenCalledWith('', '_blank')
    await waitFor(() => expect(tab.location.replace).toHaveBeenCalledWith(GAME_URL))
    expect(createPsoTable).toHaveBeenCalledWith('deck123')
  })

  it('falls back to a link when the popup was blocked', async () => {
    vi.spyOn(window, 'open').mockReturnValue(null)
    createPsoTable.mockResolvedValue({ game_url: GAME_URL })

    render(<TryDeckButton deckId="deck123" />)
    await userEvent.click(screen.getByRole('button', { name: /Try this Deck/i }))

    const link = await screen.findByRole('link', { name: /Open your table/i })
    expect(link).toHaveAttribute('href', GAME_URL)
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('closes the tab and shows the error when provisioning fails', async () => {
    const tab = mockTab()
    vi.spyOn(window, 'open').mockReturnValue(tab)
    createPsoTable.mockRejectedValue(new Error('Sorcery Online is not connected right now.'))

    render(<TryDeckButton deckId="deck123" />)
    await userEvent.click(screen.getByRole('button', { name: /Try this Deck/i }))

    expect(await screen.findByText(/not connected right now/i)).toBeInTheDocument()
    expect(tab.close).toHaveBeenCalled()
    expect(tab.location.replace).not.toHaveBeenCalled()
  })

  it('does not fire a second request while one is in flight', async () => {
    vi.spyOn(window, 'open').mockReturnValue(mockTab())
    createPsoTable.mockReturnValue(new Promise(() => {}))

    render(<TryDeckButton deckId="deck123" />)
    const button = screen.getByRole('button', { name: /Try this Deck/i })
    await userEvent.click(button)

    expect(await screen.findByRole('button', { name: /Opening table/i })).toBeDisabled()
    expect(createPsoTable).toHaveBeenCalledTimes(1)
  })
})
