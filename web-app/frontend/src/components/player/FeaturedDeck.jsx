import { useEffect, useState } from 'react'
import DeckVisualizer from '@/components/deck/DeckVisualizer'
import { getFeaturedDeck } from '@/api/players'
import { getDeckSourceLabel } from '@/utils/deckLinks'

/**
 * The deck shown off on a player's profile: one they pasted, or by default
 * their most-played deck that is public on sorcerytcg.com or Sorcery Online.
 * Visitors see nothing when there is none; the owner gets a prompt.
 */
export default function FeaturedDeck({ playerId, isOwner, onEdit, refreshKey = 0, onLoaded }) {
  const [deck, setDeck] = useState(undefined)
  const [mode, setMode] = useState('auto')

  useEffect(() => {
    let active = true
    getFeaturedDeck(playerId)
      .then((res) => {
        if (!active) return
        setDeck(res?.deck || null)
        setMode(res?.mode || 'auto')
        onLoaded?.(res || null)
      })
      .catch(() => active && setDeck(null))
    return () => {
      active = false
    }
  }, [playerId, refreshKey]) // eslint-disable-line react-hooks/exhaustive-deps

  if (deck === undefined) return null

  if (!deck) {
    if (!isOwner) return null
    return (
      <section className="rounded-xl border border-dashed border-border bg-bg-surface p-5 flex flex-wrap items-center justify-between gap-4">
        <div className="min-w-0">
          <h2 className="text-xs font-bold uppercase tracking-wider text-text-muted">Featured Deck</h2>
          <p className="text-sm text-text-muted mt-1">
            {mode === 'off'
              ? 'Turned off. Nobody sees a featured deck on your profile.'
              : 'Your most-played deck shows here once it is public on sorcerytcg.com or Sorcery Online. Or pick a deck yourself.'}
          </p>
        </div>
        <button
          type="button"
          onClick={onEdit}
          className="px-4 py-2 text-sm font-semibold rounded bg-secondary text-black hover:opacity-90"
        >
          {mode === 'off' ? 'Turn on' : 'Choose a deck'}
        </button>
      </section>
    )
  }

  return (
    <section className="bg-bg-surface border border-border rounded-xl p-5 space-y-4" aria-label="Featured deck">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-4 min-w-0">
          {deck.avatar_image && (
            <img
              src={`/card-images/${deck.avatar_image}`}
              alt={deck.avatar || ''}
              className="w-14 sm:w-16 rounded shrink-0"
              loading="lazy"
            />
          )}
          <div className="min-w-0">
            <h2 className="text-xs font-bold uppercase tracking-wider text-text-muted">
              Featured Deck
              {deck.picked === 'auto' && (
                <span className="ml-2 normal-case tracking-normal font-semibold text-secondary">· Most played</span>
              )}
            </h2>
            <p className="text-xl font-display text-text-primary break-words mt-0.5">{deck.name}</p>
            {deck.avatar && <p className="text-sm text-text-muted">{deck.avatar}</p>}
          </div>
        </div>
        <div className="flex items-center gap-4 shrink-0">
          <a
            href={deck.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-secondary hover:underline"
          >
            View on {getDeckSourceLabel(deck.url)} &rarr;
          </a>
          {isOwner && (
            <button
              type="button"
              onClick={onEdit}
              className="px-3 py-1.5 text-sm rounded border border-border text-text-muted hover:text-text-primary hover:border-secondary"
            >
              Edit
            </button>
          )}
        </div>
      </div>
      {isOwner && (
        <p className="text-xs text-text-muted">
          {deck.picked === 'auto'
            ? 'Picked for you: your most-played deck that is public. It changes when you play another deck more. Edit to choose your own or turn it off.'
            : deck.auto_update
              ? 'Kept up to date: changes you make to the public deck show here within a few hours.'
              : 'Saved as it was when you added it. Turn on "Keep it up to date" to follow changes.'}
        </p>
      )}
      <DeckVisualizer spellbook={deck.spellbook} atlas={deck.atlas} sideboard={deck.sideboard} />
    </section>
  )
}
