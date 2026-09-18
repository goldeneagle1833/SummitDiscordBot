import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithRouter } from '@/test/test-utils'
import EventDetail from '../EventDetail'

vi.mock('@/api/client', () => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  del: vi.fn(),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useParams: () => ({ folder: 'Test Event' }) }
})

import { get } from '@/api/client'

const EVENT = {
  event_name: 'Test Event',
  event_folder: 'Test Event',
  description: '',
  top8_decks: [
    { player: 'paladin_of_io', avatar: 'Druid', deck_name: 'Seeing Red', deck_id: 'deck-1' },
    { player: 'nohistory', avatar: 'Battlemage', deck_name: 'Other', deck_id: 'deck-9' },
  ],
  all_decks: [],
  card_data: [],
  top8_card_data: [],
  element_stats: null,
  element_stats_by_group: null,
  is_admin: false,
}

const HISTORY = {
  available: true,
  event_url: 'https://sorcerytcg.com/events/abc123',
  fetched_at: '2026-09-12T18:00:00',
  by_username: { paladin_of_io: 'deck-1' },
  by_deck_id: {
    'deck-1': {
      display_name: 'Christian V',
      deck_id: 'deck-1',
      avatar: 'Druid',
      profile_image: '',
      wins: 2,
      losses: 0,
      draws: 0,
      matches: [
        {
          round: 2,
          phase: 'SingleElimination',
          result: 'Win',
          is_bye: false,
          opponent: {
            display_name: 'Gideon M',
            deck_id: 'deck-2',
            avatar: 'Battlemage',
            profile_image: '',
          },
        },
        { round: 1, phase: 'Swiss', result: 'Win', is_bye: true, opponent: null },
      ],
    },
  },
}

function mockApi({ history = HISTORY } = {}) {
  get.mockImplementation((url) => {
    if (url.includes('/match-history')) return Promise.resolve(history)
    if (url.includes('/avatars/image-files')) return Promise.resolve([])
    if (url.includes('/api/events/')) return Promise.resolve(EVENT)
    return Promise.resolve({})
  })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('EventDetail match history', () => {
  it('expands a player row into their rounds, newest first', async () => {
    mockApi()
    renderWithRouter(<EventDetail />)

    const toggle = await screen.findByRole('button', { name: /paladin_of_io/ })
    expect(screen.queryByText('Round 2')).not.toBeInTheDocument()

    await userEvent.click(toggle)

    const rounds = screen.getAllByText(/^Round \d+$/).map((el) => el.textContent)
    expect(rounds).toEqual(['Round 2', 'Round 1'])
    expect(screen.getByText('Opponent: Gideon M')).toBeInTheDocument()
    expect(screen.getByText('Top Cut')).toBeInTheDocument()
    expect(screen.getByText('Bye')).toBeInTheDocument()
  })

  it('links each opponent to their deck rec page', async () => {
    mockApi()
    renderWithRouter(<EventDetail />)

    await userEvent.click(await screen.findByRole('button', { name: /paladin_of_io/ }))

    const links = screen.getAllByRole('link', { name: 'Deck List' })
    expect(links.some((a) => a.getAttribute('href') === '/deck-rec/deck-2')).toBe(true)
  })

  it('shows the record beside players we have pairings for', async () => {
    mockApi()
    renderWithRouter(<EventDetail />)

    expect(await screen.findByText(/2-0 · 2 rounds/)).toBeInTheDocument()
  })

  it('leaves players without pairings as plain rows', async () => {
    mockApi()
    renderWithRouter(<EventDetail />)

    await screen.findByRole('button', { name: /paladin_of_io/ })
    expect(screen.queryByRole('button', { name: /nohistory/ })).not.toBeInTheDocument()
    expect(screen.getByText('nohistory')).toBeInTheDocument()
  })

  it('renders the deck tables unchanged when no history was imported', async () => {
    mockApi({ history: { available: false, by_deck_id: {}, by_username: {} } })
    renderWithRouter(<EventDetail />)

    expect(await screen.findByText('paladin_of_io')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /paladin_of_io/ })).not.toBeInTheDocument()
  })
})
