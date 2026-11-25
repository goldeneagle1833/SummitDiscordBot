import { describe, it, expect } from 'vitest'
import { screen, within } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import LimitedArena from '../LimitedArena'

const limitedMatch = (overrides = {}) => ({
  match_id: 1182,
  result: 'Win',
  match_type: 'limited',
  opponent: 'Vorona',
  opponent_id: '200',
  elo_change: 17,
  date: '2026-11-24T12:00:00',
  match_time: 26,
  first_player: 'Play',
  player_avatar: 'Sparkmage',
  deck_elements: ['Fire'],
  opponent_avatar: 'Geomancer',
  opponent_elements: ['Earth'],
  player_deck_url: 'https://curiosa.io/decks/mine',
  has_deck_json: true,
  match_comment: null,
  match_source: 'limited',
  ...overrides,
})

const limited = (matches) => ({
  has_data: true,
  elo: 1407,
  total_wins: 54,
  total_losses: 48,
  win_rate: 52.9,
  arena_runs: [{ run_id: 1, wins: 1, losses: 0, deck_url: 'https://curiosa.io/decks/mine', status: 'active', starting_elo: 1464, created_at: '2026-11-24' }],
  recent_matches: matches,
})

describe('LimitedArena recent matches', () => {
  it('shows the owner the same details as Match History, without replay or change result', () => {
    renderWithRouter(<LimitedArena limited={limited([limitedMatch()])} playerId="100" isOwner open />)
    // Arena Runs table is still there
    expect(screen.getByRole('heading', { name: 'Arena Runs' })).toBeInTheDocument()
    const headers = screen.getAllByRole('columnheader').map((th) => th.textContent)
    expect(headers).toEqual(expect.arrayContaining(['Result', 'Type', 'Avatar', 'Opponent', 'Rating', 'Play/Draw', 'Date', 'Deck', 'Notes']))
    expect(headers).not.toContain('Replay')
    expect(headers).not.toContain('Change Result')
    const row = screen.getByText('Vorona').closest('tr')
    expect(within(row).getByText('Limited')).toBeInTheDocument()
    expect(within(row).getByRole('link', { name: 'Sparkmage' })).toBeInTheDocument()
    expect(within(row).getByRole('link', { name: 'Geomancer' })).toBeInTheDocument()
    expect(within(row).getByText('Play')).toBeInTheDocument()
    expect(within(row).getByRole('button', { name: '26 min' })).toBeInTheDocument()
    expect(within(row).getByRole('button', { name: '+ Note' })).toBeInTheDocument()
    expect(within(row).getByRole('link', { name: 'Snapshot' })).toHaveAttribute('href', '/deck-snapshot/1182/100?mode=limited')
    expect(within(row).queryByRole('img', { name: /voice/i })).not.toBeInTheDocument()
  })

  it('keeps archived games read-only', () => {
    renderWithRouter(
      <LimitedArena limited={limited([limitedMatch({ match_source: null, archived: true, has_deck_json: false })])} playerId="100" isOwner open />
    )
    const row = screen.getByText('Vorona').closest('tr')
    expect(within(row).queryByRole('button', { name: '26 min' })).not.toBeInTheDocument()
    expect(within(row).getByText('26 min')).toBeInTheDocument()
    expect(within(row).queryByRole('button', { name: '+ Note' })).not.toBeInTheDocument()
  })

  it('hides deck links and owner-only parts from visitors when the profile keeps them private', () => {
    renderWithRouter(
      <LimitedArena limited={limited([limitedMatch({ player_deck_url: null, has_deck_json: false, match_source: null })])} playerId="100" profileVisibility={{}} open />
    )
    const headers = screen.getAllByRole('columnheader').map((th) => th.textContent)
    expect(headers).not.toContain('Notes')
    expect(headers).not.toContain('Avatar')
    expect(screen.queryByRole('link', { name: 'Snapshot' })).not.toBeInTheDocument()
  })
})
