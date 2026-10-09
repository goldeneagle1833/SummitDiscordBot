import { useState, useMemo } from 'react'
import { getAvatarImagePath } from '@/utils/avatarBadges'
import { countsAt } from '@/utils/elementTimeline'

const TOP_N = 12

/**
 * Decks per avatar for the timeline's current window, as horizontal bars.
 * `cumulative` is {avatar: running totals} on the page's shared date axis.
 */
export default function AvatarMetaChart({ cumulative, endIdx, days, imageFiles = [] }) {
  const [showAll, setShowAll] = useState(false)

  const rows = useMemo(() => countsAt(cumulative, endIdx, days), [cumulative, endIdx, days])
  const prevCounts = useMemo(() => {
    if (days == null || endIdx - days < 0) return null
    return Object.fromEntries(countsAt(cumulative, endIdx - days, days).map((r) => [r.name, r.count]))
  }, [cumulative, endIdx, days])

  const total = rows.reduce((s, r) => s + r.count, 0)
  const max = rows[0]?.count || 1
  const shown = showAll ? rows : rows.slice(0, TOP_N)

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-5 mb-6">
      <h3 className="font-display text-secondary text-lg mb-1">Avatar Counts</h3>
      <p className="text-xs text-text-muted mb-4">
        Decks reported with each avatar in the selected window (online matches, both players)
        <span className="text-text"> · {total} deck{total !== 1 ? 's' : ''}</span>
      </p>

      {shown.length === 0 ? (
        <p className="text-sm text-text-muted py-4">No decks reported in this window.</p>
      ) : (
        <div className="space-y-1.5">
          {shown.map((r) => {
            const imgFile = getAvatarImagePath(r.name, imageFiles)
            const share = total ? ((r.count / total) * 100).toFixed(1) : '0.0'
            const prev = prevCounts ? prevCounts[r.name] || 0 : null
            const delta = prev == null ? null : r.count - prev
            return (
              <div key={r.name} className="flex items-center gap-2" data-testid="meta-row">
                <div className="w-36 sm:w-44 flex items-center gap-2 flex-shrink-0 min-w-0">
                  {imgFile ? (
                    <img src={`/avatar-images/${imgFile}`} alt="" className="w-6 h-6 rounded-full object-cover object-top flex-shrink-0" />
                  ) : (
                    <span className="w-6 h-6 rounded-full bg-bg-raised flex-shrink-0" />
                  )}
                  <span className="text-xs font-semibold text-text truncate" title={r.name}>{r.name}</span>
                </div>
                <div className="flex-1 bg-bg-raised rounded-full h-5 overflow-hidden">
                  <div
                    className="bg-secondary/60 h-full rounded-full transition-all duration-300"
                    style={{ width: `${Math.max((r.count / max) * 100, 1)}%` }}
                  />
                </div>
                <div className="w-28 text-right text-xs text-text-muted flex-shrink-0">
                  <span className="text-text font-semibold">{r.count}</span> · {share}%
                  {delta != null && delta !== 0 && (
                    <span className={`ml-1 ${delta > 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {delta > 0 ? '▲' : '▼'}{Math.abs(delta)}
                    </span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {rows.length > TOP_N && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="mt-3 text-xs text-secondary hover:underline"
        >
          {showAll ? `Show top ${TOP_N}` : `Show all ${rows.length} avatars`}
        </button>
      )}
      {days != null && (
        <p className="text-[11px] text-text-muted mt-3">▲▼ change versus the {days} days before.</p>
      )}
    </div>
  )
}
