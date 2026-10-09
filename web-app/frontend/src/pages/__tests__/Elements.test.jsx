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
})
