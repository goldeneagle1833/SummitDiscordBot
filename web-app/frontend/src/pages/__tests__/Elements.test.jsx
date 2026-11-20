import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, within } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import Elements from '../Elements'

vi.mock('@/api/client', () => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() }))
vi.mock('@/api/cards', () => ({ getAvatarImageFiles: vi.fn(() => Promise.resolve([])) }))

import { get } from '@/api/client'

const TIMELINE = {
  dates: ['2026-09-01', '2026-09-02'],
  days: {
    '2026-09-01': { el: { Fire: [3, 0] }, dom: { Fire: [3, 0] } },
    '2026-09-02': { el: { Fire: [0, 1], Water: [1, 0] }, dom: { Water: [1, 0] } },
  },
}
const META = {
  dates: ['2026-09-01', '2026-09-02'],
  avatars: { Sorcerer: { '2026-09-01': 3 }, Druid: { '2026-09-02': 1 } },
  matchups: {
    '2026-09-01': { 'Druid|Water>Sorcerer|Fire': 15, 'Sorcerer|Fire>Druid|Water': 5, 'Sorcerer|Fire>Druid|Earth': 12 },
    '2026-09-02': { 'Sorcerer|Fire>Druid|Water': 4 },
  },
}

describe('Elements page timeline', () => {
  beforeEach(() => {
    get.mockImplementation((url) => {
      if (url.startsWith('/api/elements/filters')) return Promise.resolve({ events: [] })
      if (url.startsWith('/api/elements/timeline')) return Promise.resolve(TIMELINE)
      if (url.startsWith('/api/elements/avatar-meta')) return Promise.resolve(META)
      return Promise.resolve({})
    })
  })

  it('moves every chart with the shared slider', async () => {
    renderWithRouter(<Elements />)
    const winRate = (await screen.findByText('Win Rate by Element')).parentElement
    // All time on the latest day: Fire 3-1
    expect(within(winRate).getByText('3W - 1L')).toBeInTheDocument()
    expect(screen.getAllByTestId('meta-row')).toHaveLength(2)

    fireEvent.change(screen.getByLabelText('Date'), { target: { value: '0' } })
    expect(within(winRate).getByText('3W - 0L')).toBeInTheDocument()
    expect(screen.getAllByTestId('meta-row')).toHaveLength(1)
  })

  it('loads all events by default', async () => {
    renderWithRouter(<Elements />)
    await screen.findByText('Win Rate by Element')
    expect(get).toHaveBeenCalledWith('/api/elements/timeline')
  })

  it('shows what the deck picked in the top bar loses to, following the timeline', async () => {
    renderWithRouter(<Elements />)
    const section = (await screen.findByText("Your Deck's Matchups")).closest('section')
    expect(await within(section).findByText('Mono Fire decks')).toBeInTheDocument()
    // All time: Mono Fire is 21-15 (36 games); loses to Druid Water 9-15, beats Druid Earth 12-0
    const deck = screen.getByRole('combobox', { name: 'Your deck type' })
    expect(deck).toHaveValue('Fire')
    fireEvent.click(screen.getByRole('button', { name: 'Deck types' }))
    expect(within(section).getByText('37.5%')).toBeInTheDocument()
    expect(within(section).getByText('100%')).toBeInTheDocument()
    // Pick another deck type in the top bar
    fireEvent.change(deck, { target: { value: 'Water' } })
    expect(within(section).getByText('Mono Water decks')).toBeInTheDocument()
    expect(within(section).getAllByText('62.5%')).toHaveLength(2)
    // First day only: Water vs Fire is 20 games, still listed
    fireEvent.change(screen.getByLabelText('Date'), { target: { value: '0' } })
    expect(within(section).getAllByText('75%')).toHaveLength(2)
  })
})
