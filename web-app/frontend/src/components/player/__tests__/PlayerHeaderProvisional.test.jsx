import { describe, it, expect } from 'vitest'
import { screen, renderWithRouter, within } from '@/test/test-utils'
import PlayerHeader from '../PlayerHeader'

const base = {
  data: { name: 'Alice' },
  playerId: '1',
  eventFilter: 'lifetime',
  pastEvents: [],
  onEventChange: () => {},
  canSeeLifetime: true,
}

describe('PlayerHeader provisional ratings', () => {
  it('shows "Provisional (n/8)" instead of the ELO, with no rank', () => {
    renderWithRouter(
      <PlayerHeader
        {...base}
        headline={{ elo: null, eloLabel: 'Lifetime ELO', rank: null, provisional: { games: 4 } }}
      />,
    )
    expect(screen.getByText('Provisional (4/8)')).toBeInTheDocument()
    expect(screen.getByText('Lifetime ELO')).toBeInTheDocument()
    expect(screen.queryByText(/^#/)).toBeNull()
  })

  it('shows a settled ELO, rank and legacy ELO as numbers', () => {
    renderWithRouter(
      <PlayerHeader
        {...base}
        headline={{ elo: 1612, eloLabel: 'Lifetime ELO', rank: 7, rankLabel: 'Rank', legacyElo: 1580 }}
      />,
    )
    expect(screen.getByText('1612')).toBeInTheDocument()
    expect(screen.getByText('#7')).toBeInTheDocument()
    expect(screen.getByText('1580')).toBeInTheDocument()
    expect(screen.getByText('Legacy ELO (Seasons 1-8)')).toBeInTheDocument()
    expect(screen.queryByTestId('provisional-tag')).toBeNull()
  })

  it('shows legacy ELO next to a provisional lifetime rating', () => {
    renderWithRouter(
      <PlayerHeader
        {...base}
        headline={{ elo: null, eloLabel: 'Lifetime ELO', provisional: { games: 1 }, legacyElo: 1544 }}
      />,
    )
    expect(screen.getByText('Provisional (1/8)')).toBeInTheDocument()
    expect(screen.getByText('1544')).toBeInTheDocument()
  })

  it('hides legacy ELO when the player has none', () => {
    renderWithRouter(<PlayerHeader {...base} headline={{ elo: 1500, eloLabel: 'Lifetime ELO', legacyElo: null }} />)
    expect(screen.queryByText('Legacy ELO (Seasons 1-8)')).toBeNull()
  })

  it('tags provisional avatar entries and drops their rank', () => {
    renderWithRouter(
      <PlayerHeader
        {...base}
        eventFilter="current"
        avatarEntries={[
          { avatar: 'Imposter', event_elo: 1600, rank: 1 },
          { avatar: 'Witch', event_elo: null, rank: null, provisional: true, provisional_games: 3 },
        ]}
      />,
    )
    const list = screen.getByRole('list', { name: /event elo per avatar/i })
    const [imposter, witch] = within(list).getAllByRole('listitem')
    expect(imposter).toHaveTextContent('1600 · #1')
    expect(witch).toHaveTextContent('Provisional (3/8)')
    expect(witch).not.toHaveTextContent('#')
    expect(witch).not.toHaveTextContent('null')
  })
})
