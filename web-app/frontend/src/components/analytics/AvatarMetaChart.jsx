import { useState, useMemo, useRef, useEffect } from 'react'
import { getAvatarImagePath } from '@/utils/avatarBadges'
import { countsAt, windowSum } from '@/utils/elementTimeline'
import RankedList from './RankedList'

const TOP_N = 12

const PAIR_COLORS = {
  Fire: { hex: '#ef4444', chip: 'bg-red-500/15 text-red-400 border-red-500/40' },
  Water: { hex: '#3b82f6', chip: 'bg-blue-500/15 text-blue-400 border-blue-500/40' },
  Earth: { hex: '#22c55e', chip: 'bg-green-500/15 text-green-400 border-green-500/40' },
  Air: { hex: '#22d3ee', chip: 'bg-cyan-400/15 text-cyan-300 border-cyan-400/40' },
}

/** "Geomancer|Earth / Fire" -> { avatar, elements: ['Earth', 'Fire'] }. Plain avatar names have no elements. */
export function splitPairKey(key) {
  const cut = key.indexOf('|')
  if (cut < 0) return { avatar: key, elements: [] }
  const pair = key.slice(cut + 1)
  return { avatar: key.slice(0, cut), elements: pair ? pair.split(' / ') : [] }
}

/** Bar fill: one solid color per element, side by side. */
function pairFill(elements) {
  const hexes = elements.map((e) => PAIR_COLORS[e]?.hex).filter(Boolean)
  if (hexes.length === 0) return undefined
  if (hexes.length === 1) return hexes[0]
  const step = 100 / hexes.length
  return `linear-gradient(90deg, ${hexes.map((h, i) => `${h} ${i * step}%, ${h} ${(i + 1) * step}%`).join(', ')})`
}

/**
 * Decks per Avatar + element pair for the timeline's current window, as
 * horizontal bars. `cumulative` is {"Avatar|Air / Fire": running totals} on the
 * page's shared date axis (plain avatar keys also work, with no element chips).
 */
export default function AvatarMetaChart({ cumulative, endIdx, days, imageFiles = [] }) {
  const [showAll, setShowAll] = useState(false)
  const lastRank = useRef(new Map())

  // Every avatar, ranked by count. Ties keep their previous order so near-equal
  // avatars don't swap back and forth on every step; zero-count avatars sit
  // below the visible rows and slide in when they show up.
  const ranked = useMemo(() => {
    const prev = lastRank.current
    const far = Number.MAX_SAFE_INTEGER
    return Object.entries(cumulative)
      .map(([name, running]) => ({ name, count: windowSum(running, endIdx, days) }))
      .sort((a, b) => b.count - a.count || (prev.get(a.name) ?? far) - (prev.get(b.name) ?? far) || a.name.localeCompare(b.name))
  }, [cumulative, endIdx, days])
  useEffect(() => {
    lastRank.current = new Map(ranked.map((r, i) => [r.name, i]))
  }, [ranked])

  const rows = ranked.filter((r) => r.count > 0)
  const prevCounts = useMemo(() => {
    if (days == null || endIdx - days < 0) return null
    return Object.fromEntries(countsAt(cumulative, endIdx - days, days).map((r) => [r.name, r.count]))
  }, [cumulative, endIdx, days])

  const total = rows.reduce((s, r) => s + r.count, 0)
  const max = rows[0]?.count || 1
  const visible = showAll ? rows.length : Math.min(TOP_N, rows.length)

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-5 mb-6">
      <h3 className="font-display text-secondary text-lg mb-1">Avatar Counts</h3>
      <p className="text-xs text-text-muted mb-4">
        Decks reported with each Avatar + element pair in the selected window (online matches, both players).
        Pairs are a deck&apos;s top two spellbook elements, grouped the same way as Deck Archetypes
        <span className="text-text"> · {total} deck{total !== 1 ? 's' : ''}</span>
      </p>

      {rows.length === 0 ? (
        <p className="text-sm text-text-muted py-4">No decks reported in this window.</p>
      ) : (
        <RankedList items={ranked} itemKey={(r) => r.name} gap={6} visible={visible} renderItem={(r) => {
            const { avatar, elements } = splitPairKey(r.name)
            const imgFile = getAvatarImagePath(avatar, imageFiles)
            const fill = pairFill(elements)
            const share = total ? ((r.count / total) * 100).toFixed(1) : '0.0'
            const prev = prevCounts ? prevCounts[r.name] || 0 : null
            const delta = prev == null ? null : r.count - prev
            return (
              <div className="flex items-center gap-2" data-testid={r.count > 0 ? 'meta-row' : undefined}>
                <div className="w-44 sm:w-72 flex items-center gap-2 flex-shrink-0 min-w-0">
                  {imgFile ? (
                    <img src={`/avatar-images/${imgFile}`} alt="" className="w-6 h-6 rounded-full object-cover object-top flex-shrink-0" />
                  ) : (
                    <span className="w-6 h-6 rounded-full bg-bg-raised flex-shrink-0" />
                  )}
                  <span className="text-xs font-semibold text-text truncate" title={avatar}>{avatar}</span>
                  {elements.length > 0 && (
                    <span className="flex gap-1 flex-shrink-0" title={elements.join(' / ')}>
                      {elements.map((el) => (
                        <span key={el} className={`text-[10px] font-bold px-1.5 py-px rounded-full border ${PAIR_COLORS[el]?.chip || 'border-border text-text-muted'}`}>
                          <span className="hidden sm:inline">{el}</span>
                          <span className="sm:hidden" aria-label={el}>{el[0]}</span>
                        </span>
                      ))}
                    </span>
                  )}
                </div>
                <div className="flex-1 bg-bg-raised rounded-full h-5 overflow-hidden">
                  <div
                    className={`h-full rounded-full timeline-bar ${fill ? 'opacity-80' : 'bg-secondary/60'}`}
                    style={{ width: `${Math.max((r.count / max) * 100, 1)}%`, background: fill }}
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
          }} />
      )}

      {rows.length > TOP_N && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="mt-3 text-xs text-secondary hover:underline"
        >
          {showAll ? `Show top ${TOP_N}` : `Show all ${rows.length}`}
        </button>
      )}
      {days != null && (
        <p className="text-[11px] text-text-muted mt-3">▲▼ change versus the {days} days before.</p>
      )}
    </div>
  )
}
