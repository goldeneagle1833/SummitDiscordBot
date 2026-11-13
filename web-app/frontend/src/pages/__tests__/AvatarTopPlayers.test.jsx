import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, renderWithRouter, waitFor, within } from '@/test/test-utils'
import userEvent from '@testing-library/user-event'
import AvatarTopPlayers from '../AvatarTopPlayers'
import { getAvatarFilters, getAvatarTopPlayers } from '@/api/cards'
import { getAvatarLeaderboards, getLifetimeAvatarLeaderboards } from '@/api/leaderboard'

vi.mock('@/api/cards', () => ({
  getAvatarFilters: vi.fn(),
  getAvatarTopPlayers: vi.fn(),
}))
vi.mock('@/api/leaderboard', () => ({
  getAvatarLeaderboards: vi.fn(),
  getLifetimeAvatarLeaderboards: vi.fn(),
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
    getLifetimeAvatarLeaderboards.mockResolvedValue({ scope: 'lifetime', avatars: [] })
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
    getLifetimeAvatarLeaderboards.mockResolvedValue({ scope: 'lifetime', avatars: [] })
  })

  it('opens on the avatar from the link, ranked by season Elo', async () => {
    renderWithRouter(<AvatarTopPlayers />, {
      route: '/avatars/top-players?avatar=Avatar%20of%20Air&event=current',
    })

    expect(await screen.findByRole('heading', { name: 'Avatar of Air' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Elo' }).selected).toBe(true)
    expect(screen.getByRole('columnheader', { name: 'Season Elo' })).toBeInTheDocument()
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

  it('has no Elo option in a Player-mode season before lifetime avatar Elo exists', async () => {
    getAvatarLeaderboards.mockResolvedValue({ elo_mode: 'player', avatars: [] })
    renderWithRouter(<AvatarTopPlayers />, { route: '/avatars/top-players?avatar=Witch' })

    expect(await screen.findByRole('columnheader', { name: /avatar score/i })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Elo' })).not.toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Elo ladder' })).not.toBeInTheDocument()
  })
})

const LIFETIME_LADDER = {
  scope: 'lifetime',
  elo_mode: 'avatar',
  avatars: [{
    avatar: 'Avatar of Air',
    players: 2,
    entries: [
      { rank: 1, overall_rank: null, user_id: '22', display_name: 'Ed', elo: 1640, games: 20, wins: 14, losses: 6, provisional: false, provisional_games: 20 },
      { rank: null, overall_rank: null, user_id: '11', display_name: 'Amy', elo: null, games: 3, wins: 2, losses: 1, provisional: true, provisional_games: 3 },
    ],
  }],
}

describe('AvatarTopPlayers lifetime Elo', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getAvatarFilters.mockResolvedValue({ events: SEASONS })
    getAvatarTopPlayers.mockResolvedValue(SCORE_DATA)
    getAvatarLeaderboards.mockResolvedValue(AVATAR_LADDER)
    getLifetimeAvatarLeaderboards.mockResolvedValue(LIFETIME_LADDER)
  })

  it('switches the Elo table between season and lifetime', async () => {
    const user = userEvent.setup()
    renderWithRouter(<AvatarTopPlayers />, {
      route: '/avatars/top-players?avatar=Avatar%20of%20Air',
    })

    expect(await screen.findByRole('columnheader', { name: 'Season Elo' })).toBeInTheDocument()
    const ladder = screen.getByRole('group', { name: 'Elo ladder' })
    expect(within(ladder).getByRole('button', { name: 'Season' })).toHaveAttribute('aria-pressed', 'true')

    await user.click(within(ladder).getByRole('button', { name: 'Lifetime' }))

    expect(await screen.findByRole('columnheader', { name: 'Lifetime Elo' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Lifetime Elo by Avatar' })).toBeInTheDocument()
    const rows = screen.getAllByRole('row').slice(1)
    expect(within(rows[0]).getByRole('link', { name: 'Ed' })).toBeInTheDocument()
    expect(within(rows[0]).getByText('1640')).toBeInTheDocument()
    expect(within(rows[0]).getByText('#1')).toBeInTheDocument()
    // Provisional: no rating, no rank
    expect(within(rows[1]).getByText('Provisional (3/8)')).toBeInTheDocument()
    expect(within(rows[1]).queryByText(/#/)).not.toBeInTheDocument()
  })

  it('offers lifetime Elo in a Player-mode season', async () => {
    getAvatarLeaderboards.mockResolvedValue({ elo_mode: 'player', avatars: [] })
    const user = userEvent.setup()
    renderWithRouter(<AvatarTopPlayers />, {
      route: '/avatars/top-players?avatar=Avatar%20of%20Air',
    })

    // Default stays Avatar Score; Elo opens the lifetime ladder, season disabled
    const sort = (await screen.findByRole('option', { name: 'Elo' })).closest('select')
    expect(screen.getByRole('option', { name: 'Avatar Score' }).selected).toBe(true)
    await user.selectOptions(sort, 'elo')

    expect(await screen.findByRole('columnheader', { name: 'Lifetime Elo' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Season' })).toBeDisabled()
  })
})
