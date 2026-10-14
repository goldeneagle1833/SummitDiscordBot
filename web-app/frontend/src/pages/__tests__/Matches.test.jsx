import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import Matches from '../Matches'

vi.mock('@/api/client', () => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() }))

import { get } from '@/api/client'

const RECAP = {
  kind: 'daily',
  date: '2026-10-09',
  title: '📊 Daily Recap — Friday, October 09, 2026',
  compare_label: 'yesterday',
  footer: 'Summit Bot • Matches tracked since midnight EST',
  stats: {
    total_matches: 12,
    casual_matches: 3,
    unique_players: 8,
    top_gainer: ['111', 'OldName', 42],
    rivalry: ['111', 'OldName', '222', 'Bob', 2, 1, 3],
    hot_streaks: [['222', 'Bob', 4]],
    broken_streaks: [],
  },
  previous: { total_matches: 10, unique_players: 6 },
  names: { 111: 'Alice' },
}

describe('Matches page recap', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockImplementation((url) => {
      if (url.startsWith('/api/match-history/available-dates')) return Promise.resolve(['2026-10-09'])
      if (url.startsWith('/api/match-history/recap')) return Promise.resolve(RECAP)
      return Promise.resolve([])
    })
  })

  it('shows the recap from the Discord link and loads that date', async () => {
    renderWithRouter(<Matches />, { route: '/match-history?recap=daily&date=2026-10-09' })

    expect(await screen.findByText(RECAP.title)).toBeInTheDocument()
    expect(get).toHaveBeenCalledWith('/api/match-history/recap?kind=daily&date=2026-10-09')
    expect(get).toHaveBeenCalledWith('/api/match-history?date=2026-10-09')
    expect(screen.getByText(/matches total/).textContent).toBe('📅 15 matches total — ▲ 5 vs yesterday (10)')
    // Saved server display name wins over the stored match name
    expect(screen.getAllByRole('link', { name: 'Alice' })[0]).toHaveAttribute('href', '/player/111')
    expect(screen.getByText(/wins in a row/)).toBeInTheDocument()
  })

  it('shows no recap without the link params', async () => {
    renderWithRouter(<Matches />, { route: '/match-history' })

    expect(await screen.findByText('No matches recorded')).toBeInTheDocument()
    expect(screen.queryByLabelText('Recap')).not.toBeInTheDocument()
    expect(get).not.toHaveBeenCalledWith(expect.stringContaining('/recap'))
  })
})

describe('Matches page replay column', () => {
  it('links to the Sorcery Online replay when a match has one', async () => {
    const replay = 'https://playsorceryonline.com/replay/abc123'
    get.mockReset()
    get.mockImplementation((url) => {
      if (url.startsWith('/api/match-history/available-dates')) return Promise.resolve([])
      return Promise.resolve([
        { match_id: 2, winner: 'Alice', winner_id: '1', loser: 'Bob', loser_id: '2',
          winner_elo_change: 16, loser_elo_change: -16, replay_url: replay },
        { match_id: 1, winner: 'Cara', winner_id: '3', loser: 'Dan', loser_id: '4',
          winner_elo_change: 16, loser_elo_change: -16, replay_url: null },
      ])
    })
    renderWithRouter(<Matches />, { route: '/match-history' })

    const watch = await screen.findByRole('link', { name: 'Watch' })
    expect(watch).toHaveAttribute('href', replay)
    expect(watch).toHaveAttribute('target', '_blank')
    expect(screen.getAllByRole('link', { name: 'Watch' })).toHaveLength(1)
    expect(screen.getByText('Replay')).toBeInTheDocument()
  })
})
