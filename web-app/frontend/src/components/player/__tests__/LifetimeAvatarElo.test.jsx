import { describe, it, expect } from 'vitest'
import { screen, renderWithRouter, within } from '@/test/test-utils'
import AvatarPerformance from '../AvatarPerformance'

// Lifetime avatar ELO (Glicko-2, Season 9 on) on the profile's Avatars tab

const AVATARS = [
  { name: 'Witch', wins: 9, losses: 3, win_rate: 75 },
  { name: 'Druid', wins: 2, losses: 3, win_rate: 40 },
  { name: 'Sparkmage', wins: 1, losses: 0, win_rate: 100 },
]

describe('AvatarPerformance lifetime avatar ELO', () => {
  it('adds a column with the rating and rank, or the provisional tag', () => {
    renderWithRouter(
      <AvatarPerformance
        playerId="1"
        avatars={AVATARS}
        lifetimeElo={[
          { avatar: 'Witch', elo: 1588, games: 12, rank: 2, provisional: false, provisional_games: 12 },
          { avatar: 'Druid', elo: null, games: 5, rank: null, provisional: true, provisional_games: 5 },
        ]}
      />,
    )
    expect(screen.getByRole('columnheader', { name: 'Lifetime avatar ELO' })).toBeInTheDocument()
    const row = (name) => screen.getByRole('link', { name }).closest('tr')
    expect(within(row('Witch')).getByText('1588')).toBeInTheDocument()
    expect(within(row('Witch')).getByText('· #2')).toBeInTheDocument()
    expect(within(row('Druid')).getByText('Provisional (5/8)')).toBeInTheDocument()
    expect(within(row('Druid')).queryByText(/#/)).not.toBeInTheDocument()
    // No entry on this avatar yet
    expect(within(row('Sparkmage')).getAllByText('-').length).toBeGreaterThan(0)
  })

  it('shows nothing new without lifetime avatar ELO (before Season 9, or hidden)', () => {
    renderWithRouter(<AvatarPerformance playerId="1" avatars={AVATARS} lifetimeElo={[]} />)
    expect(screen.queryByRole('columnheader', { name: 'Lifetime avatar ELO' })).not.toBeInTheDocument()
    renderWithRouter(<AvatarPerformance playerId="1" avatars={AVATARS} />)
    expect(screen.queryByText(/Lifetime avatar ELO/)).not.toBeInTheDocument()
  })
})
