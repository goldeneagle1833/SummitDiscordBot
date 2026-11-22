import { useState, useEffect } from 'react'
import { get } from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import { ALL_NAV_OPTIONS, PERMANENT_LINKS, normalizeLabels } from '@/components/layout/Nav'

function Tile({ label, value, color = 'text-secondary', small = false }) {
  return (
    <div className="bg-bg-raised border border-border rounded-lg p-4 text-center">
      <div className={`${small ? 'text-base sm:text-lg py-1' : 'text-2xl'} font-bold ${color} leading-tight`}>{value ?? '--'}</div>
      <div className="text-xs text-text-muted mt-1 leading-tight">{label}</div>
    </div>
  )
}

/** Count how many saved top bars include each Customize option. */
export function countNavPicks(saves) {
  const options = ALL_NAV_OPTIONS.map((o) => o.label).filter((l) => !PERMANENT_LINKS.includes(l))
  const counts = Object.fromEntries(options.map((l) => [l, 0]))
  let added = 0
  let onlyDefaults = 0
  for (const save of saves) {
    const picked = normalizeLabels(save).filter((l) => l in counts)
    picked.forEach((l) => { counts[l] += 1 })
    added += picked.length
    if (picked.length === 0) onlyDefaults += 1
  }
  const rows = options
    .map((label, i) => ({ label, count: counts[label], order: i }))
    .sort((a, b) => b.count - a.count || a.order - b.order)
  return { rows, people: saves.length, added, onlyDefaults }
}

/** Admin: which pages people pin to their top bar through Customize. */
export default function NavPicksSection() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    get('/api/admin/nav-picks')
      .then((d) => setData(countNavPicks(d.saves || [])))
      .catch((e) => setError(e.message))
  }, [])

  if (error) return <div className="px-4 py-6 text-sm text-accent-red">{error}</div>
  if (!data) return <div className="flex justify-center py-8"><Spinner /></div>

  const { rows, people, added, onlyDefaults } = data
  const top = rows[0]?.count ? rows[0].label : '-'
  const max = Math.max(1, rows[0]?.count || 0)

  return (
    <section className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Tile label="People who customized" value={people} />
        <Tile label="Pages added per person" value={people ? (added / people).toFixed(1) : '0'} />
        <Tile label="Saved with nothing added" value={onlyDefaults} color="text-text-muted" />
        <Tile label="Most pinned" value={top} small />
      </div>

      <div className="bg-bg-raised border border-border rounded-lg divide-y divide-border/50 max-w-3xl">
        {rows.map((r, i) => {
          const pct = people ? Math.round((r.count / people) * 100) : 0
          return (
            <div key={r.label} className="flex items-center gap-3 px-4 py-2 text-sm">
              <span className="w-5 text-xs text-text-muted text-right shrink-0">{i + 1}</span>
              <span className={`w-36 sm:w-44 shrink-0 truncate ${r.count ? 'text-text-primary' : 'text-text-muted'}`}>{r.label}</span>
              <div className="flex-1 h-2 rounded-full bg-white/5 overflow-hidden min-w-0">
                <div className="h-full bg-secondary/70 rounded-full" style={{ width: `${(r.count / max) * 100}%` }} />
              </div>
              <span className="w-16 text-right shrink-0 tabular-nums">
                <span className="text-text-primary">{r.count}</span>
                <span className="text-xs text-text-muted ml-1">{pct}%</span>
              </span>
            </div>
          )
        })}
      </div>
      <p className="text-xs text-text-muted">
        Counts people who pressed Save in Customize Nav Bar (the pencil by the top bar links), which needs a login.
        People who never opened it just see the defaults and are not counted. {PERMANENT_LINKS.join(', ')} is always on
        the top bar, so it is left out. % is out of the people who customized.
      </p>
    </section>
  )
}
