import { useState, useEffect } from 'react'
import { getQueueSettings, setQueueSettings } from '@/api/players'

export default function QueueSettingsModal({ playerId, onClose }) {
  const [voiceOnly, setVoiceOnly] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    getQueueSettings(playerId)
      .then((data) => setVoiceOnly(Boolean(data.voice_only)))
      .catch((err) => setError(err.message || 'Failed to load settings'))
      .finally(() => setLoading(false))
  }, [playerId])

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      await setQueueSettings(playerId, { voice_only: voiceOnly })
      onClose()
    } catch (err) {
      setError(err.message || 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-bg-surface border border-border rounded-lg p-6 w-full max-w-md mx-4" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold text-text-primary mb-1">Queue Settings</h3>
        <p className="text-xs text-text-muted mb-4">
          How the Summit bot treats you in the Discord queues.
        </p>

        {loading && <p className="text-sm text-text-muted py-4 text-center">Loading...</p>}

        {error && <p className="text-xs text-accent-red mb-3">{error}</p>}

        {!loading && (
          <label className="flex items-start gap-3 px-3 py-3 rounded bg-bg-raised border border-border cursor-pointer hover:border-secondary/50 transition-colors">
            <input
              type="checkbox"
              checked={voiceOnly}
              onChange={() => setVoiceOnly((v) => !v)}
              className="w-4 h-4 mt-0.5 accent-secondary"
            />
            <span>
              <span className="block text-sm text-text-primary">🔊 Voice-only player</span>
              <span className="block text-xs text-text-muted mt-0.5">
                Don&apos;t DM me when someone joins looking for a no-voice game while I&apos;m queued for voice.
              </span>
            </span>
            <span className={`ml-auto text-xs whitespace-nowrap ${voiceOnly ? 'text-green-400' : 'text-text-muted'}`}>
              {voiceOnly ? 'On' : 'Off'}
            </span>
          </label>
        )}

        <p className="text-xs text-text-muted mt-3">
          You can also use <code>/voice-only</code> or <code>!voice_only on</code> / <code>off</code> in Discord.
        </p>

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
