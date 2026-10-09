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
