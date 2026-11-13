import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import { PreconLadder } from '../PreconLadderContent'

const season = { season_id: 1, name: 'LM vs FM 1', starts_at: '2026-11-01T00:00:00', ends_at: '2099-01-01T00:00:00', is_open: true }

describe('PreconLadder stats', () => {
  it('shows mirror games so the tiles add up to the games total', () => {
    renderWithRouter(<PreconLadder data={{
      season, standings: [], recent: [], min_ranked_games: 5,
      stats: { players: 6, games: 22, lm_vs_fm: { lm_wins: 8, fm_wins: 6, lm_mirrors: 5, fm_mirrors: 3, no_precon: 0 } },
    }} />)
    expect(screen.getByText('Mirror games').previousSibling).toHaveTextContent('8')
    expect(screen.getByText(/LM vs LM 5, FM vs FM 3/)).toBeInTheDocument()
    expect(screen.queryByText(/no precon recorded/)).not.toBeInTheDocument()
  })
})
