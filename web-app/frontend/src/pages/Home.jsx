import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getEvents } from '@/api/events'
import usePageTitle from '@/hooks/usePageTitle'

export default function Home() {
  usePageTitle('Home')
  const [featuredEvent, setFeaturedEvent] = useState(null)

  useEffect(() => {
    getEvents()
      .then((events) => {
        if (events.length > 0) setFeaturedEvent(events[0])
      })
      .catch(() => {})
  }, [])

  return (
    <div className="space-y-8">
      <div className="text-center py-12">
        <h1 className="text-4xl font-display text-secondary mb-4">Sorcerers Summit</h1>
        <p className="text-text-muted text-lg max-w-2xl mx-auto">
          The community hub for Sorcery: Contested Realm. Track your ELO, explore decks, view leaderboards, and connect with fellow sorcerers.
        </p>
        <div className="flex justify-center gap-4 mt-6">
          <Link
            to="/leaderboard"
            className="px-5 py-2 bg-primary text-white rounded-soft font-medium hover:bg-primary-light transition-colors"
          >
            Leaderboard
          </Link>
          <Link
            to="/matches"
            className="px-5 py-2 bg-bg-surface border border-border rounded-soft font-medium hover:border-primary/50 transition-colors"
          >
            Matches
          </Link>
        </div>
      </div>

      {featuredEvent && (
        <div className="bg-bg-surface border border-border rounded-soft p-6">
          <h2 className="text-lg font-display text-secondary mb-2">Featured Event</h2>
          <Link
            to={`/top-8/${featuredEvent.folder}`}
            className="text-primary hover:text-primary-light font-medium"
          >
            {featuredEvent.display_name || featuredEvent.folder}
          </Link>
          <p className="text-sm text-text-muted mt-1">
            {featuredEvent.top8?.length || 0} top 8 decks
            {featuredEvent.all_decks?.length ? ` and ${featuredEvent.all_decks.length} total decks` : ''}
          </p>
        </div>
      )}
    </div>
  )
}
