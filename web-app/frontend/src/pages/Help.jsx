import { useEffect } from 'react'
import usePageTitle from '@/hooks/usePageTitle'

export default function Help() {
  usePageTitle('Help')
  useEffect(() => {
  }, [])

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h1 className="text-2xl font-display text-secondary">Help</h1>

      <div className="bg-bg-surface border border-border rounded-soft p-6 space-y-4">
        <h2 className="text-lg font-semibold">Bot Commands</h2>
        <div className="space-y-3 text-sm">
          <div>
            <p className="font-medium text-primary">!lfg / /lfg</p>
            <p className="text-text-muted">Join the Looking For Game queue to find an opponent.</p>
          </div>
          <div>
            <p className="font-medium text-primary">!stats / /stats</p>
            <p className="text-text-muted">View your ELO rating, win/loss record, and match history.</p>
          </div>
          <div>
            <p className="font-medium text-primary">!leaderboard / /leaderboard</p>
            <p className="text-text-muted">View the current ELO leaderboard.</p>
          </div>
          <div>
            <p className="font-medium text-primary">!deck / /deck</p>
            <p className="text-text-muted">Check deck information using a Curiosa deck link.</p>
          </div>
        </div>
      </div>

      <div className="bg-bg-surface border border-border rounded-soft p-6 space-y-4">
        <h2 className="text-lg font-semibold">Website Features</h2>
        <div className="space-y-3 text-sm">
          <div>
            <p className="font-medium">Leaderboard</p>
            <p className="text-text-muted">Browse event and limited leaderboards.</p>
          </div>
          <div>
            <p className="font-medium">Events & Decks</p>
            <p className="text-text-muted">Explore top 8 decks from past tournaments.</p>
          </div>
          <div>
            <p className="font-medium">Player Profiles</p>
            <p className="text-text-muted">View detailed stats and match history for any player.</p>
          </div>
          <div>
            <p className="font-medium">Cards & Avatars</p>
            <p className="text-text-muted">Browse card and avatar performance data across all matches.</p>
          </div>
        </div>
      </div>
    </div>
  )
}
