import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, renderWithRouter, waitFor, within } from '@/test/test-utils'
import AvatarTopPlayers from '../AvatarTopPlayers'
import { getAvatarFilters, getAvatarTopPlayers } from '@/api/cards'
import { getAvatarLeaderboards } from '@/api/leaderboard'

vi.mock('@/api/cards', () => ({
  getAvatarFilters: vi.fn(),
  getAvatarTopPlayers: vi.fn(),
}))
vi.mock('@/api/leaderboard', () => ({
  getAvatarLeaderboards: vi.fn(),
}))

const SEASONS = [
  { event_id: 1, event_name: 'Alpha Season', is_active: false },
  { event_id: 3, event_name: 'Summit Gothic Season 4', is_active: true },
]

const AVATAR_LADDER = {
  elo_mode: 'avatar',
  avatars: [
    {
      avatar: 'Avatar of Air',
      players: 2,
      entries: [
        { rank: 1, overall_rank: 4, user_id: '11', display_name: 'Amy', elo: 1588, games: 9, wins: 7, losses: 2 },
        { rank: 2, overall_rank: 15, user_id: '22', display_name: 'Ed', elo: 1501, games: 2, wins: 1, losses: 1 },
      ],
    },
    {
      avatar: 'Witch',
      players: 1,
      entries: [{ rank: 1, overall_rank: 2, user_id: '33', display_name: 'Sam', elo: 1610, games: 12, wins: 9, losses: 3 }],
    },
  ],
}

// Avatar Score data only has Witch: nobody is past 10 games on Avatar of Air yet
const SCORE_DATA = {
  avatars: [{
    name: 'Witch', wins: 9, losses: 3, win_rate: 75, avatar_score: 700,
    players: [{ player_id: '33', name: 'Sam', avatar_score: 700, wins: 9, losses: 3, win_rate: 75, total: 12 }],
  }],
}

describe('AvatarTopPlayers season filter', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getAvatarTopPlayers.mockResolvedValue({ avatars: [] })
    getAvatarLeaderboards.mockResolvedValue({ elo_mode: 'player', avatars: [] })
  })

  it('opens on the running season, listed first', async () => {
    getAvatarFilters.mockResolvedValue({ events: SEASONS })
    renderWithRouter(<AvatarTopPlayers />)

    const season = await screen.findByRole('option', { name: 'Summit Gothic Season 4 (current)' })
    expect(season.selected).toBe(true)
    expect(getAvatarFilters).toHaveBeenCalledWith({ include_active: 1 })
    expect(getAvatarTopPlayers).toHaveBeenCalledWith(expect.objectContaining({ event: 'current' }))
    const options = screen.getAllByRole('option').map((o) => o.textContent)
    expect(options.indexOf('Summit Gothic Season 4 (current)')).toBeLessThan(options.indexOf('Alpha Season'))
  })

  it('falls back to all seasons between seasons', async () => {
    getAvatarFilters.mockResolvedValue({ events: [SEASONS[0]] })
    renderWithRouter(<AvatarTopPlayers />)

    await waitFor(() =>
      expect(getAvatarTopPlayers).toHaveBeenLastCalledWith(expect.objectContaining({ event: 'all' })),
    )
    expect(screen.getByRole('option', { name: 'All Seasons' }).selected).toBe(true)
  })
})

describe('AvatarTopPlayers season Elo', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getAvatarFilters.mockResolvedValue({ events: SEASONS })
    getAvatarTopPlayers.mockResolvedValue(SCORE_DATA)
    getAvatarLeaderboards.mockResolvedValue(AVATAR_LADDER)
  })

  it('opens on the avatar from the link, ranked by season Elo', async () => {
    renderWithRouter(<AvatarTopPlayers />, {
      route: '/avatars/top-players?avatar=Avatar%20of%20Air&event=current',
    })

    expect(await screen.findByRole('heading', { name: 'Avatar of Air' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Season Elo' }).selected).toBe(true)
    expect(screen.getByText('2 players rated on Avatar of Air this season')).toBeInTheDocument()
    const rows = screen.getAllByRole('row').slice(1)
    expect(within(rows[0]).getByRole('link', { name: 'Amy' })).toHaveAttribute('href', '/player/11')
    expect(within(rows[0]).getByText('1588')).toBeInTheDocument()
    expect(within(rows[1]).getByText('#2')).toBeInTheDocument()
  })

  it('switches back to Avatar Score', async () => {
    renderWithRouter(<AvatarTopPlayers />, {
      route: '/avatars/top-players?avatar=Witch&event=current&sort=avatar_score',
    })

    expect(await screen.findByRole('columnheader', { name: /avatar score/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Avatar Score' }).selected).toBe(true)
  })

  it('has no Season Elo option in a Player-mode season', async () => {
    getAvatarLeaderboards.mockResolvedValue({ elo_mode: 'player', avatars: [] })
    renderWithRouter(<AvatarTopPlayers />, { route: '/avatars/top-players?avatar=Witch' })

    expect(await screen.findByRole('columnheader', { name: /avatar score/i })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Season Elo' })).not.toBeInTheDocument()
  })
})
