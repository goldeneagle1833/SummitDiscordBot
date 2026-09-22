import { describe, it, expect } from 'vitest'
import { screen, within } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import MatchHistoryTable from '../MatchHistoryTable'

const match = (id, voice) => ({
  match_id: id,
  result: 'Win',
  match_type: 'ranked',
  opponent: `Opp ${id}`,
  opponent_id: `${id}`,
  elo_change: 12,
  date: '2026-09-21T12:00:00',
  voice,
})

describe('MatchHistoryTable voice column', () => {
  it('shows the Voice column to visitors, not just the owner', () => {
    renderWithRouter(
      <MatchHistoryTable title="Ranked Match History" matches={[match(1, true)]} isOwner={false} />
    )
    expect(screen.getByRole('columnheader', { name: 'Voice' })).toBeInTheDocument()
  })

  it('labels voice, no-voice and untracked matches', () => {
    renderWithRouter(
      <MatchHistoryTable
        title="Ranked Match History"
        matches={[match(1, true), match(2, false), match(3, undefined)]}
        isOwner={false}
      />
    )
    const rows = screen.getAllByRole('row').slice(1)
    expect(within(rows[0]).getByText('Voice')).toBeInTheDocument()
    expect(within(rows[1]).getByText('No voice')).toBeInTheDocument()
    expect(within(rows[2]).queryByText(/voice/i)).not.toBeInTheDocument()
  })
})
