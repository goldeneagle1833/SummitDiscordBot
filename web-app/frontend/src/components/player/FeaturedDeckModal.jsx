import { useState } from 'react'
import { setFeaturedDeck, clearFeaturedDeck } from '@/api/players'
import { DECK_URL_PLACEHOLDER } from '@/utils/deckLinks'

/** Owner's settings for the featured deck: pick a recent deck or paste a link, or remove it. */
export default function FeaturedDeckModal({ playerId, current, recentDecks = [], onClose, onSaved }) {
  const chosen = current?.deck || null
  const [url, setUrl] = useState(chosen?.url || '')
  const [autoUpdate, setAutoUpdate] = useState(chosen ? Boolean(chosen.auto_update) : true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const run = async (action, failure) => {
    setSaving(true)
    setError(null)
    try {
      await action()
      onSaved?.()
      onClose()
    } catch (err) {
      setError(err.message || failure)
    } finally {
      setSaving(false)
    }
  }

  const save = () => {
    const trimmed = url.trim()
    if (!trimmed) {
      setError('Pick a deck or paste a deck link.')
      return
    }
    run(() => setFeaturedDeck(playerId, trimmed, autoUpdate), 'Could not save the deck')
  }

  const remove = () => run(() => clearFeaturedDeck(playerId), 'Could not remove the deck')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        role="dialog"
        aria-label="Featured deck"
        className="bg-bg-surface border border-border rounded-lg p-6 w-full max-w-md mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-lg font-semibold text-text-primary mb-1">Featured Deck</h3>
        <p className="text-sm text-text-muted mb-4">
          Everyone who visits your profile sees this deck and its full card list.
        </p>

        {recentDecks.length > 0 && (
          <>
            <label htmlFor="featured-deck-recent" className="block text-xs text-text-muted mb-1">
              Pick from your recent decks
            </label>
            <select
              id="featured-deck-recent"
              value={recentDecks.some((d) => d.url === url.trim()) ? url.trim() : ''}
              onChange={(e) => e.target.value && setUrl(e.target.value)}
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-3"
            >
              <option value="">Choose a recent deck…</option>
              {recentDecks.map((d) => (
                <option key={d.url} value={d.url}>
                  {d.deck_name}{d.avatar && d.avatar !== 'Unknown' ? ` · ${d.avatar}` : ''} ({d.wins}W {d.losses}L)
                </option>
              ))}
            </select>
          </>
        )}

        <label htmlFor="featured-deck-url" className="block text-xs text-text-muted mb-1">
          {recentDecks.length > 0 ? 'Or paste a deck link' : 'Deck link'}
        </label>
        <input
          id="featured-deck-url"
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder={DECK_URL_PLACEHOLDER}
          className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm"
          onKeyDown={(e) => e.key === 'Enter' && save()}
        />
        <label className="flex items-start gap-2 mt-3 text-sm text-text-primary cursor-pointer">
          <input
            type="checkbox"
            checked={autoUpdate}
            onChange={(e) => setAutoUpdate(e.target.checked)}
            className="mt-0.5"
          />
          <span>
            Keep it up to date
            <span className="block text-xs text-text-muted">
              When you change the deck, your profile follows within a few hours.
            </span>
          </span>
        </label>

        {error && <p className="text-xs text-accent-red mt-3">{error}</p>}
        <div className="flex flex-wrap justify-between gap-2 mt-5">
          <div>
            {chosen && (
              <button
                type="button"
                onClick={remove}
                disabled={saving}
                className="px-3 py-1.5 text-sm rounded border border-border text-accent-red hover:border-accent-red disabled:opacity-40"
              >
                Remove
              </button>
            )}
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={save}
              disabled={saving}
              className="px-3 py-1.5 text-sm bg-secondary text-black rounded hover:opacity-90 disabled:opacity-40"
            >
              {saving ? 'Checking deck...' : 'Save'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
