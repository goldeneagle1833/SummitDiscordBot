import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithRouter, screen, waitFor, userEvent, within } from '@/test/test-utils'
import CardPlayedWinrates from '@/pages/CardPlayedWinrates'
import { getRankedCards, getRankedCatalog, getRankedCardReplays, getRankedSeasons } from '@/api/rankedAnalytics'
import { ApiError } from '@/api/client'

vi.mock('@/api/rankedAnalytics', async () => {
  const actual = await vi.importActual('@/api/rankedAnalytics')
  return {
    ...actual,
    getRankedCards: vi.fn(),
    getRankedCatalog: vi.fn(),
    getRankedCardReplays: vi.fn(),
    getRankedSeasons: vi.fn(),
  }
})

const rate = (winRate, playerGames) => ({
  playerGames, matches: playerGames, wins: Math.round(playerGames * (winRate ?? 0)), winRate,
})
const suppressed = { playerGames: null, matches: null, wins: null, winRate: null }

const CARDS = {
  generatedAt: 1790000000000,
  releasedThrough: '2026-09-27',
  dataAvailable: true,
  totalGames: 4812,
  totalPlayerGames: 9624,
  cards: [
    {
      cardKey: 'whirling blades', cardName: 'Whirling Blades', deckShare: 0.31,
      inDeck: rate(0.54, 1490), played: rate(0.612, 412), openingHand: rate(0.575, 203), inDeckUnplayed: rate(0.528, 1078),
    },
    {
      cardKey: 'gravedigger', cardName: 'Gravedigger', deckShare: 0.09,
      inDeck: rate(0.489, 433), played: rate(0.441, 121), openingHand: suppressed, inDeckUnplayed: rate(0.503, 312),
    },
    {
      cardKey: 'imposter', cardName: 'Imposter', deckShare: 0.106,
      inDeck: rate(0.551, 512), played: suppressed, openingHand: suppressed, inDeckUnplayed: suppressed,
    },
  ],
}

const SEASONS = [
  { id: '8', name: 'Season 8', from: '2026-10-03', through: null, is_active: true },
  { id: '7', name: 'Season 7', from: '2026-08-30', through: '2026-09-28', is_active: false },
]

const CATALOG = [
  { name: 'Whirling Blades', type: 'Magic', elements: ['Air'], rarity: 'Exceptional', imageUrl: '/card-images/alp-whirling_blades-b-s.png' },
  { name: 'Gravedigger', type: 'Minion', elements: ['Earth'], rarity: 'Ordinary', imageUrl: null },
  { name: 'Imposter', type: 'Avatar', elements: [], rarity: 'Unique', imageUrl: '/card-images/got-imposter-b-s.png' },
  { name: 'Battlemage', type: 'Avatar', elements: [], rarity: 'Unique', imageUrl: '/card-images/alp-battlemage-b-s.png' },
]

describe('CardPlayedWinrates', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getRankedCatalog.mockResolvedValue(CATALOG)
    getRankedCards.mockResolvedValue(CARDS)
    getRankedCardReplays.mockResolvedValue({ replays: [] })
    getRankedSeasons.mockResolvedValue(SEASONS)
  })

  it('asks the proxy for constructed cards and renders the table', async () => {
    renderWithRouter(<CardPlayedWinrates />)

    expect(await screen.findByRole('row', { name: /Whirling Blades/ })).toBeInTheDocument()
    expect(getRankedCards).toHaveBeenCalledWith({ format: 'constructed' })
    expect(screen.getByText('4,812 games')).toBeInTheDocument()
    expect(screen.getByText(/data through 2026-09-27/)).toBeInTheDocument()

    const row = screen.getByRole('row', { name: /Whirling Blades/ })
    expect(within(row).getByText('61.2%')).toBeInTheDocument()
    expect(within(row).getByText('+8.4 pp')).toBeInTheDocument()
    expect(within(row).getByText('412 games')).toBeInTheDocument()
  })

  it('sorts by played win rate by default and labels suppressed rates', async () => {
    renderWithRouter(<CardPlayedWinrates />)
    await screen.findByRole('row', { name: /Whirling Blades/ })

    const names = screen.getAllByRole('row').slice(1).map((r) => within(r).getByRole('button', { expanded: false }).textContent)
    // Suppressed rates always sort last, whatever the direction.
    expect(names).toEqual(['▸Whirling Blades', '▸Gravedigger', '▸Imposter'])
    const imposter = screen.getByRole('row', { name: /Imposter/ })
    expect(within(imposter).getAllByText('under 20 games').length).toBeGreaterThan(0)
  })

  it('shows standout tiles drawn from the same rows', async () => {
    renderWithRouter(<CardPlayedWinrates />)
    await screen.findByRole('row', { name: /Whirling Blades/ })

    const tiles = screen.getByLabelText('Standout cards')
    expect(within(tiles).getByText('Best when played').parentElement).toHaveTextContent('Whirling Blades')
    expect(within(tiles).getByText('Underperforming').parentElement).toHaveTextContent('Gravedigger')
  })

  it('filters rows by search and by quick filter', async () => {
    const user = userEvent.setup()
    renderWithRouter(<CardPlayedWinrates />)
    await screen.findByRole('row', { name: /Whirling Blades/ })

    await user.type(screen.getByLabelText('Search cards'), 'grave')
    expect(screen.queryByRole('row', { name: /Whirling Blades/ })).not.toBeInTheDocument()
    expect(screen.getByRole('row', { name: /Gravedigger/ })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    await user.click(screen.getByRole('button', { name: 'Avatar' }))
    expect(screen.getByRole('row', { name: /Imposter/ })).toBeInTheDocument()
    expect(screen.queryByRole('row', { name: /Gravedigger/ })).not.toBeInTheDocument()
  })

  it('turns a chosen season into that season\u2019s date range', async () => {
    const user = userEvent.setup()
    renderWithRouter(<CardPlayedWinrates />)
    await screen.findByRole('row', { name: /Whirling Blades/ })
    await screen.findByRole('option', { name: /Season 7/ })

    await user.selectOptions(screen.getByLabelText('Season'), '7')
    await waitFor(() => expect(getRankedCards).toHaveBeenLastCalledWith({ format: 'constructed', from: '2026-08-30', through: '2026-09-28' }))
    expect(screen.queryByLabelText('From')).not.toBeInTheDocument()

    // A season still running has no end date yet.
    await user.selectOptions(screen.getByLabelText('Season'), '8')
    await waitFor(() => expect(getRankedCards).toHaveBeenLastCalledWith({ format: 'constructed', from: '2026-10-03' }))

    await user.selectOptions(screen.getByLabelText('Season'), 'custom')
    expect(screen.getByLabelText('From')).toBeInTheDocument()
    expect(screen.getByLabelText('Through')).toBeInTheDocument()
  })

  it('renders rate columns it did not know about, such as in hand', async () => {
    const user = userEvent.setup()
    getRankedCards.mockResolvedValue({
      ...CARDS,
      cards: CARDS.cards.map((c, i) => ({
        ...c,
        inHand: rate(0.5 + i * 0.05, 100 + i),
        notInHand: i === 2 ? suppressed : rate(0.45, 90),
      })),
    })
    renderWithRouter(<CardPlayedWinrates />)
    await screen.findByRole('row', { name: /Whirling Blades/ })

    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent.replace(/[\u2191\u2193\u2195]/g, '').trim())
    expect(headers).toEqual(['Card', 'Popularity', 'In deck', 'Played', 'Opening hand', 'In hand', 'Not in hand', 'Not played', 'Effect of playing it'])
    expect(within(screen.getByRole('row', { name: /Whirling Blades/ })).getByText('50.0%')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /In hand/ }))
    const names = screen.getAllByRole('row').slice(1).map((r) => within(r).getByRole('button', { expanded: false }).textContent)
    expect(names).toEqual(['\u25b8Imposter', '\u25b8Gravedigger', '\u25b8Whirling Blades'])
  })

  it('expands a card into art and replay clips', async () => {
    const user = userEvent.setup()
    getRankedCardReplays.mockResolvedValue({
      replays: [{
        clipId: 'clip-123', finishedAt: 1790000000000, won: true,
        player: { avatarNames: ['Imposter'], colors: ['fire'] },
        opponent: { avatarNames: ['Battlemage'], colors: ['water'] },
      }],
    })
    renderWithRouter(<CardPlayedWinrates />)
    await screen.findByRole('row', { name: /Whirling Blades/ })

    const row = screen.getByRole('row', { name: /Whirling Blades/ })
    await user.click(within(row).getByRole('button', { name: /Whirling Blades/ }))

    expect(getRankedCardReplays).toHaveBeenCalledWith('whirling blades', { format: 'constructed' })
    expect(await screen.findByRole('link', { name: /Win ·/ })).toHaveAttribute(
      'href', 'https://playsorceryonline.com/replay-clips/clip-123',
    )
    expect(screen.getByRole('img', { name: 'Whirling Blades' })).toHaveAttribute('src', '/card-images/alp-whirling_blades-b-s.png')
    expect(screen.getByRole('img', { name: 'Imposter' })).toHaveAttribute('src', '/card-images/got-imposter-b-s.png')
    expect(screen.getByText('In deck, never played')).toBeInTheDocument()
  })

  it('explains when the partner route is not live yet', async () => {
    getRankedCards.mockRejectedValue(new ApiError(503, 'Ranked analytics is unavailable'))
    renderWithRouter(<CardPlayedWinrates />)

    expect(await screen.findByText(/isn’t available yet/)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('treats dataAvailable false the same way', async () => {
    getRankedCards.mockResolvedValue({ ...CARDS, dataAvailable: false, totalGames: 0, cards: [] })
    renderWithRouter(<CardPlayedWinrates />)

    expect(await screen.findByText(/isn’t available yet/)).toBeInTheDocument()
  })

  it('still renders rows when the catalog fails', async () => {
    getRankedCatalog.mockRejectedValue(new Error('nope'))
    renderWithRouter(<CardPlayedWinrates />)

    expect(await screen.findByRole('row', { name: /Whirling Blades/ })).toBeInTheDocument()
    expect(screen.getByText(/quick filters could not be loaded/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Minion' })).toBeDisabled()
  })
})
