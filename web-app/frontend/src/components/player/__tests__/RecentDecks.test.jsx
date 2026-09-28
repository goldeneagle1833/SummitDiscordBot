import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import RecentDecks from '../RecentDecks'

const baseDeck = {
  url: 'https://curiosa.io/decks/abc123',
  avatar: 'Sorcerer',
  deck_name: 'Earth/Fire',
  wins: 21,
  losses: 5,
  win_rate: 80.8,
  total_games: 26,
}

describe('RecentDecks', () => {
  it('shows season and lifetime ELO impact for a deck', () => {
    renderWithRouter(
      <RecentDecks
        decks={[{ ...baseDeck, elo_season: 42, elo_lifetime: -7, season_wins: 21, season_losses: 5 }]}
        playerId="111"
        open
        onToggle={() => {}}
      />,
    )

    const line = screen.getByText(/^ELO:/).textContent
    expect(line).toContain('Season +42 (21-5)')
    expect(line).toContain('Lifetime -7')
  })

  it('omits the season figure when no season window applies', () => {
    renderWithRouter(
      <RecentDecks
        decks={[{ ...baseDeck, elo_season: null, elo_lifetime: 13, season_wins: 0, season_losses: 0 }]}
        playerId="111"
        open
        onToggle={() => {}}
      />,
    )

    const line = screen.getByText(/^ELO:/).textContent
    expect(line).not.toContain('Season')
    expect(line).toContain('Lifetime +13')
  })

  it('renders decks without ELO fields unchanged', () => {
    renderWithRouter(<RecentDecks decks={[baseDeck]} playerId="111" open onToggle={() => {}} />)

    expect(screen.getByText('Earth/Fire')).toBeInTheDocument()
    expect(screen.queryByText(/^ELO:/)).not.toBeInTheDocument()
  })
})
