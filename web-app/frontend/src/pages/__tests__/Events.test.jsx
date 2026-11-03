import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithRouter } from '@/test/test-utils'
import Events from '../Events'

vi.mock('@/api/client', () => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  del: vi.fn(),
}))

import { get } from '@/api/client'

const EVENTS = [
  { folder: 'gencon-2026', name: 'GenCon 2026', event_date: '2026-08-01', event_date_display: 'Aug 1, 2026', winner_username: 'alice', winner_avatar: 'Druid', player_count: 64, rating: 3 },
  { folder: 'scg-portland-2026', name: 'SCG Portland 2026', event_date: '2026-05-10', event_date_display: 'May 10, 2026', winner_username: 'bob', winner_avatar: 'Elementalist', player_count: 32, rating: 2 },
]

function mockApi() {
  get.mockImplementation((url) => {
    if (url === '/api/top-8-events') return Promise.resolve({ events: EVENTS, is_admin: false, featured_event: null })
    if (url === '/api/avatar-image-files') return Promise.resolve([])
    if (url.startsWith('/api/events/')) return Promise.resolve({ top8_decks: [], all_decks: [], element_stats: null })
    return Promise.resolve({})
  })
}

/** Make `window.matchMedia` report a phone or a desktop viewport. */
function setViewport({ desktop }) {
  window.matchMedia = vi.fn().mockImplementation((query) => ({
    matches: query.includes('min-width: 1024px') ? desktop : false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
  }))
}

const rowFor = (name) => screen.getByRole('button', { name: new RegExp(name) })

describe('Events page — mobile accordion', () => {
  let scrollSpy
  beforeEach(() => {
    mockApi()
    setViewport({ desktop: false })
    scrollSpy = vi.fn()
    Element.prototype.scrollIntoView = scrollSpy
    vi.stubGlobal('requestAnimationFrame', (cb) => { cb(); return 1 })
    vi.stubGlobal('cancelAnimationFrame', () => {})
  })
  afterEach(() => vi.unstubAllGlobals())

  it('shows the preview tile inside the open accordion, right under the tapped row', async () => {
    renderWithRouter(<Events />)
    await screen.findByText('SCG Portland 2026')

    await userEvent.click(rowFor('SCG Portland 2026'))

    const row = rowFor('SCG Portland 2026')
    expect(row).toHaveAttribute('aria-expanded', 'true')
    const panel = document.getElementById(row.getAttribute('aria-controls'))
    expect(panel).not.toBeNull()
    expect(panel).toHaveAttribute('role', 'region')
    expect(panel).toHaveAttribute('aria-labelledby', row.id)
    // The panel sits immediately after its row in the DOM.
    expect(row.nextElementSibling).toBe(panel)
    // The hero tile (heading + View Decks) is the first thing in the panel.
    expect(within(panel).getByRole('heading', { level: 2, name: 'SCG Portland 2026' })).toBeInTheDocument()
    expect(within(panel).getByRole('link', { name: /View Decks/ })).toHaveAttribute('href', '/top-8/scg-portland-2026')
    expect(within(panel).getByText(/Winner:/)).toHaveTextContent('bob')
    // Only one accordion open at a time.
    expect(rowFor('GenCon 2026')).toHaveAttribute('aria-expanded', 'false')
  })

  it('keeps the tapped row in view and announces the selection', async () => {
    renderWithRouter(<Events />)
    await screen.findByText('SCG Portland 2026')
    const live = document.querySelector('[aria-live="polite"]')
    expect(live).toHaveTextContent('')

    await userEvent.click(rowFor('SCG Portland 2026'))

    await waitFor(() => expect(scrollSpy).toHaveBeenCalledWith(expect.objectContaining({ block: 'start' })))
    expect(live).toHaveTextContent('Showing SCG Portland 2026')
    expect(rowFor('SCG Portland 2026')).toHaveAttribute('aria-current', 'true')
  })

  it('uses an instant scroll when the user prefers reduced motion', async () => {
    window.matchMedia = vi.fn().mockImplementation((query) => ({
      matches: query.includes('reduced-motion'),
      media: query, addEventListener: vi.fn(), removeEventListener: vi.fn(),
    }))
    renderWithRouter(<Events />)
    await screen.findByText('SCG Portland 2026')
    await userEvent.click(rowFor('SCG Portland 2026'))
    await waitFor(() => expect(scrollSpy).toHaveBeenCalledWith(expect.objectContaining({ behavior: 'auto' })))
  })
})

describe('Events page — desktop', () => {
  beforeEach(() => {
    mockApi()
    setViewport({ desktop: true })
    Element.prototype.scrollIntoView = vi.fn()
  })

  it('does not expose accordion semantics and does not scroll', async () => {
    renderWithRouter(<Events />)
    await screen.findByText('SCG Portland 2026')
    await userEvent.click(rowFor('SCG Portland 2026'))
    const row = rowFor('SCG Portland 2026')
    expect(row).not.toHaveAttribute('aria-expanded')
    expect(row).toHaveAttribute('aria-current', 'true')
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled()
    // Preview is in the left panel: exactly one h2 for the selected event.
    expect(screen.getAllByRole('heading', { level: 2, name: 'SCG Portland 2026' })).toHaveLength(1)
  })
})

describe('Events page — event type tags', () => {
  const TAGGED = [
    { ...EVENTS[0], tag: 'Grand Contest' },
    { ...EVENTS[1], tag: 'Cornerstone' },
    { folder: 'local-night', name: 'Local Night', event_date: '2026-04-01', player_count: 12, rating: 1, tag: null },
  ]

  beforeEach(() => {
    setViewport({ desktop: true })
    get.mockImplementation((url) => {
      if (url === '/api/top-8-events') return Promise.resolve({ events: TAGGED, is_admin: false, featured_event: null, event_tags: ['Grand Contest', 'Cornerstone', 'Local'] })
      if (url === '/api/avatar-image-files') return Promise.resolve([])
      if (url.startsWith('/api/events/')) return Promise.resolve({ top8_decks: [], all_decks: [], element_stats: null })
      return Promise.resolve({})
    })
  })

  it('shows tag badges and filters the list by type', async () => {
    renderWithRouter(<Events />)
    await screen.findByText('Local Night')
    expect(within(rowFor('SCG Portland 2026')).getByText('Cornerstone')).toBeInTheDocument()

    const select = screen.getByLabelText('Type')
    // Untagged is admin-only
    expect(within(select).queryByRole('option', { name: 'Untagged' })).toBeNull()

    await userEvent.selectOptions(select, 'Cornerstone')
    expect(screen.queryByRole('button', { name: /Local Night/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /GenCon 2026/ })).toBeNull()
    expect(rowFor('SCG Portland 2026')).toBeInTheDocument()
    expect(screen.getByText('1 event')).toBeInTheDocument()

    await userEvent.selectOptions(select, 'Local')
    expect(screen.getByText('No events match your filters.')).toBeInTheDocument()

    await userEvent.selectOptions(select, '')
    expect(screen.getByText('3 events')).toBeInTheDocument()
  })
})

describe('Events page — deck filters', () => {
  const INDEX = {
    events: {
      'gencon-2026': [
        [1, 'alice', 'Druid', ['Earth', 'Water'], 'd1'],
        [2, 'carol', 'Sparkmage', ['Fire', 'Air'], 'd2'],
        [null, 'dave', 'Sparkmage', ['Fire'], 'd3'],
      ],
      'scg-portland-2026': [
        [1, 'bob', 'Elementalist', ['Fire', 'Water'], 'd4'],
        [5, 'alice', 'Sparkmage', ['Air', 'Fire'], 'd5'],
      ],
    },
    avatars: ['Druid', 'Elementalist', 'Sparkmage'],
    cards: ['Askelon Phoenix', 'Blink'],
  }

  beforeEach(() => {
    setViewport({ desktop: true })
    Element.prototype.scrollIntoView = vi.fn()
    get.mockImplementation((url) => {
      if (url === '/api/top-8-events') return Promise.resolve({ events: EVENTS, is_admin: false, featured_event: null })
      if (url === '/api/avatar-image-files') return Promise.resolve([])
      if (url === '/api/top-8-events/deck-index') return Promise.resolve(INDEX)
      if (url.startsWith('/api/top-8-events/card-search')) {
        return Promise.resolve({ matches: url.includes('Blink') ? { 'scg-portland-2026': [0] } : {} })
      }
      if (url.startsWith('/api/events/')) return Promise.resolve({ top8_decks: [], all_decks: [], element_stats: null })
      return Promise.resolve({})
    })
  })

  it('filters by avatar and lists the matching decks with their finish', async () => {
    renderWithRouter(<Events />)
    await screen.findByText('SCG Portland 2026')
    const avatar = screen.getByLabelText('Avatar')
    await waitFor(() => expect(within(avatar).getByRole('option', { name: 'Druid' })).toBeInTheDocument())

    await userEvent.selectOptions(avatar, 'Druid')
    expect(screen.queryByRole('button', { name: /SCG Portland 2026/ })).toBeNull()
    expect(rowFor('GenCon 2026')).toBeInTheDocument()
    expect(screen.getByText('1 matching deck')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /1st\s*alice\s*Druid/ })).toHaveAttribute('href', '/deck-rec/d1')

    // Sparkmage: both events; Finish = Top 4 leaves only Gen Con's finalist
    await userEvent.selectOptions(avatar, 'Sparkmage')
    expect(screen.getByText(/2 events · 3 matching decks/)).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Finish'), '4')
    expect(screen.getByText(/1 event · 1 matching deck/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /2nd\s*carol/ })).toBeInTheDocument()
  })

  it('searches player names and needs every picked element', async () => {
    renderWithRouter(<Events />)
    await screen.findByText('SCG Portland 2026')
    await userEvent.type(screen.getByLabelText('Search player or event'), 'bob')
    await waitFor(() => expect(screen.queryByRole('button', { name: /GenCon 2026/ })).toBeNull())
    expect(screen.getByRole('link', { name: /1st\s*bob/ })).toBeInTheDocument()

    await userEvent.clear(screen.getByLabelText('Search player or event'))
    await userEvent.click(screen.getByRole('button', { name: 'Fire', pressed: false }))
    await userEvent.click(screen.getByRole('button', { name: 'Air', pressed: false }))
    expect(screen.getByText(/2 events · 2 matching decks/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(screen.getByText('2 events')).toBeInTheDocument()
  })

  it('filters by a card once a real card name is typed', async () => {
    renderWithRouter(<Events />)
    await screen.findByText('SCG Portland 2026')
    await waitFor(() => expect(within(screen.getByLabelText('Avatar')).getByRole('option', { name: 'Druid' })).toBeInTheDocument())
    await userEvent.type(screen.getByLabelText('Deck runs card'), 'blink')
    await waitFor(() => expect(screen.queryByRole('button', { name: /GenCon 2026/ })).toBeNull())
    expect(get).toHaveBeenCalledWith('/api/top-8-events/card-search?card=Blink')
    expect(screen.getByRole('link', { name: /1st\s*bob/ })).toBeInTheDocument()
  })

  it('reads filters from the link', async () => {
    renderWithRouter(<Events />, { route: '/top-8?avatar=Elementalist' })
    // Wait for the events to load first: before they do, GenCon is "missing" too.
    await waitFor(() => expect(rowFor('SCG Portland 2026')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /GenCon 2026/ })).toBeNull()
    expect(screen.getByLabelText('Avatar')).toHaveValue('Elementalist')
  })
})
