import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithRouter, screen, waitFor, userEvent } from '@/test/test-utils'
import DeckCardStats from '@/components/deck/DeckCardStats'
import { getRankedCards, getRankedCatalog, getRankedSeasons } from '@/api/rankedAnalytics'

vi.mock('@/api/rankedAnalytics', async () => {
  const actual = await vi.importActual('@/api/rankedAnalytics')
  return { ...actual, getRankedCards: vi.fn(), getRankedCatalog: vi.fn(), getRankedSeasons: vi.fn(), getRankedCardReplays: vi.fn() }
})

const rate = (winRate, playerGames) => ({ playerGames, matches: playerGames, wins: Math.round(playerGames * winRate), winRate })
const row = (name, wr) => ({
  cardKey: name.toLowerCase(), cardName: name, deckShare: 0.2,
  inDeck: rate(wr, 300), played: rate(wr, 200), openingHand: rate(wr, 100), inDeckUnplayed: rate(0.5, 100),
})
const CARDS = { dataAvailable: true, releasedThrough: '2026-11-01', totalGames: 1000,
  cards: [row('Whirling Blades', 0.6), row('Gravedigger', 0.45), row('Not In Deck', 0.7), row('Sorcerer', 0.52)] }
const SEASONS = [{ id: '8', name: 'Season 8', from: '2026-10-03', through: null, is_active: true }]
const DECK = [
  { name: 'Whirling Blades', qty: 3 }, { name: 'Gravedigger', qty: 2 }, { name: 'Brand New Card', qty: 1 },
]

describe('DeckCardStats', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getRankedCards.mockResolvedValue(CARDS)
    getRankedCatalog.mockResolvedValue([])
    getRankedSeasons.mockResolvedValue(SEASONS)
  })

  it('shows only the deck cards and the avatar', async () => {
    renderWithRouter(<DeckCardStats cards={DECK} avatarName="Sorcerer" />)
    expect(await screen.findByText('Whirling Blades')).toBeInTheDocument()
    expect(screen.getByText('Gravedigger')).toBeInTheDocument()
    expect(screen.getByText('Sorcerer')).toBeInTheDocument()
    expect(screen.queryByText('Not In Deck')).not.toBeInTheDocument()
    expect(screen.getByText(/No ranked data yet: Brand New Card/)).toBeInTheDocument()
    expect(screen.getByText('3 of 4 cards in this deck have ranked data')).toBeInTheDocument()
  })

  it('asks only for saved selections (all games or a season, never custom dates)', async () => {
    renderWithRouter(<DeckCardStats cards={DECK} avatarName="Sorcerer" />)
    await screen.findByText('Whirling Blades')
    expect(getRankedCards).toHaveBeenLastCalledWith({ format: 'constructed' })
    expect(screen.queryByText(/Custom dates/)).not.toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('option', { name: /Season 8/ })).toBeInTheDocument())
    await userEvent.selectOptions(screen.getByRole('combobox'), '8')
    await waitFor(() => expect(getRankedCards).toHaveBeenLastCalledWith({ format: 'constructed', from: '2026-10-03' }))
  })

  it('says so when no deck card has data', async () => {
    getRankedCards.mockResolvedValue({ ...CARDS, cards: [row('Not In Deck', 0.7)] })
    renderWithRouter(<DeckCardStats cards={DECK} avatarName="Sorcerer" />)
    expect(await screen.findByText(/None of this deck’s cards/)).toBeInTheDocument()
  })
})
