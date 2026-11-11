import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, within } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'

vi.mock('@/context/AuthContext', () => ({ useAuth: () => ({ user: null }) }))
vi.mock('@/api/client', () => ({ get: vi.fn(() => Promise.resolve({})) }))
vi.mock('@/api/cards', () => ({
  getAvatarImageFiles: vi.fn(() => Promise.resolve([])),
  getSeasonAvatarBadges: vi.fn(() => Promise.resolve({ badges: [] })),
}))
vi.mock('@/api/leaderboard', () => ({
  getLimitedLeaderboard: vi.fn(() => Promise.resolve({ leaderboard: [] })),
  getPreconStandings: vi.fn(() => Promise.resolve({
    season: {
      season_id: 1, name: 'LM vs FM 1', starts_at: '2026-11-12T18:00:00',
      ends_at: '2099-12-10T18:00:00', last_day: '2099-12-10T18:00:00', is_open: true,
    },
    seasons: [],
    min_ranked_games: 5,
    standings: [
      { user_id: '1', name: 'Alice', rating: 1612, games: 9, wins: 7, losses: 2,
        lm_wins: 5, lm_losses: 1, fm_wins: 2, fm_losses: 1, ranked: true, rank: 1 },
      { user_id: '2', name: 'Bob', rating: 1530, games: 2, wins: 1, losses: 1,
        lm_wins: 0, lm_losses: 0, fm_wins: 1, fm_losses: 1, ranked: false, rank: null },
    ],
    stats: { players: 2, games: 11, lm_vs_fm: { lm_wins: 6, fm_wins: 3 } },
    recent: [],
  })),
  getEventLeaderboard: vi.fn(() => Promise.resolve({
    event: { event_name: 'Gothic Season 8', elo_mode: 'avatar' },
    leaderboard: [
      { id: '1', entry_id: '1:Pathfinder', name: 'Alice', avatar: 'Pathfinder', event_elo: 1700 },
      { id: '2', entry_id: '2:Sorcerer', name: 'Bob', avatar: 'Sorcerer', event_elo: 1650 },
      { id: '1', entry_id: '1:Seer', name: 'Alice', avatar: 'Seer', event_elo: 1600 },
      { id: '3', entry_id: '3:Pathfinder', name: 'Cara', avatar: 'Pathfinder', event_elo: 1550 },
    ],
  })),
}))

import Home, { bestEntryPerPlayer } from '../Home'

const bodyRows = () => within(screen.getByRole('table')).getAllByRole('row').slice(1)

describe('bestEntryPerPlayer', () => {
  it('keeps each player once, on their first (best) entry', () => {
    const rows = [
      { player: { id: '1', avatar: 'Pathfinder' } },
      { player: { id: 3, avatar: 'Seer' } },
      { player: { id: '1', avatar: 'Avatar of Earth' } },
      { player: { id: '3', avatar: 'Witch' } },
    ]
    expect(bestEntryPerPlayer(rows).map(({ player }) => player.avatar)).toEqual(['Pathfinder', 'Seer'])
  })
})

describe('Home leaderboard Filtered toggle', () => {
  beforeEach(() => localStorage.clear())

  it('shows each player once on their best avatar, with ranks renumbered', async () => {
    renderWithRouter(<Home />)
    const button = await screen.findByRole('button', { name: 'Filtered' })
    expect(bodyRows()).toHaveLength(4)

    fireEvent.click(button)
    expect(button).toHaveAttribute('aria-pressed', 'true')
    const rows = bodyRows()
    expect(rows).toHaveLength(3)
    expect(rows.map((r) => r.textContent)).toEqual([
      expect.stringMatching(/Alice.*Pathfinder.*1700/),
      expect.stringMatching(/Bob.*Sorcerer.*1650/),
      expect.stringMatching(/^III.*Cara.*Pathfinder.*1550/),
    ])
    // The avatar place still counts every Pathfinder entry
    expect(rows[2].textContent).toMatch(/#2 of 2/)
    expect(localStorage.getItem('home_leaderboard_best_only')).toBe('1')
  })
})

describe('Home LM / FM tab', () => {
  beforeEach(() => localStorage.clear())

  it('shows the precon ladder with ranked and not-yet-ranked players', async () => {
    renderWithRouter(<Home />)
    fireEvent.click(await screen.findByRole('button', { name: 'LM / FM' }))
    expect(await screen.findByRole('heading', { level: 2, name: 'LM vs FM 1' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Not yet ranked' })).toBeInTheDocument()
    expect(screen.getByText('Lavamancer 67%')).toBeInTheDocument()
    expect(localStorage.getItem('home_elo_source_preference')).toBe('precon')
  })
})
