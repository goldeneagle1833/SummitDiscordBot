import { describe, it, expect } from 'vitest'
import { screen, within } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import { PreconMatchHistory, PreconStandings, filterPreconGames, withPreconFilters } from '../PlayerPrecon'

const DATA = {
  min_ranked_games: 5,
  seasons: [{
    season: {
      season_id: 2, name: 'LM vs FM 1', starts_at: '2026-11-12T18:00:00',
      ends_at: '2099-12-10T18:00:00', last_day: '2099-12-10T18:00:00', is_open: true,
    },
    standing: { rating: 1588, rank: 3, ranked: true, games: 8, wins: 6, losses: 2,
      lm_wins: 4, lm_losses: 1, fm_wins: 2, fm_losses: 1 },
    ranked_players: 12,
  }],
  games: [
    { match_id: 41, won: true, precon: 'lavamancer', opponent_id: '9', opponent_name: 'Bob',
      opponent_precon: 'frostmage', rating_before: 1560, rating_after: 1588, went_first: 'y',
      replay_url: 'https://playsorceryonline.com/replay/abc', timestamp: '2026-11-13T19:00:00' },
    { match_id: 40, won: false, precon: 'frostmage', opponent_id: '7', opponent_name: 'Cara',
      opponent_precon: 'frostmage', rating_before: 1580, rating_after: 1560, went_first: 'n',
      replay_url: null, timestamp: '2026-11-13T18:00:00' },
  ],
}

describe('PlayerPrecon', () => {
  it('shows the ladder rating, rank and per-precon records', () => {
    renderWithRouter(<PreconStandings data={DATA} />)
    expect(screen.getByRole('link', { name: 'LM vs FM 1' })).toHaveAttribute('href', '/elo?board=precon:2')
    expect(screen.getByText('1588')).toBeInTheDocument()
    expect(screen.getByText('#3')).toBeInTheDocument()
    expect(screen.getByText('of 12')).toBeInTheDocument()
    expect(screen.getByText('LM 4-1')).toBeInTheDocument()
  })

  it('lists precon games with the PSO replay link when there is one', () => {
    renderWithRouter(<PreconMatchHistory data={DATA} />)
    const rows = within(screen.getByRole('table')).getAllByRole('row').slice(1)
    expect(rows[0]).toHaveTextContent(/P41.*Win.*LM.*Bob.*FM.*\+28.*Watch.*Play/)
    expect(within(rows[0]).getByRole('link', { name: 'Watch' })).toHaveAttribute('href', 'https://playsorceryonline.com/replay/abc')
    expect(rows[1]).toHaveTextContent(/P40.*Loss.*-20/)
    expect(within(rows[1]).queryByRole('link', { name: 'Watch' })).toBeNull()
  })

  it('renders nothing for a player with no precon games', () => {
    const { container } = renderWithRouter(<PreconMatchHistory data={{ games: [] }} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('adds Lavamancer, Frostmage and precon opponents to the Matches tab filters', () => {
    const base = {
      options: { opponents: [{ id: '9', name: 'Bob', games: 3 }], avatars: ['Witch'], opponent_avatars: ['Seer'] },
      ranked: { wins: 1, losses: 0 }, casual: { wins: 0, losses: 0 },
    }
    const out = withPreconFilters(base, DATA, {})
    expect(out.options.avatars).toEqual(['Frostmage', 'Lavamancer', 'Witch'])
    expect(out.options.opponent_avatars).toEqual(['Frostmage', 'Seer'])
    expect(out.options.opponents).toEqual([
      { id: '9', name: 'Bob', games: 4 },
      { id: '7', name: 'Cara', games: 1 },
    ])
    expect(out.precon).toEqual({ wins: 1, losses: 1 })
    expect(base.options.opponents[0].games).toBe(3)
  })

  it('leaves the filters alone for a player with no precon games', () => {
    const base = { options: { avatars: ['Witch'] } }
    expect(withPreconFilters(base, { games: [] }, {})).toBe(base)
  })

  it('filters precon games by avatar, opponent avatar, opponent, result and play/draw', () => {
    const ids = (f) => filterPreconGames(DATA.games, f).map((g) => g.match_id)
    expect(ids({})).toEqual([41, 40])
    expect(ids({ avatar: 'Lavamancer' })).toEqual([41])
    expect(ids({ opponent_avatar: 'Frostmage', result: 'loss' })).toEqual([40])
    expect(ids({ opponent: '9' })).toEqual([41])
    expect(ids({ play_draw: 'draw' })).toEqual([40])
    expect(ids({ avatar: 'Witch' })).toEqual([])
    expect(ids({ card: 'Fireball' })).toEqual([])
  })

  it('says so when no precon games fit the filters', () => {
    renderWithRouter(<PreconMatchHistory data={DATA} filters={{ avatar: 'Witch' }} />)
    expect(screen.getByText('No precon games fit these filters.')).toBeInTheDocument()
    expect(screen.queryByRole('table')).toBeNull()
  })
})
