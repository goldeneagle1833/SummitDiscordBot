import { describe, it, expect, vi, beforeEach } from 'vitest'
import { Routes, Route } from 'react-router-dom'
import { renderWithRouter, screen, waitFor, userEvent } from '@/test/test-utils'
import CardDetail from '@/pages/CardDetail'
import { getCard } from '@/api/cards'
import { getRankedCards, getRankedCatalog, getRankedCardReplays, getRankedSeasons } from '@/api/rankedAnalytics'
import { get } from '@/api/client'

vi.mock('@/api/cards', async () => {
  const actual = await vi.importActual('@/api/cards')
  return { ...actual, getCard: vi.fn() }
})
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
vi.mock('@/api/client', async () => {
  const actual = await vi.importActual('@/api/client')
  return { ...actual, get: vi.fn() }
})

const rate = (winRate, playerGames) => ({ playerGames, matches: playerGames, wins: Math.round(playerGames * winRate), winRate })

const CARD = {
  name: 'Pudge Butcher', element: 'Fire', type: 'Minion', rarity: 'Elite', set: 'Arthurian Legends',
  cost: 3, power: 3, defense: 3, text: 'Some rules text', image: null,
  wins: 12, losses: 8, total_matches: 20, win_rate: 60,
}
const RANKED = {
  dataAvailable: true,
  cards: [
    {
      cardKey: 'pudge butcher', cardName: 'Pudge Butcher', deckShare: 0.2,
      inDeck: rate(0.55, 400), played: rate(0.6, 200), openingHand: rate(0.58, 90), inDeckUnplayed: rate(0.5, 200),
    },
    {
      cardKey: 'gravedigger', cardName: 'Gravedigger', deckShare: 0.1,
      inDeck: rate(0.49, 100), played: rate(0.44, 50), openingHand: rate(0.5, 30), inDeckUnplayed: rate(0.5, 50),
    },
  ],
}
const USAGE = [
  { name: 'Gravedigger', decks_with_card: 80, total_decks: 200, average_played: 2, count: 160, sideboard_count: 3 },
  { name: 'Pudge Butcher', decks_with_card: 40, total_decks: 200, average_played: 3, count: 120, sideboard_count: 5 },
]
const SEASONS = [{ id: '8', name: 'Season 8', from: '2026-10-03', through: null, is_active: true }]

const renderPage = () => renderWithRouter(
  <Routes><Route path="/card/:name" element={<CardDetail />} /></Routes>,
  { route: '/card/Pudge%20Butcher' },
)

describe('CardDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getCard.mockResolvedValue(CARD)
    getRankedCards.mockResolvedValue(RANKED)
    getRankedCatalog.mockResolvedValue([])
    getRankedSeasons.mockResolvedValue(SEASONS)
    getRankedCardReplays.mockResolvedValue({ replays: [] })
    get.mockImplementation((url) => {
      if (url.startsWith('/api/creator/popular-cards')) return Promise.resolve(USAGE)
      if (url.startsWith('/api/creator/card-history')) return Promise.resolve([])
      if (url.startsWith('/api/data-release')) return Promise.resolve({})
      return Promise.reject(new Error(`not mocked: ${url}`))
    })
  })

  it('keeps the card info and match stats, and links back to Card Stats', async () => {
    renderPage()
    expect(await screen.findByRole('heading', { name: 'Pudge Butcher' })).toBeInTheDocument()
    expect(screen.getByText('Some rules text')).toBeInTheDocument()
    expect(screen.getByText('60%')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Card Stats/ })).toHaveAttribute('href', '/card-stats')
  })

  it('shows the saved PSO win rates and Summit popularity for the card', async () => {
    renderPage()
    expect(await screen.findByText('60.0%')).toBeInTheDocument() // played
    expect(screen.getByText('55.0%')).toBeInTheDocument() // in deck
    expect(screen.getByText('58.0%')).toBeInTheDocument() // opening hand
    expect(screen.getByText('+10.0 pp')).toBeInTheDocument() // effect of playing
    expect(screen.getByText('20.0%')).toBeInTheDocument() // 40 of 200 decks
    expect(screen.getByText('#2 of 2 cards')).toBeInTheDocument()
    expect(getRankedCards).toHaveBeenCalledWith({ format: 'constructed' })
  })

  it('asks PSO for replays only when the visitor presses the button', async () => {
    renderPage()
    const button = await screen.findByRole('button', { name: 'Show public replays' })
    expect(getRankedCardReplays).not.toHaveBeenCalled()
    await userEvent.click(button)
    await waitFor(() => expect(getRankedCardReplays).toHaveBeenCalledWith('pudge butcher', { format: 'constructed' }))
  })

  it('switches to a season from the saved data', async () => {
    renderPage()
    await screen.findByText('60.0%')
    await userEvent.selectOptions(screen.getByLabelText('Season'), '8')
    await waitFor(() => expect(getRankedCards).toHaveBeenLastCalledWith({ format: 'constructed', from: '2026-10-03' }))
    expect(get).toHaveBeenCalledWith('/api/creator/popular-cards?event=8')
  })
})
