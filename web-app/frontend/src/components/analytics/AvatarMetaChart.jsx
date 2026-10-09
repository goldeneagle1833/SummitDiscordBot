import { useState, useEffect, useMemo, useRef } from 'react'
import { get } from '@/api/client'
import { getAvatarImageFiles } from '@/api/cards'
import { getAvatarImagePath } from '@/utils/avatarBadges'
import Spinner from '@/components/ui/Spinner'

const WINDOWS = [
  { key: '7', label: '7 days', days: 7 },
  { key: '30', label: '30 days', days: 30 },
  { key: '90', label: '90 days', days: 90 },
  { key: 'all', label: 'All time', days: null },
]
const TOP_N = 12

function formatDay(iso) {
  if (!iso) return ''
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

/**
 * Turn {name: {date: count}} into running totals per avatar so any window's
 * count is one subtraction: cumulative[name][i] = decks through dates[i].
 */
export function buildCumulative(dates, avatars) {
  const out = {}
  for (const [name, byDay] of Object.entries(avatars || {})) {
    const running = new Array(dates.length)
    let sum = 0
    dates.forEach((d, i) => {
      sum += byDay[d] || 0
      running[i] = sum
    })
    out[name] = running
  }
  return out
}

/** Decks per avatar in the `days`-long window ending at index `end` (null days = everything so far). */
export function countsAt(cumulative, end, days) {
  const rows = []
  if (end < 0) return rows
  for (const [name, running] of Object.entries(cumulative)) {
    const before = days == null || end - days < 0 ? 0 : running[end - days]
    const count = running[end] - before
    if (count > 0) rows.push({ name, count })
  }
  return rows.sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
}

export default function AvatarMetaChart() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [imageFiles, setImageFiles] = useState([])
  const [windowKey, setWindowKey] = useState('30')
  const [endIdx, setEndIdx] = useState(-1)
  const [showAll, setShowAll] = useState(false)
  const [playing, setPlaying] = useState(false)
  const timer = useRef(null)

  useEffect(() => {
    get('/api/elements/avatar-meta')
      .then((d) => {
        setData(d)
        setEndIdx((d?.dates?.length || 0) - 1)
      })
      .catch((err) => setError(err.message))
    getAvatarImageFiles().then((f) => setImageFiles(Array.isArray(f) ? f : [])).catch(() => {})
  }, [])

  const dates = data?.dates || []
  const cumulative = useMemo(() => buildCumulative(data?.dates || [], data?.avatars), [data])
  const days = WINDOWS.find((w) => w.key === windowKey)?.days ?? null

  const rows = useMemo(() => countsAt(cumulative, endIdx, days), [cumulative, endIdx, days])
  const prevCounts = useMemo(() => {
    if (days == null || endIdx - days < 0) return null
    return Object.fromEntries(countsAt(cumulative, endIdx - days, days).map((r) => [r.name, r.count]))
  }, [cumulative, endIdx, days])

  // Play animates the slider from the start to the latest day
  useEffect(() => {
    if (!playing) return undefined
    const step = Math.max(1, Math.round(dates.length / 120))
    timer.current = setInterval(() => {
      setEndIdx((i) => Math.min(i + step, dates.length - 1))
    }, 100)
    return () => clearInterval(timer.current)
  }, [playing, dates.length])

  useEffect(() => {
    if (playing && endIdx >= dates.length - 1) setPlaying(false)
  }, [playing, endIdx, dates.length])

  const togglePlay = () => {
    if (!playing && endIdx >= dates.length - 1) setEndIdx(Math.min((days || 1) - 1, dates.length - 1))
    setPlaying((p) => !p)
  }

  if (error) return null
  if (!data) return <Spinner className="py-10" />
  if (!dates.length) {
    return <p className="text-center text-text-muted py-6">No avatar data yet.</p>
  }

  const total = rows.reduce((s, r) => s + r.count, 0)
  const max = rows[0]?.count || 1
  const shown = showAll ? rows : rows.slice(0, TOP_N)
  const startIdx = days == null ? 0 : Math.max(0, endIdx - days + 1)

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-5 mb-6">
      <h3 className="font-display text-secondary text-lg mb-1">Avatar Counts Over Time</h3>
      <p className="text-xs text-text-muted mb-4">
        Decks reported with each avatar (online matches, both players). Drag the slider or press play to watch the meta shift.
      </p>

      <div className="flex flex-wrap items-center gap-2 mb-3">
        {WINDOWS.map((w) => (
          <button
            key={w.key}
            type="button"
            onClick={() => setWindowKey(w.key)}
            className={`px-3 py-1 text-xs font-medium rounded-lg border transition-colors ${windowKey === w.key ? 'bg-primary text-bg border-primary' : 'bg-bg-raised text-text-muted border-border hover:text-text'}`}
          >
            {w.label}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-3 mb-1">
        <button
          type="button"
          onClick={togglePlay}
          aria-label={playing ? 'Pause' : 'Play'}
          className="w-8 h-8 flex-shrink-0 rounded-full border border-border bg-bg-raised text-text hover:border-primary text-xs"
        >
          {playing ? '❚❚' : '▶'}
        </button>
        <input
          type="range"
          min={0}
          max={dates.length - 1}
          value={Math.max(endIdx, 0)}
          onChange={(e) => { setPlaying(false); setEndIdx(Number(e.target.value)) }}
          aria-label="Date"
          className="flex-1 accent-secondary"
        />
      </div>
      <div className="flex justify-between text-[11px] text-text-muted mb-4 pl-11">
        <span>{formatDay(dates[0])}</span>
        <span>{formatDay(dates[dates.length - 1])}</span>
      </div>

      <p className="text-sm text-text mb-3">
        <span className="font-semibold">{formatDay(dates[startIdx])}</span>
        {startIdx !== endIdx && <> to <span className="font-semibold">{formatDay(dates[endIdx])}</span></>}
        <span className="text-text-muted"> · {total} deck{total !== 1 ? 's' : ''}</span>
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
