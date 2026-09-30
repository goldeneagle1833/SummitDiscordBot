import { describe, it, expect } from 'vitest'
import { screen, renderWithRouter, within } from '@/test/test-utils'
import LeaderboardTable from '@/components/leaderboard/LeaderboardTable'
import PlayerHeader from '../PlayerHeader'
import AvatarPerformance from '../AvatarPerformance'

// Avatar-mode seasons: one event ELO per player and avatar

const AVATAR_LADDER = [
  { id: '1', entry_id: '1:Imposter', name: 'Alice', avatar: 'Imposter', event_elo: 1600, wins: 3, losses: 0 },
  { id: '2', entry_id: '2:Witch', name: 'Bob', avatar: 'Witch', event_elo: 1570, wins: 2, losses: 1 },
  { id: '1', entry_id: '1:Persecutor', name: 'Alice', avatar: 'Persecutor', event_elo: 1530, wins: 1, losses: 0 },
]

describe('event leaderboard in Avatar mode', () => {
  it('shows an avatar column and one row per player and avatar', () => {
    renderWithRouter(<LeaderboardTable data={AVATAR_LADDER} columns="event" />)
    expect(screen.getByRole('columnheader', { name: /avatar/i })).toBeInTheDocument()
    const rows = screen.getAllByRole('row').slice(1)
    expect(rows).toHaveLength(3)
    expect(within(rows[2]).getByText('Persecutor')).toBeInTheDocument()
    expect(within(rows[2]).getByRole('link', { name: 'Alice' })).toHaveAttribute('href', '/player/1')
  })

  it('has no avatar column in Player mode', () => {
    const playerMode = AVATAR_LADDER.slice(0, 2).map((row) => ({ ...row, avatar: null }))
    renderWithRouter(<LeaderboardTable data={playerMode} columns="event" />)
    expect(screen.queryByRole('columnheader', { name: /avatar/i })).not.toBeInTheDocument()
  })
})

describe('profile in Avatar mode', () => {
  const baseHeader = {
    data: { name: 'Alice' },
    playerId: '1',
    eloText: 'Event ELO per avatar:',
    rankText: '',
    eventFilter: 'current',
    pastEvents: [],
    onEventChange: () => {},
    canSeeLifetime: false,
  }

  it('lists every avatar entry with its ELO and rank', () => {
    renderWithRouter(
      <PlayerHeader
        {...baseHeader}
        avatarEntries={[
          { avatar: 'Imposter', event_elo: 1600, rank: 1 },
          { avatar: 'Persecutor', event_elo: 1530, rank: 3 },
        ]}
      />,
    )
    const list = screen.getByRole('list', { name: /event elo per avatar/i })
    expect(within(list).getAllByRole('listitem')).toHaveLength(2)
    expect(within(list).getByText(/1530 · #3/)).toBeInTheDocument()
  })

  it('no longer offers the Paper ladder toggle', () => {
    renderWithRouter(<PlayerHeader {...baseHeader} data={{ name: 'Alice', has_web_matches: true }} />)
    expect(screen.queryByRole('button', { name: 'Paper' })).not.toBeInTheDocument()
  })

  it('adds event ELO and rank to Avatar Performance', () => {
    renderWithRouter(
      <AvatarPerformance
        open
        onToggle={() => {}}
        playerId="1"
        avatars={[
          { name: 'Imposter', wins: 3, losses: 0, win_rate: 100, event_elo: 1600, event_rank: 1 },
          { name: 'Druid', wins: 0, losses: 1, win_rate: 0, event_elo: null, event_rank: null },
        ]}
      />,
    )
    expect(screen.getByRole('columnheader', { name: /event elo/i })).toBeInTheDocument()
    expect(screen.getByText('#1')).toBeInTheDocument()
  })
})
