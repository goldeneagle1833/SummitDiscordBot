import { useEffect } from 'react'
import usePageTitle from '@/hooks/usePageTitle'

export default function About() {
  usePageTitle('About')
  useEffect(() => {
  }, [])

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h1 className="text-2xl font-display text-secondary">About Sorcerers Summit</h1>
      <div className="bg-bg-surface border border-border rounded-soft p-6 space-y-4 text-sm leading-relaxed">
        <p>
          Sorcerers Summit is a community-driven platform built for players of Sorcery: Contested Realm.
          Our mission is to bring the community together through competitive matchmaking, stat tracking,
          and deck sharing.
        </p>
        <p>
          Whether you are a seasoned veteran or just getting started, Summit provides tools to help you
          improve your game. Track your ELO rating, analyze your match history, explore top tournament
          decks, and find opponents through our Looking For Game system.
        </p>
        <p>
          The platform includes a Discord bot for in-server matchmaking and game reporting, paired with
          this web application for deeper stats, leaderboards, and deck exploration.
        </p>
        <p className="text-text-muted">
          Built with care by the Sorcerers Summit community.
        </p>
      </div>
    </div>
  )
}
