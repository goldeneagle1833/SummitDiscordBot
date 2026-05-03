import { describe, it, expect } from 'vitest'
import { screen, renderWithRouter, within } from '@/test/test-utils'
import LeaderboardTable from '../LeaderboardTable'

const MOCK_PLAYERS = [
  { id: '1', name: 'Alice', elo: 1800, wins: 20, losses: 5, primary_mode: 'Online' },
  { id: '2', name: 'Bob', elo: 1650, wins: 15, losses: 10, primary_mode: 'Paper' },
  { id: '3', name: 'Charlie', elo: 1500, wins: 8, losses: 8, primary_mode: 'Online' },
]

describe('LeaderboardTable', () => {
  it('renders "No data available" when data is empty', () => {
    renderWithRouter(<LeaderboardTable data={[]} />)
    expect(screen.getByText(/no data available/i)).toBeInTheDocument()
  })

  it('renders player names as links to their profile', () => {
    renderWithRouter(<LeaderboardTable data={MOCK_PLAYERS} />)
    const link = screen.getByRole('link', { name: 'Alice' })
    expect(link).toHaveAttribute('href', '/player/1')
  })

  it('renders medals for top 3 players', () => {
    renderWithRouter(<LeaderboardTable data={MOCK_PLAYERS} />)
    // Medals are unicode chars in table cells
    expect(screen.getByText('\u{1F947}')).toBeInTheDocument() // gold
    expect(screen.getByText('\u{1F948}')).toBeInTheDocument() // silver
    expect(screen.getByText('\u{1F949}')).toBeInTheDocument() // bronze
  })

  it('calculates win percentage correctly', () => {
    renderWithRouter(<LeaderboardTable data={MOCK_PLAYERS} columns="lifetime" />)
    // Alice: 20/(20+5) = 80.0%
    expect(screen.getByText('80.0%')).toBeInTheDocument()
    // Bob: 15/(15+10) = 60.0%
    expect(screen.getByText('60.0%')).toBeInTheDocument()
  })

  it('renders a "Show" dropdown to control visible rows', () => {
    renderWithRouter(<LeaderboardTable data={MOCK_PLAYERS} />)
    const select = screen.getByRole('combobox')
    expect(select).toBeInTheDocument()
  })

  it('renders event ELO column when columns="event"', () => {
    const eventData = [{ id: '1', name: 'Alice', event_elo: 1600 }]
    renderWithRouter(<LeaderboardTable data={eventData} columns="event" />)
    expect(screen.getByText('Event ELO')).toBeInTheDocument()
    expect(screen.getByText('1600')).toBeInTheDocument()
  })

  it('uses display_name as fallback for name', () => {
    const data = [{ user_id: '99', display_name: 'DisplayUser', elo: 1500, wins: 1, losses: 0 }]
    renderWithRouter(<LeaderboardTable data={data} />)
    expect(screen.getByText('DisplayUser')).toBeInTheDocument()
  })
})
