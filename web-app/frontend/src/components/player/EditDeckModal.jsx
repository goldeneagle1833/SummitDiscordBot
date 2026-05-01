import { useState } from 'react'
import { updateMatchDeck } from '@/api/games'

export default function EditDeckModal({ matchId, currentUrl, eloSource, onClose, onSaved }) {
  const [deckUrl, setDeckUrl] = useState(currentUrl || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const handleSubmit = async () => {
    const trimmed = deckUrl.trim()
    if (!trimmed) {
      setError('Please enter a deck URL.')
      return
    }
    try {
      new URL(trimmed)
    } catch {
      setError('Please enter a valid URL.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await updateMatchDeck(matchId, trimmed, eloSource)
      onSaved?.()
      onClose()
    } catch (err) {
      setError(err.message || 'Failed to update deck')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-bg-surface border border-border rounded-lg p-6 w-full max-w-md mx-4" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold text-text-primary mb-1">Edit Deck Link</h3>
        <p className="text-xs text-text-muted mb-4">Match #{matchId}</p>
        <input
          type="url"
          value={deckUrl}
          onChange={(e) => setDeckUrl(e.target.value)}
          placeholder="https://curiosa.io/decks/..."
          className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-2"
          autoFocus
          onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
        />
        {error && <p className="text-xs text-accent-red mb-3">{error}</p>}
        <div className="flex justify-end gap-2 mt-4">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={saving}
            className="px-3 py-1.5 text-sm bg-secondary text-white rounded hover:opacity-90 disabled:opacity-40"
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
