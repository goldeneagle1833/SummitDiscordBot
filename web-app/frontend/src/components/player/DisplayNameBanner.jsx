import { useState } from 'react'
import { setDisplayName } from '@/api/players'

export default function DisplayNameBanner({ playerId, defaultName, hasCustomName, onNameChange }) {
  const [dismissed, setDismissed] = useState(
    () => sessionStorage.getItem('display_name_banner_dismissed') === '1'
  )
  const [showModal, setShowModal] = useState(false)
  const [nameInput, setNameInput] = useState(defaultName || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  if (hasCustomName || dismissed) return null

  const dismiss = () => {
    sessionStorage.setItem('display_name_banner_dismissed', '1')
    setDismissed(true)
  }

  const openModal = () => {
    setNameInput(defaultName || '')
    setError(null)
    setShowModal(true)
  }

  const submit = async (name) => {
    const trimmed = (name || '').trim()
    if (!trimmed || trimmed.length > 32) {
      setError('Name must be 1-32 characters.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await setDisplayName(playerId, trimmed)
      setShowModal(false)
      dismiss()
      onNameChange?.(trimmed)
    } catch (err) {
      setError(err.message || 'Failed to set display name')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <div className="flex items-center gap-3 p-3 rounded-lg border"
        style={{ background: 'linear-gradient(135deg, rgba(232,168,0,0.15), rgba(200,146,0,0.1))', borderColor: 'rgba(232,168,0,0.3)' }}
      >
        <span className="text-lg">&#128211;</span>
        <p className="text-sm text-text-primary flex-1">Set a custom display name for the leaderboard and your profile.</p>
        <button
          onClick={openModal}
          className="px-3 py-1.5 text-xs font-medium bg-secondary text-black rounded hover:opacity-90 transition-opacity"
        >
          Set Name
        </button>
        <button onClick={dismiss} className="text-text-muted hover:text-text-primary text-lg leading-none">&times;</button>
      </div>

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShowModal(false)}>
          <div className="bg-bg-surface border border-border rounded-lg p-6 w-full max-w-md mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-text-primary mb-4">Set Display Name</h3>
            <input
              type="text"
              value={nameInput}
              onChange={(e) => setNameInput(e.target.value)}
              maxLength={32}
              placeholder="Enter your display name"
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-2"
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && submit(nameInput)}
            />
            <p className="text-xs text-text-muted mb-4">1-32 characters. Letters, numbers, spaces, hyphens, underscores, and periods.</p>
            {error && <p className="text-xs text-accent-red mb-3">{error}</p>}
            <div className="flex justify-end gap-2">
              <button
                onClick={() => submit(defaultName)}
                disabled={saving}
                className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40"
              >
                Use Default
              </button>
              <button
                onClick={() => submit(nameInput)}
                disabled={saving}
                className="px-3 py-1.5 text-sm bg-secondary text-black rounded hover:opacity-90 disabled:opacity-40"
              >
                {saving ? 'Saving...' : 'Save Name'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
