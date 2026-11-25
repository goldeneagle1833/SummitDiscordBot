import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { get } from '@/api/client'
import Spinner from '@/components/ui/Spinner'

const ICONS = { voice_only: '🔊', tag_me: '🔔', skill_match: '🎯' }

function formatWhen(value) {
  if (!value) return '-'
  const d = new Date(value)
  if (isNaN(d.getTime())) return value
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function SettingCard({ setting }) {
  const [open, setOpen] = useState(false)
  const total = setting.on + setting.off
  const pct = total ? Math.round((100 * setting.on) / total) : 0
  const changedLabel = setting.default_on ? 'turned it off' : 'turned it on'
  return (
    <div className="bg-bg-raised border border-border rounded-lg p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-text-primary">
            {ICONS[setting.key]} {setting.label}
          </div>
          <div className="text-xs text-text-muted mt-0.5">
            {setting.default_on ? 'On' : 'Off'} by default
          </div>
        </div>
        <div className="text-right text-xs text-text-muted whitespace-nowrap">
          {setting.changed_last_7_days} changed this week
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 mt-3">
        <div className="rounded bg-bg-surface border border-border p-2 text-center">
          <div className="text-xl font-bold text-green-400">{setting.on.toLocaleString()}</div>
          <div className="text-xs text-text-muted">On</div>
        </div>
        <div className="rounded bg-bg-surface border border-border p-2 text-center">
          <div className="text-xl font-bold text-text-primary">{setting.off.toLocaleString()}</div>
          <div className="text-xs text-text-muted">Off</div>
        </div>
      </div>
      <div className="h-1.5 rounded-full bg-bg-surface mt-3 overflow-hidden" aria-hidden="true">
        <div className="h-full bg-green-400" style={{ width: `${pct}%` }} />
      </div>
      <div className="text-xs text-text-muted mt-1">{pct}% on</div>

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="text-xs text-secondary hover:underline mt-3"
        aria-expanded={open}
      >
        {open ? 'Hide' : 'Show'} the {setting.players.length} player{setting.players.length === 1 ? '' : 's'} who {changedLabel}
      </button>
      {open && (
        setting.players.length === 0 ? (
          <p className="text-xs text-text-muted mt-2">Nobody yet.</p>
        ) : (
          <ul className="mt-2 max-h-64 overflow-y-auto divide-y divide-border text-sm">
            {setting.players.map((p) => (
              <li key={p.user_id} className="flex items-center justify-between gap-2 py-1.5">
                <Link to={`/player/${p.user_id}`} className="text-text-primary hover:text-secondary truncate">{p.name}</Link>
                <span className="text-xs text-text-muted whitespace-nowrap">
                  {formatWhen(p.set_at)}{p.source ? ` · ${p.source}` : ''}
                </span>
              </li>
            ))}
          </ul>
        )
      )}
    </div>
  )
}

/** Admin: how many players have each Discord queue setting on or off. */
export default function QueueSettingsSection() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    get('/api/admin/queue-settings')
      .then(setData)
      .catch((e) => setError(e.message || 'Failed to load queue settings'))
  }, [])

  if (error) return <div className="px-4 py-6 text-sm text-accent-red">{error}</div>
  if (!data) return <div className="flex justify-center py-8"><Spinner /></div>

  return (
    <section className="space-y-3">
      <p className="text-xs text-text-muted">
        Out of {data.players.toLocaleString()} Discord players with a rating. Players who never opened Queue
        Settings count at the default.
      </p>
      <div className="grid gap-3 md:grid-cols-3 items-start">
        {data.settings.map((s) => <SettingCard key={s.key} setting={s} />)}
      </div>
    </section>
  )
}
