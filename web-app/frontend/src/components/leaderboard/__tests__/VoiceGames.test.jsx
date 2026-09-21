import { describe, it, expect } from 'vitest'
import { screen, renderWithRouter } from '@/test/test-utils'
import LeaderboardTable from '../LeaderboardTable'
import { VoiceRequirementNote } from '../VoiceGames'

const REQUIREMENT = { min_games: 5, enforced: false }
const EVENT_PLAYERS = [
  { id: '1', name: 'Alice', event_elo: 1640, voice_games: 7 },
  { id: '2', name: 'Bob', event_elo: 1580, voice_games: 2 },
]

describe('voice games on the season leaderboard', () => {
  it('shows progress toward the requirement and a check once met', () => {
    renderWithRouter(
      <LeaderboardTable data={EVENT_PLAYERS} columns="event" voiceRequirement={REQUIREMENT} />
    )
    expect(screen.getByText('Voice')).toBeInTheDocument()
    expect(screen.getByText('✓')).toBeInTheDocument()
    expect(screen.getByText('2/5')).toBeInTheDocument()
  })

  it('hides the column without a requirement (archived seasons)', () => {
    renderWithRouter(<LeaderboardTable data={EVENT_PLAYERS} columns="event" />)
    expect(screen.queryByText('Voice')).not.toBeInTheDocument()
    expect(screen.queryByText('2/5')).not.toBeInTheDocument()
  })

  it('announces the requirement for next season until enforced', () => {
    const { rerender } = renderWithRouter(<VoiceRequirementNote requirement={REQUIREMENT} />)
    expect(screen.getByText(/will require 5 starting next season/)).toBeInTheDocument()
    rerender(<VoiceRequirementNote requirement={{ min_games: 5, enforced: true }} />)
    expect(screen.getByText(/Top cut requires 5\./)).toBeInTheDocument()
  })
})
