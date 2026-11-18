import { useEffect, useState } from 'react'
import { setHiddenBadges } from '@/api/players'

/**
 * Owner setting: which badges show on the profile's hero card. Every badge
 * starts shown; switching one off keeps it in the Postseason tab.
 */
export default function ManageBadgesModal({ playerId, badges = [], hidden = [], onClose, onSaved }) {
  const [off, setOff] = useState(() => new Set(hidden))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  const toggle = (key) => {
    setOff((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const setAll = (show) => setOff(show ? new Set() : new Set(badges.map((b) => b.key)))

  const save = async () => {
    setSaving(true)
    setError(null)
    // Keys of badges the player no longer holds are dropped on save
    const keys = badges.map((b) => b.key).filter((k) => off.has(k))
    try {
      const res = await setHiddenBadges(playerId, keys)
      onSaved?.(res?.hidden || keys)
      onClose()
    } catch (err) {
      setError(err.message || 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  const groups = []
  for (const b of badges) {
    let g = groups.find((x) => x.name === b.group)
    if (!g) {
      g = { name: b.group, items: [] }
      groups.push(g)
    }
    g.items.push(b)
  }
  const shown = badges.filter((b) => !off.has(b.key)).length

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-label="Profile badges"
        className="bg-bg-surface border border-border rounded-lg w-full max-w-md max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-5 pb-3">
          <h3 className="text-lg font-semibold text-text-primary">Profile badges</h3>
          <p className="text-xs text-text-muted mt-1">
            Pick which badges show under your name. Hidden ones are still listed in your Postseason tab.
          </p>
        </div>

        <div className="px-5 overflow-y-auto flex-1">
          {badges.length === 0 ? (
            <p className="text-sm text-text-muted py-6 text-center">You don't have any badges yet.</p>
          ) : (
            <>
              <div className="flex items-center justify-between text-xs text-text-muted mb-2">
                <span>{shown} of {badges.length} showing</span>
                <span className="flex gap-3">
                  <button type="button" className="text-secondary hover:underline" onClick={() => setAll(true)}>Show all</button>
                  <button type="button" className="text-secondary hover:underline" onClick={() => setAll(false)}>Hide all</button>
                </span>
              </div>
              <div className="space-y-4 pb-2">
                {groups.map((g) => (
                  <div key={g.name}>
                    <div className="text-[11px] font-bold uppercase tracking-wider text-text-muted mb-1.5">{g.name}</div>
                    <ul className="space-y-1.5">
                      {g.items.map((b) => {
                        const on = !off.has(b.key)
                        return (
                          <li key={b.key}>
                            <label className="flex items-center gap-3 p-2.5 rounded-lg border border-border bg-bg-raised cursor-pointer">
                              <input
                                type="checkbox"
                                checked={on}
                                onChange={() => toggle(b.key)}
                                className="h-5 w-5 shrink-0 accent-[var(--color-secondary,#d4a94a)]"
                              />
                              <span className="min-w-0">
                                <span className={`block text-sm font-semibold ${on ? 'text-text-primary' : 'text-text-muted line-through'}`}>
                                  {b.label}
                                </span>
                                <span className="block text-xs text-text-muted truncate">{b.detail}</span>
                              </span>
                            </label>
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                ))}
              </div>
            </>
          )}
          {error && <p className="text-xs text-accent-red mt-2">{error}</p>}
        </div>

        <div className="p-4 flex justify-end gap-2 border-t border-border mt-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded border border-border text-text-muted hover:text-text-primary"
          >
            Cancel
          </button>
          <button
            onClick={save}
            disabled={saving || badges.length === 0}
            className="px-4 py-2 text-sm rounded bg-secondary text-black font-semibold hover:opacity-90 disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
