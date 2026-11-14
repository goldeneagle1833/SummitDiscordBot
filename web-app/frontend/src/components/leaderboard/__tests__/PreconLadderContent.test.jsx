import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import { PreconLadder } from '../PreconLadderContent'

const season = { season_id: 1, name: 'LM vs FM 1', starts_at: '2026-11-01T00:00:00', ends_at: '2099-01-01T00:00:00', is_open: true }

describe('PreconLadder stats', () => {
  it('shows only Players and Games tiles, plus the LM / FM split bar', () => {
    renderWithRouter(<PreconLadder data={{
      season, standings: [], recent: [], min_ranked_games: 5,
      stats: { players: 30, games: 34, lm_vs_fm: { lm_wins: 12, fm_wins: 14, lm_mirrors: 5, fm_mirrors: 3, no_precon: 0 } },
    }} />)
    expect(screen.getByText('Players').previousSibling).toHaveTextContent('30')
    expect(screen.getByText('Games').previousSibling).toHaveTextContent('34')
    expect(screen.queryByText('LM wins vs FM')).not.toBeInTheDocument()
    expect(screen.queryByText('FM wins vs LM')).not.toBeInTheDocument()
    expect(screen.queryByText('Mirror games')).not.toBeInTheDocument()
    expect(screen.getByText(/Lavamancer 46%/)).toBeInTheDocument()
  })
})
