import { useState } from 'react'
import { setFeaturedDeck, clearFeaturedDeck } from '@/api/players'
import { DECK_URL_PLACEHOLDER } from '@/utils/deckLinks'

/** Owner's settings for the featured deck: paste a public link, or remove it. */
export default function FeaturedDeckModal({ playerId, current, onClose, onSaved }) {
  const [url, setUrl] = useState(current?.url || '')
  const [autoUpdate, setAutoUpdate] = useState(current ? Boolean(current.auto_update) : true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const save = async () => {
    const trimmed = url.trim()
    if (!trimmed) {
      setError('Paste a deck link.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await setFeaturedDeck(playerId, trimmed, autoUpdate)
      onSaved?.()
      onClose()
    } catch (err) {
      setError(err.message || 'Could not save the deck')
    } finally {
      setSaving(false)
    }
  }

  const remove = async () => {
    setSaving(true)
    setError(null)
    try {
      await clearFeaturedDeck(playerId)
      onSaved?.()
      onClose()
    } catch (err) {
      setError(err.message || 'Could not remove the deck')
    } finally {
      setSaving(false)
    }
  }

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
          Everyone who visits your profile sees this deck. The deck must be set to public on
          sorcerytcg.com or Sorcery Online.
        </p>
        <label htmlFor="featured-deck-url" className="block text-xs text-text-muted mb-1">Deck link</label>
        <input
          id="featured-deck-url"
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder={DECK_URL_PLACEHOLDER}
          className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm"
          autoFocus
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
            {current && (
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
