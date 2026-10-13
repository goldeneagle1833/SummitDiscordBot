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
