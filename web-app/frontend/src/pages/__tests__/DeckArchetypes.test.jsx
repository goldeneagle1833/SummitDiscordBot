import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithRouter } from '@/test/test-utils'
import DeckArchetypes from '../DeckArchetypes'

vi.mock('@/api/client', () => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  del: vi.fn(),
}))

import { get } from '@/api/client'

const GROUP = {
  id: 'sorcerer-fire-d1',
  name: 'Sorcerer · Fire',
  avatar: 'Sorcerer',
  avatars: [['Sorcerer', 5]],
  elements: [['Fire', 5]],
  elementsLabel: 'Fire',
  size: 5,
  tournamentDecks: 2,
  wins: 1,
  top8: 2,
  topCut: 2,
  events: 1,
  rankedGames: 40,
  rankedWins: 24,
  rankedLosses: 16,
  rankedWinRate: 0.6,
  players: 4,
}
const TOURNAMENT_GROUP = { ...GROUP, id: 'sorcerer-fire-t1', name: 'Sorcerer · Fire (cup)', rankedGames: 0, rankedWins: 0, rankedLosses: 0, rankedWinRate: null }
const META = { source: 'all', threshold: 0.35, fetchedDecks: 5, tournamentCount: 1, rankedGames: 40, tournamentDecks: 2, rankedDecks: 3, pendingDecks: 0, unavailableDecks: 0 }
const DETAIL = {
  status: 'ready',
  patterns: {
    spellbook: [{ name: 'Fireball', count: 5, rate: 1, avgCopies: 3, image: 'fireball.webp' }],
    atlas: [{ name: 'Arid Desert', count: 5, rate: 1, avgCopies: 2, image: 'arid_desert.webp' }],
    collection: [],
  },
  recommendations: [{ deckId: 'd1', label: 'Representative deck' }],
  members: ['d1', 'd2'],
  decks: {
    d1: { id: 'd1', name: 'Burn It', url: 'https://sorcerytcg.com/decks/d1', deckRecId: 'd1', avatar: 'Sorcerer', elements: 'Fire', entries: [{ event: 'Cup', player: 'alice', placement: 1, top8: true, topCut: true }] },
    d2: { id: 'd2', name: 'Ranked Burn', url: null, avatar: 'Sorcerer', elements: 'Fire', entries: [], ranked: { wins: 9, losses: 3, player: 'bob' } },
  },
}

describe('DeckArchetypes', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockImplementation((url) => {
      if (url === '/api/avatars/image-files') return Promise.resolve([])
      if (url.startsWith('/api/deck-archetypes?source=all')) return Promise.resolve({ status: 'ready', meta: META, groups: [GROUP] })
      if (url === '/api/deck-archetypes?source=tournament') return Promise.resolve({ status: 'ready', meta: { ...META, source: 'tournament' }, groups: [TOURNAMENT_GROUP] })
      if (url.startsWith('/api/deck-archetypes/')) return Promise.resolve(DETAIL)
      return Promise.resolve({})
    })
  })

  it('shows ranked stats on archetype cards', async () => {
    renderWithRouter(<DeckArchetypes />)
    expect(await screen.findByText('Sorcerer · Fire')).toBeInTheDocument()
    expect(screen.getByText(/40 ranked games · 60% win rate/)).toBeInTheDocument()
  })

  it('reloads from tournament decks only when that option is picked', async () => {
    renderWithRouter(<DeckArchetypes />)
    await screen.findByText('Sorcerer · Fire')
    await userEvent.click(screen.getByRole('button', { name: 'Tournaments only' }))
    expect(await screen.findByText('Sorcerer · Fire (cup)')).toBeInTheDocument()
    expect(get).toHaveBeenCalledWith('/api/deck-archetypes?source=tournament')
  })

  it('loads an archetype’s decks when its card is opened', async () => {
    renderWithRouter(<DeckArchetypes />)
    await userEvent.click(await screen.findByRole('button', { name: /View Sorcerer · Fire/ }))
    expect(await screen.findByText('Ranked Burn')).toBeInTheDocument()
    expect(screen.getAllByText('Burn It').length).toBeGreaterThan(0)
    expect(get).toHaveBeenCalledWith('/api/deck-archetypes/sorcerer-fire-d1?source=all')
    // A ranked deck reported without a link isn't rendered as a link.
    expect(screen.getByText('Ranked Burn').closest('a')).toBeNull()
    // Sorcery TCG lists open on Summit's Deck Rec page.
    for (const name of screen.getAllByText('Burn It')) {
      expect(name.closest('a')).toHaveAttribute('href', '/deck-rec/d1')
    }
  })

  it('asks the server again when a date range and event size are picked', async () => {
    renderWithRouter(<DeckArchetypes />)
    await screen.findByText('Sorcerer · Fire')
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-01-01' } })
    await userEvent.selectOptions(screen.getByLabelText('Event size'), '32')
    await waitFor(() => expect(get).toHaveBeenCalledWith('/api/deck-archetypes?source=all&from=2026-01-01&min_event_decks=32'))
    await userEvent.click(screen.getByRole('button', { name: 'Clear dates and size' }))
    await waitFor(() => expect(get).toHaveBeenLastCalledWith('/api/deck-archetypes?source=all'))
  })

  it('previews hovered cards and turns sites sideways', async () => {
    const rect = vi.spyOn(Element.prototype, 'getBoundingClientRect')
      .mockReturnValue({ left: 960, top: 100, right: 1920, bottom: 140, width: 960, height: 40 })
    renderWithRouter(<DeckArchetypes />)
    await userEvent.click(await screen.findByRole('button', { name: /View Sorcerer · Fire/ }))
    fireEvent.mouseEnter((await screen.findByText('Fireball')).parentElement)
    expect(screen.getByAltText('Fireball')).not.toHaveClass('rotate-90')
    await userEvent.click(screen.getByRole('button', { name: 'atlas' }))
    fireEvent.mouseEnter((await screen.findByText('Arid Desert')).parentElement)
    expect(screen.getByAltText('Arid Desert')).toHaveClass('rotate-90')
    rect.mockRestore()
  })

  it('waits while the server builds its first snapshot', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let calls = 0
    get.mockImplementation((url) => {
      if (url === '/api/deck-archetypes?source=all') {
        calls += 1
        return Promise.resolve(calls === 1 ? { status: 'building' } : { status: 'ready', meta: META, groups: [GROUP] })
      }
      return Promise.resolve([])
    })
    renderWithRouter(<DeckArchetypes />)
    expect(await screen.findByText('Loading deck archetypes…')).toBeInTheDocument()
    await vi.advanceTimersByTimeAsync(5000)
    await waitFor(() => expect(screen.getByText('Sorcerer · Fire')).toBeInTheDocument())
    vi.useRealTimers()
  })
})
