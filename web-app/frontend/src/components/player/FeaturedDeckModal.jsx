import { useState } from 'react'
import { setFeaturedDeck, setFeaturedDeckAuto, clearFeaturedDeck } from '@/api/players'
import { DECK_URL_PLACEHOLDER } from '@/utils/deckLinks'

const CHOICES = [
  {
    value: 'auto',
    label: 'My most-played public deck',
    hint: 'Picked for you from your games. Only decks set to public on sorcerytcg.com or Sorcery Online.',
  },
  { value: 'manual', label: 'A deck I choose', hint: 'Paste a public deck link.' },
  { value: 'off', label: 'No featured deck', hint: 'Nothing shows on your profile.' },
]

/** Owner's settings for the featured deck: automatic, a pasted link, or off. */
export default function FeaturedDeckModal({ playerId, current, onClose, onSaved }) {
  const currentMode = current?.mode || 'auto'
  const pasted = currentMode === 'manual' ? current?.deck : null
  const [choice, setChoice] = useState(currentMode)
  const [url, setUrl] = useState(pasted?.url || '')
  const [autoUpdate, setAutoUpdate] = useState(pasted ? Boolean(pasted.auto_update) : true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const save = async () => {
    const trimmed = url.trim()
    if (choice === 'manual' && !trimmed) {
      setError('Paste a deck link.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      if (choice === 'manual') await setFeaturedDeck(playerId, trimmed, autoUpdate)
      else if (choice === 'auto') await setFeaturedDeckAuto(playerId)
      else await clearFeaturedDeck(playerId)
      onSaved?.()
      onClose()
    } catch (err) {
      setError(err.message || 'Could not save the featured deck')
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
        <p className="text-sm text-text-muted mb-4">Everyone who visits your profile sees this deck.</p>

        <fieldset className="space-y-3">
          <legend className="sr-only">Which deck to feature</legend>
          {CHOICES.map((c) => (
            <div key={c.value}>
              <label className="flex items-start gap-2 text-sm text-text-primary cursor-pointer">
                <input
                  type="radio"
                  name="featured-deck-choice"
                  value={c.value}
                  checked={choice === c.value}
                  onChange={() => setChoice(c.value)}
                  className="mt-1"
                />
                <span>
                  {c.label}
                  <span className="block text-xs text-text-muted">{c.hint}</span>
                </span>
              </label>
              {c.value === 'manual' && choice === 'manual' && (
                <div className="mt-3 pl-6">
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
                </div>
              )}
            </div>
          ))}
        </fieldset>

        {error && <p className="text-xs text-accent-red mt-3">{error}</p>}
        <div className="flex justify-end gap-2 mt-5">
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
            {saving ? (choice === 'manual' ? 'Checking deck...' : 'Saving...') : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
