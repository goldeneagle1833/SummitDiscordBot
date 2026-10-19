import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@/test/test-utils'
import userEvent from '@testing-library/user-event'
import CardmarketButton, { cardmarketDeckList, CARDMARKET_WANTS_URL } from '../CardmarketButton'

vi.mock('@/utils/region', () => ({ isEuropeanVisitor: vi.fn() }))
import { isEuropeanVisitor } from '@/utils/region'

const cards = [
  { qty: 1, name: 'Sorcerer' },
  { qty: 4, name: 'Lightning Bolt' },
  { qty: 0, name: 'Ignored' },
]

beforeEach(() => {
  vi.clearAllMocks()
})

describe('cardmarketDeckList', () => {
  it('writes one "qty name" line per card', () => {
    expect(cardmarketDeckList(cards)).toBe('1 Sorcerer\n4 Lightning Bolt')
  })
})

describe('CardmarketButton', () => {
  it('stays hidden outside Europe', async () => {
    isEuropeanVisitor.mockResolvedValue(false)
    render(<CardmarketButton cards={cards} />)
    await waitFor(() => expect(isEuropeanVisitor).toHaveBeenCalled())
    expect(screen.queryByRole('button', { name: /Cardmarket/i })).not.toBeInTheDocument()
  })

  it('copies the deck and opens the Cardmarket wants page in Europe', async () => {
    isEuropeanVisitor.mockResolvedValue(true)
    const open = vi.spyOn(window, 'open').mockReturnValue(null)
    const user = userEvent.setup()
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
    render(<CardmarketButton cards={cards} />)
    await user.click(await screen.findByRole('button', { name: /Buy on Cardmarket/i }))
    expect(open).toHaveBeenCalledWith(CARDMARKET_WANTS_URL, '_blank', 'noopener,noreferrer')
    expect(writeText).toHaveBeenCalledWith('1 Sorcerer\n4 Lightning Bolt')
    expect(await screen.findByText(/Deck list copied/i)).toBeInTheDocument()
  })
})
