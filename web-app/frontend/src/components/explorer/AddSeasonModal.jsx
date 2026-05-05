import { useState, useEffect } from 'react'
import { createSeason } from '@/api/explorer'

export default function AddSeasonModal({ onClose, onCreated }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!name.trim()) return
    setSaving(true)
    setError(null)
    try {
      const result = await createSeason(name.trim(), description.trim() || null, null)
      onCreated(result.season)
    } catch (err) {
      if (err.status === 409) {
        setError('Season already exists')
      } else {
        setError(err.message || 'Failed to create season')
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[1100] flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-bg-surface border border-border rounded-lg w-full max-w-sm mx-4" onClick={(e) => e.stopPropagation()}>
        <div className="p-5">
          <h3 className="text-lg font-semibold text-text-primary mb-4">Add Season</h3>
          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className="text-xs text-text-muted block mb-1">Season Name *</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Explorer Series Season 3"
                className="w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm"
                required
                autoFocus
              />
            </div>
            <div>
              <label className="text-xs text-text-muted block mb-1">Description (optional)</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optional description"
                rows={2}
                className="w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm resize-none"
              />
            </div>
            {error && <p className="text-xs text-red-400">{error}</p>}
            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={onClose}
                className="px-3 py-1.5 text-sm bg-bg-elevated border border-border rounded hover:border-secondary transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving || !name.trim()}
                className="px-3 py-1.5 text-sm bg-secondary text-black font-medium rounded hover:bg-secondary/80 transition-colors disabled:opacity-40"
              >
                {saving ? 'Creating...' : 'Create Season'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
