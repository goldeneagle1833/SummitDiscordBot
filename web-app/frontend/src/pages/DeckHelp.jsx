import { useEffect } from 'react'
import usePageTitle from '@/hooks/usePageTitle'

export default function DeckHelp() {
  usePageTitle('Deck Help')
  useEffect(() => {
  }, [])

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h1 className="text-2xl font-display text-secondary">Deck Help</h1>
      <div className="bg-bg-surface border border-border rounded-soft p-6 space-y-4 text-sm leading-relaxed">
        <h2 className="text-lg font-semibold">Building Your Deck</h2>
        <p className="text-text-muted">
          A standard Sorcery: Contested Realm deck consists of an avatar and a deck of spells, minions,
          and other cards. Use the Curiosa deck builder to create and share your decks.
        </p>

        <h2 className="text-lg font-semibold pt-2">Submitting Decks</h2>
        <p className="text-text-muted">
          When reporting a match through the Summit bot, you can include your Curiosa deck link. This
          allows us to track card and avatar performance across all matches.
        </p>

        <h2 className="text-lg font-semibold pt-2">Checking a Deck</h2>
        <p className="text-text-muted">
          Use the <span className="text-primary font-medium">!deck</span> or <span className="text-primary font-medium">/deck</span> command
          with a Curiosa deck link to view the deck contents, card breakdown, and element distribution.
        </p>

        <h2 className="text-lg font-semibold pt-2">Browsing Top Decks</h2>
        <p className="text-text-muted">
          Visit the Events page to explore top 8 decks from past tournaments. You can view full decklists,
          avatar choices, and element distributions for each event.
        </p>
      </div>
    </div>
  )
}
