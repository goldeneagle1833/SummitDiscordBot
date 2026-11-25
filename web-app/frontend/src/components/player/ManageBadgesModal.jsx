import { useEffect, useState } from 'react'
import { setShownBadges } from '@/api/players'
import { DEFAULT_SHOWN, heroBadgeKeys } from '@/components/player/profileBadges'

/**
 * Owner setting: which badges show on the profile's hero card. By default
 * it is the player's best 3, so the card stays tidy; the player can tick
 * their own set instead, or go back to the default. Every badge is always
 * listed in the Postseason tab.
 */
export default function ManageBadgesModal({ playerId, badges = [], shown = null, hidden = [], onClose, onSaved }) {
  const [on, setOn] = useState(() => heroBadgeKeys(badges, shown, hidden))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const isDefault = !Array.isArray(shown)

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  const toggle = (key) => {
    setOn((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const save = async (value) => {
    setSaving(true)
    setError(null)
    try {
      const res = await setShownBadges(playerId, value)
      onSaved?.(res && 'shown' in res ? res.shown : value)
      onClose()
    } catch (err) {
      setError(err.message || 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  // Saved best first, so the card keeps its usual order
  const picked = () => badges.map((b) => b.key).filter((k) => on.has(k))

  const groups = []
  for (const b of badges) {
    let g = groups.find((x) => x.name === b.group)
    if (!g) {
      g = { name: b.group, items: [] }
      groups.push(g)
    }
    g.items.push(b)
  }

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
            Your profile shows your best {DEFAULT_SHOWN} badges unless you pick your own. Every badge is still listed in your Postseason tab.
          </p>
        </div>

        <div className="px-5 overflow-y-auto flex-1">
          {badges.length === 0 ? (
            <p className="text-sm text-text-muted py-6 text-center">You don't have any badges yet.</p>
          ) : (
            <>
              <div className="flex items-center justify-between text-xs text-text-muted mb-2">
                <span>
                  {on.size} of {badges.length} showing{isDefault ? ` (your best ${DEFAULT_SHOWN})` : ''}
                </span>
                <span className="flex gap-3">
                  <button type="button" className="text-secondary hover:underline" onClick={() => setOn(new Set(badges.map((b) => b.key)))}>All</button>
                  <button type="button" className="text-secondary hover:underline" onClick={() => setOn(new Set())}>None</button>
                </span>
              </div>
              <div className="space-y-4 pb-2">
                {groups.map((g) => (
                  <div key={g.name}>
                    <div className="text-[11px] font-bold uppercase tracking-wider text-text-muted mb-1.5">{g.name}</div>
                    <ul className="space-y-1.5">
                      {g.items.map((b) => {
                        const checked = on.has(b.key)
                        return (
                          <li key={b.key}>
                            <label className="flex items-center gap-3 p-2.5 rounded-lg border border-border bg-bg-raised cursor-pointer">
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggle(b.key)}
                                className="h-5 w-5 shrink-0 accent-[var(--color-secondary,#d4a94a)]"
                              />
                              <span className="min-w-0">
                                <span className={`block text-sm font-semibold ${checked ? 'text-text-primary' : 'text-text-muted'}`}>
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

        <div className="p-4 flex flex-wrap justify-end gap-2 border-t border-border mt-2">
          {!isDefault && (
            <button
              onClick={() => save(null)}
              disabled={saving}
              className="mr-auto px-3 py-2 text-sm rounded text-secondary hover:underline disabled:opacity-50"
            >
              Use my best {DEFAULT_SHOWN}
            </button>
          )}
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded border border-border text-text-muted hover:text-text-primary"
          >
            Cancel
          </button>
          <button
            onClick={() => save(picked())}
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
