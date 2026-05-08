import { useState, useEffect } from 'react'
import { addCommunityEntry } from '@/api/community'

const TYPES = [
  { value: 'youtube', label: 'YouTube Channel' },
  { value: 'discord', label: 'Discord Server' },
  { value: 'website', label: 'Website' },
]

const INITIAL = { name: '', description: '', invite_url: '', state: '', channel_id: '', channel_url: '', url: '' }

export default function AddCommunityModal({ onClose, onSaved }) {
  const [type, setType] = useState('youtube')
  const [fields, setFields] = useState(INITIAL)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const set = (key, value) => setFields((f) => ({ ...f, [key]: value }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await addCommunityEntry({ type, ...fields })
      onSaved()
    } catch (err) {
      setError(err.message || 'Failed to add entry')
    } finally {
      setSaving(false)
    }
  }

  const canSubmit = () => {
    if (!fields.name.trim()) return false
    if (type === 'discord') return fields.invite_url.trim() && fields.state.trim()
    if (type === 'youtube') return fields.channel_id.trim() && fields.channel_url.trim()
    if (type === 'website') return fields.url.trim()
    return false
  }

  return (
    <div className="fixed inset-0 z-[1100] flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-bg-surface border border-border rounded-lg w-full max-w-lg mx-4 max-h-[90vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="p-5 border-b border-border flex-shrink-0">
          <h3 className="text-lg font-semibold text-text-primary">Add Community Entry</h3>
        </div>

        <form onSubmit={handleSubmit} className="p-5 overflow-y-auto flex-1 space-y-3">
          <div>
            <label className="text-xs text-text-muted block mb-1">Type *</label>
            <select
              value={type}
              onChange={(e) => { setType(e.target.value); setFields(INITIAL); setError(null) }}
              className="w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm"
            >
              {TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-xs text-text-muted block mb-1">Name *</label>
            <input
              type="text"
              value={fields.name}
              onChange={(e) => set('name', e.target.value)}
              className="w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm"
              required
              autoFocus
            />
          </div>

          {type === 'discord' && (
            <>
              <div>
                <label className="text-xs text-text-muted block mb-1">Invite URL *</label>
                <input
                  type="url"
                  value={fields.invite_url}
                  onChange={(e) => set('invite_url', e.target.value)}
                  placeholder="https://discord.gg/..."
                  className="w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm"
                  required
                />
              </div>
              <div>
                <label className="text-xs text-text-muted block mb-1">Location *</label>
                <input
                  type="text"
                  value={fields.state}
                  onChange={(e) => set('state', e.target.value)}
                  placeholder="e.g. California, USA"
                  className="w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm"
                  required
                />
              </div>
              <div>
                <label className="text-xs text-text-muted block mb-1">Description</label>
                <input
                  type="text"
                  value={fields.description}
                  onChange={(e) => set('description', e.target.value)}
                  className="w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm"
                />
              </div>
            </>
          )}

          {type === 'youtube' && (
            <>
              <div>
                <label className="text-xs text-text-muted block mb-1">Channel ID *</label>
                <input
                  type="text"
                  value={fields.channel_id}
                  onChange={(e) => set('channel_id', e.target.value)}
                  placeholder="e.g. UCxxxxxxxxxxxxxxxx"
                  className="w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm"
                  required
                />
              </div>
              <div>
                <label className="text-xs text-text-muted block mb-1">Channel URL *</label>
                <input
                  type="url"
                  value={fields.channel_url}
                  onChange={(e) => set('channel_url', e.target.value)}
                  placeholder="https://www.youtube.com/@..."
                  className="w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm"
                  required
                />
              </div>
            </>
          )}

          {type === 'website' && (
            <>
              <div>
                <label className="text-xs text-text-muted block mb-1">URL *</label>
                <input
                  type="url"
                  value={fields.url}
                  onChange={(e) => set('url', e.target.value)}
                  placeholder="https://..."
                  className="w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm"
                  required
                />
              </div>
              <div>
                <label className="text-xs text-text-muted block mb-1">Description</label>
                <input
                  type="text"
                  value={fields.description}
                  onChange={(e) => set('description', e.target.value)}
                  className="w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm"
                />
              </div>
            </>
          )}

          {error && <p className="text-xs text-red-400">{error}</p>}

          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm bg-bg-elevated border border-border rounded hover:border-secondary transition-colors">
              Cancel
            </button>
            <button type="submit" disabled={saving || !canSubmit()} className="px-3 py-1.5 text-sm bg-secondary text-black font-medium rounded hover:bg-secondary/80 transition-colors disabled:opacity-40">
              {saving ? 'Adding...' : 'Add'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
