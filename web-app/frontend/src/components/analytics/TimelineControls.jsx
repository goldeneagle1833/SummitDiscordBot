import { useEffect } from 'react'

export const WINDOWS = [
  { key: '7', label: '7 days', days: 7 },
  { key: '30', label: '30 days', days: 30 },
  { key: '90', label: '90 days', days: 90 },
  { key: 'all', label: 'All time', days: null },
]

// Playback: one step every PLAY_TICK_MS, about PLAY_STEPS steps start to end
export const PLAY_TICK_MS = 220
const PLAY_STEPS = 150

export const windowDays = (key) => WINDOWS.find((w) => w.key === key)?.days ?? null

export function formatDay(iso) {
  if (!iso) return ''
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

/**
 * One date slider, play button and window picker that drives every chart on
 * the page. The parent owns the state: { windowKey, endIdx, playing }.
 */
export default function TimelineControls({ dates, windowKey, endIdx, playing, onChange }) {
  const last = dates.length - 1
  const days = windowDays(windowKey)

  // Play steps the slider from where it is to the latest day
  useEffect(() => {
    if (!playing) return undefined
    const step = Math.max(1, Math.round(dates.length / PLAY_STEPS))
    const id = setInterval(() => onChange((s) => ({ ...s, endIdx: Math.min(s.endIdx + step, last) })), PLAY_TICK_MS)
    return () => clearInterval(id)
  }, [playing, dates.length, last, onChange])

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
        <div className="flex flex-wrap gap-2">
          {WINDOWS.map((w) => (
            <button
              key={w.key}
              type="button"
              onClick={() => onChange((s) => ({ ...s, windowKey: w.key }))}
              className={`px-3 py-1 text-xs font-medium rounded-lg border transition-colors ${windowKey === w.key ? 'bg-primary text-bg border-primary' : 'bg-bg-raised text-text-muted border-border hover:text-text'}`}
            >
              {w.label}
            </button>
          ))}
        </div>
        <p className="text-sm text-text" data-testid="timeline-range">
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
      </div>
    </div>
  )
}
