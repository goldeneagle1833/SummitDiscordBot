import { describe, it, expect, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import RecentDecks from '../RecentDecks'
import { getDeckLinkPreviews } from '@/api/community'

vi.mock('@/api/community', () => ({
  getDeckLinkPreviews: vi.fn(() =>
    Promise.resolve({
      previews: {
        'https://curiosa.io/decks/abc123': {
          title: 'Earth/Fire by Bruce', description: 'A deck', image: 'https://curiosa.io/og.png', site_name: 'Curiosa',
        },
      },
    }),
  ),
}))

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

  it('shows a link preview for the deck when deck links are visible', async () => {
    renderWithRouter(<RecentDecks decks={[baseDeck]} playerId="1" showLinks open />)
    const title = await screen.findByText('Earth/Fire by Bruce')
    expect(title.closest('a')).toHaveAttribute('href', 'https://curiosa.io/decks/abc123')
    expect(getDeckLinkPreviews).toHaveBeenCalledWith(['https://curiosa.io/decks/abc123'])
  })

  it('shows no preview, and fetches none, when deck links are private', () => {
    getDeckLinkPreviews.mockClear()
    renderWithRouter(<RecentDecks decks={[baseDeck]} playerId="1" open />)
    expect(screen.queryByText('Earth/Fire by Bruce')).not.toBeInTheDocument()
    expect(getDeckLinkPreviews).not.toHaveBeenCalled()
  })
})
