import { describe, it, expect, vi } from 'vitest'
import { screen, renderWithRouter, within } from '@/test/test-utils'
import userEvent from '@testing-library/user-event'

vi.mock('@/api/cards', () => ({
  getAvatarImageFiles: vi.fn(() => Promise.resolve([])),
  getAvatars: vi.fn(() => Promise.resolve([{ name: 'Witch', win_rate: 50 }])),
}))

import AvatarPerformance from '../AvatarPerformance'
import AvatarMatchups from '../AvatarMatchups'

describe('Avatars tab', () => {
  it('shows a card per avatar with record, form and the gap to everyone', async () => {
    renderWithRouter(
      <AvatarPerformance
        playerId="1"
        avatars={[
          { name: 'Witch', wins: 6, losses: 2, win_rate: 75, form: ['W', 'L', 'W'], last_played: '2026-10-10 12:00:00', elo_change: 24 },
          { name: 'Druid', wins: 1, losses: 3, win_rate: 25, form: ['L'], last_played: '2026-09-01 12:00:00', elo_change: -10 },
        ]}
      />,
    )
    const cards = screen.getAllByRole('listitem')
    expect(cards).toHaveLength(2)
    expect(within(cards[0]).getByText('6W · 2L')).toBeInTheDocument()
    expect(within(cards[0]).getByLabelText(/Last 3 games/)).toBeInTheDocument()
    expect(await within(cards[0]).findByText('(+25)')).toBeInTheDocument()
    expect(within(cards[0]).getByRole('link')).toHaveAttribute('href', '/player/1/avatar/Witch')
  })
})

describe('Matchups tab', () => {
  const overall = [
    { opponent_avatar: 'Geomancer', wins: 4, losses: 1, win_rate: 80, total_games: 5 },
    { opponent_avatar: 'Sparkmage', wins: 1, losses: 3, win_rate: 25, total_games: 4 },
  ]
  const byAvatar = {
    Witch: [{ opponent_avatar: 'Geomancer', wins: 3, losses: 0, win_rate: 100, total_games: 3 }],
    Druid: [{ opponent_avatar: 'Sparkmage', wins: 0, losses: 3, win_rate: 0, total_games: 3 }],
  }

  it('lists best and toughest matchups and filters by the avatar played', async () => {
    renderWithRouter(<AvatarMatchups matchups={overall} byAvatar={byAvatar} myAvatars={['Witch', 'Druid']} />)
    expect(screen.getByText('vs Geomancer')).toBeInTheDocument()
    expect(screen.getByText('vs Sparkmage')).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Playing as'), 'Witch')
    expect(screen.getByText('vs Geomancer')).toBeInTheDocument()
    expect(screen.queryByText('vs Sparkmage')).not.toBeInTheDocument()
  })
})
