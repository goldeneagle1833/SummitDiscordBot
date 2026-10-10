import { useEffect, useState } from 'react'

// Rolling windows: Play slides them one day per step, so the oldest day drops
// off as each new day comes in. "All time" grows from the first day instead.
export const ROLLING = [7, 14, 30, 90]
const MAX_ROLLING_DAYS = 365

// Playback speed: how long each Play step lasts (bars glide for the whole step)
export const SPEEDS = [
  { key: 'slow', label: 'Slow', ms: 1400 },
  { key: 'normal', label: 'Normal', ms: 800 },
  { key: 'fast', label: 'Fast', ms: 350 },
]
export const DEFAULT_SPEED = 'normal'
export const tickMs = (speed) => (SPEEDS.find((s) => s.key === speed) || SPEEDS[1]).ms
// All-time Play covers the whole range in about this many steps
const PLAY_STEPS = 150

/** Window length in days for a window key ('all' or a day count like '14'); null = all time. */
export const windowDays = (key) => {
  const n = parseInt(key, 10)
  return key === 'all' || !(n > 0) ? null : Math.min(n, MAX_ROLLING_DAYS)
}

export function formatDay(iso) {
  if (!iso) return ''
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

const pill = (active) => `px-3 py-1 text-xs font-medium rounded-lg border transition-colors ${active ? 'bg-primary text-bg border-primary' : 'bg-bg-raised text-text-muted border-border hover:text-text'}`

/**
 * One date slider, play button and window picker that drives every chart on
 * the page. The parent owns the state: { windowKey, endIdx, playing, speed }.
 */
export default function TimelineControls({ dates, windowKey, endIdx, playing, speed = DEFAULT_SPEED, onChange }) {
  const last = dates.length - 1
  const days = windowDays(windowKey)
  const [custom, setCustom] = useState('')
  const pick = (key) => {
    setCustom('')
    onChange((s) => ({ ...s, windowKey: key }))
  }

  // Play steps the slider from where it is to the latest day: one day at a
  // time for a rolling window, or about PLAY_STEPS steps for all time
  useEffect(() => {
    if (!playing) return undefined
    const step = days != null ? 1 : Math.max(1, Math.round(dates.length / PLAY_STEPS))
    const id = setInterval(() => onChange((s) => ({ ...s, endIdx: Math.min(s.endIdx + step, last) })), tickMs(speed))
    return () => clearInterval(id)
  }, [playing, speed, days, dates.length, last, onChange])

  useEffect(() => {
    if (playing && endIdx >= last) onChange((s) => ({ ...s, playing: false }))
  }, [playing, endIdx, last, onChange])

  if (!dates.length) return null

  const togglePlay = () => onChange((s) => {
    if (s.playing) return { ...s, playing: false }
    const restart = s.endIdx >= last ? Math.min((windowDays(s.windowKey) || 1) - 1, last) : s.endIdx
    return { ...s, playing: true, endIdx: restart }
  })

  const startIdx = days == null ? 0 : Math.max(0, endIdx - days + 1)

  return (
    <div className="bg-bg-surface/95 backdrop-blur border border-border rounded-lg px-4 py-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-text-muted">Rolling:</span>
          {ROLLING.map((n) => (
            <button
              key={n}
              type="button"
              onClick={() => pick(String(n))}
              className={pill(days === n && !custom)}
            >
              {n} days
            </button>
          ))}
          <label className="flex items-center gap-1 text-xs text-text-muted">
            <input
              type="number"
              min={1}
              max={MAX_ROLLING_DAYS}
              value={custom}
              placeholder="Custom"
              onChange={(e) => {
                setCustom(e.target.value)
                const n = parseInt(e.target.value, 10)
                if (n > 0) onChange((s) => ({ ...s, windowKey: String(Math.min(n, MAX_ROLLING_DAYS)) }))
              }}
              aria-label="Custom rolling window in days"
              className="w-20 bg-bg-raised border border-border rounded-lg px-2 py-1 text-xs"
            />
            days
          </label>
          <button
            type="button"
            onClick={() => pick('all')}
            className={pill(days == null)}
          >
            All time
          </button>
        </div>
        <p className="text-sm text-text" data-testid="timeline-range">
          {days != null && <span className="text-text-muted">{days}-day window · </span>}
          <span className="font-semibold">{formatDay(dates[startIdx])}</span>
          {startIdx !== endIdx && <> to <span className="font-semibold">{formatDay(dates[endIdx])}</span></>}
        </p>
      </div>
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={togglePlay}
          aria-label={playing ? 'Pause' : 'Play'}
          className="w-8 h-8 flex-shrink-0 rounded-full border border-border bg-bg-raised text-text hover:border-primary text-xs"
        >
          {playing ? '❚❚' : '▶'}
        </button>
        <span className="hidden sm:inline text-[11px] text-text-muted">{formatDay(dates[0])}</span>
        <input
          type="range"
          min={0}
          max={last}
          value={Math.max(endIdx, 0)}
          onChange={(e) => onChange((s) => ({ ...s, playing: false, endIdx: Number(e.target.value) }))}
          aria-label="Date"
          className="flex-1 min-w-0 accent-secondary"
        />
        <span className="hidden sm:inline text-[11px] text-text-muted">{formatDay(dates[last])}</span>
        <label className="flex items-center gap-1 text-xs text-text-muted flex-shrink-0">
          <span className="hidden sm:inline">Speed</span>
          <select
            value={speed}
            onChange={(e) => onChange((s) => ({ ...s, speed: e.target.value }))}
            aria-label="Play speed"
            className="bg-bg-raised border border-border rounded-lg px-1.5 py-1 text-xs"
          >
            {SPEEDS.map((sp) => <option key={sp.key} value={sp.key}>{sp.label}</option>)}
          </select>
        </label>
      </div>
    </div>
  )
}
