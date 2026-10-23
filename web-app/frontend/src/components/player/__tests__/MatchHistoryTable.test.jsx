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

  it('shows the voice emojis for voice, no-voice and untracked matches', () => {
    renderWithRouter(
      <MatchHistoryTable
        title="Ranked Match History"
        matches={[match(1, true), match(2, false), match(3, undefined)]}
        isOwner={false}
      />
    )
    const rows = screen.getAllByRole('row').slice(1)
    expect(within(rows[0]).getByRole('img', { name: 'Voice' })).toHaveTextContent('🔊')
    expect(within(rows[1]).getByRole('img', { name: 'No voice' })).toHaveTextContent('🔇')
    expect(within(rows[2]).queryByRole('img')).not.toBeInTheDocument()
  })
})

describe('MatchHistoryTable replay column', () => {
  it('links to the replay when the match has one', () => {
    const replay = 'https://playsorceryonline.com/replay/abc123'
    renderWithRouter(
      <MatchHistoryTable
        title="Ranked Match History"
        matches={[{ ...match(1, true), replay_url: replay }, match(2, true)]}
        isOwner={false}
      />
    )
    expect(screen.getByRole('columnheader', { name: 'Replay' })).toBeInTheDocument()
    const rows = screen.getAllByRole('row').slice(1)
    expect(within(rows[0]).getByRole('link', { name: 'Watch' })).toHaveAttribute('href', replay)
    expect(within(rows[1]).queryByRole('link', { name: 'Watch' })).not.toBeInTheDocument()
  })
})

describe('MatchHistoryTable column order', () => {
  const headers = () => screen.getAllByRole('columnheader').map((th) => th.textContent)

  it('puts Replay between ELO and Play/Draw for visitors', () => {
    renderWithRouter(
      <MatchHistoryTable title="Ranked Match History" matches={[match(1, true)]} isOwner={false} />
    )
    expect(headers()).toEqual(['ID', 'Result', 'Type', 'Voice', 'Opponent', 'ELO', 'Replay', 'Play/Draw', 'Time', 'Date'])
  })

  it('puts Notes last for the owner', () => {
    renderWithRouter(
      <MatchHistoryTable title="Ranked Match History" matches={[match(1, true)]} isOwner />
    )
    const h = headers()
    expect(h.indexOf('Replay')).toBe(h.indexOf('ELO') + 1)
    expect(h.indexOf('Play/Draw')).toBe(h.indexOf('Replay') + 1)
    expect(h[h.length - 1]).toBe('Notes')
  })
})
