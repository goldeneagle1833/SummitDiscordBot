import { useState, useEffect } from 'react'
import { getProfileVisibility, setProfileVisibility } from '@/api/players'

const SECTION_LABELS = {
  elo_history: 'ELO History',
  elo_brackets: 'ELO Brackets',
  avatar_performance: 'Avatar Performance',
  avatar_matchups: 'Avatar Matchups',
  recent_decks: 'Recent Decks',
  recorded_games: 'Self-Reported Games',
  deck_urls: 'Deck URLs',
  deck_snapshots: 'Deck Snapshots',
}

const SECTION_ORDER = [
  'elo_history',
  'elo_brackets',
  'avatar_performance',
  'avatar_matchups',
  'recent_decks',
  'recorded_games',
  'deck_urls',
  'deck_snapshots',
]

export default function PrivacySettingsModal({ playerId, onClose, onSaved }) {
  const [sections, setSections] = useState(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getProfileVisibility(playerId)
      .then((data) => setSections(data.sections))
      .catch((err) => setError(err.message || 'Failed to load settings'))
      .finally(() => setLoading(false))
  }, [playerId])

  const handleToggle = (key) => {
    setSections((s) => ({ ...s, [key]: !s[key] }))
  }

  const handleToggleAll = (value) => {
    setSections((s) => {
      const updated = { ...s }
      for (const key of SECTION_ORDER) {
        updated[key] = value
      }
      return updated
    })
  }

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      await setProfileVisibility(playerId, sections)
      onSaved?.()
      onClose()
    } catch (err) {
      setError(err.message || 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  const allPublic = sections && SECTION_ORDER.every((k) => sections[k])
  const allPrivate = sections && SECTION_ORDER.every((k) => !sections[k])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-bg-surface border border-border rounded-lg p-6 w-full max-w-md mx-4" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold text-text-primary mb-1">Profile Privacy Settings</h3>
        <p className="text-xs text-text-muted mb-4">
          Choose which sections of your profile are visible to other players.
          All sections are private by default.
        </p>

        {loading && <p className="text-sm text-text-muted py-4 text-center">Loading...</p>}

        {error && <p className="text-xs text-accent-red mb-3">{error}</p>}

        {sections && (
          <>
            <div className="flex gap-2 mb-3">
              <button
                onClick={() => handleToggleAll(true)}
                disabled={allPublic}
                className="text-xs px-2 py-1 rounded bg-bg-raised border border-border text-text-muted hover:text-text-primary disabled:opacity-40"
              >
                Make All Public
              </button>
              <button
                onClick={() => handleToggleAll(false)}
                disabled={allPrivate}
                className="text-xs px-2 py-1 rounded bg-bg-raised border border-border text-text-muted hover:text-text-primary disabled:opacity-40"
              >
                Make All Private
              </button>
            </div>

            <div className="space-y-2 max-h-72 overflow-y-auto">
              {SECTION_ORDER.map((key) => (
                <label
                  key={key}
                  className="flex items-center gap-3 px-3 py-2 rounded bg-bg-raised border border-border cursor-pointer hover:border-secondary/50 transition-colors"
                >
                  <input
                    type="checkbox"
                    checked={sections[key] || false}
                    onChange={() => handleToggle(key)}
                    className="w-4 h-4 accent-secondary"
                  />
                  <span className="text-sm text-text-primary">{SECTION_LABELS[key]}</span>
                  <span className={`ml-auto text-xs ${sections[key] ? 'text-green-400' : 'text-text-muted'}`}>
                    {sections[key] ? 'Public' : 'Private'}
                  </span>
                </label>
              ))}
            </div>
          </>
        )}

        <div className="flex justify-end gap-2 mt-4">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded border border-border text-text-muted hover:text-text-primary"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || loading}
            className="px-4 py-2 text-sm rounded bg-secondary text-black hover:opacity-90 disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
