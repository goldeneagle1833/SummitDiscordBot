import { describe, it, expect, vi } from 'vitest'
import { screen, renderWithRouter, within } from '@/test/test-utils'
import userEvent from '@testing-library/user-event'

vi.mock('@/api/players', () => ({
  setHiddenAvatars: vi.fn((id, avatars) => Promise.resolve({ success: true, avatars })),
}))

vi.mock('@/api/cards', () => ({
  getAvatarImageFiles: vi.fn(() => Promise.resolve([])),
  getAvatars: vi.fn(() => Promise.resolve([{ name: 'Witch', win_rate: 50 }])),
}))

import AvatarPerformance from '../AvatarPerformance'
import AvatarMatchups from '../AvatarMatchups'
import { setHiddenAvatars } from '@/api/players'
import { getAvatars } from '@/api/cards'

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
    const cards = within(screen.getAllByRole('list')[0]).getAllByRole('listitem')
    expect(cards).toHaveLength(2)
    expect(within(cards[0]).getByText('6W · 2L')).toBeInTheDocument()
    expect(within(cards[0]).getByLabelText(/Last 3 games/)).toBeInTheDocument()
    expect(await within(cards[0]).findByText('(+25)')).toBeInTheDocument()
    expect(within(cards[0]).getByRole('link')).toHaveAttribute('href', '/player/1/avatar/Witch')
  })
})

describe('Everyone win rate follows the period', () => {
  const avatars = [{ name: 'Witch', wins: 6, losses: 2, win_rate: 75, form: [] }]

  it('uses the same past event as the profile', async () => {
    renderWithRouter(<AvatarPerformance playerId="1" avatars={avatars} period="12" />)
    expect(await screen.findByText(/^Everyone 50%/)).toBeInTheDocument()
    expect(getAvatars).toHaveBeenLastCalledWith({ source: 'discord', event: '12' })
  })

  it('says all events when the running event is private to admins', async () => {
    renderWithRouter(<AvatarPerformance playerId="1" avatars={avatars} period="current" />)
    expect(await screen.findByText(/Everyone \(all events\) 50%/)).toBeInTheDocument()
    expect(getAvatars).toHaveBeenLastCalledWith({ source: 'discord' })
  })
})

describe('hiding avatars', () => {
  const avatars = [
    { name: 'Witch', wins: 6, losses: 2, win_rate: 75, form: [], hidden: false },
    { name: 'Druid', wins: 1, losses: 3, win_rate: 25, form: [], hidden: true },
  ]

  it('lets the owner hide and show avatars without touching the games', async () => {
    const onHiddenChange = vi.fn()
    renderWithRouter(<AvatarPerformance playerId="1" avatars={avatars} canEdit onHiddenChange={onHiddenChange} />)
    expect(screen.queryByText('vs Druid')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /hidden from your profile/i })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Hide Witch from my profile' }))
    expect(setHiddenAvatars).toHaveBeenLastCalledWith('1', ['Druid', 'Witch'])
    expect(onHiddenChange).toHaveBeenLastCalledWith(['Druid', 'Witch'])

    await userEvent.click(screen.getByRole('button', { name: 'Show Druid on my profile' }))
    expect(setHiddenAvatars).toHaveBeenLastCalledWith('1', [])
  })

  it('shows no hide controls to visitors', () => {
    renderWithRouter(<AvatarPerformance playerId="1" avatars={avatars.filter((a) => !a.hidden)} />)
    expect(screen.queryByRole('button', { name: /hide/i })).not.toBeInTheDocument()
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
    expect(screen.getByRole('cell', { name: 'Sparkmage' })).toBeInTheDocument() // full list at the bottom

    await userEvent.selectOptions(screen.getByLabelText('Playing as'), 'Witch')
    expect(screen.getByText('vs Geomancer')).toBeInTheDocument()
    expect(screen.queryByText('vs Sparkmage')).not.toBeInTheDocument()
    expect(screen.queryByRole('cell', { name: 'Sparkmage' })).not.toBeInTheDocument()
  })
})
