import { useMemo } from 'react'

const ELEMENTS = ['Air', 'Earth', 'Fire', 'Water']

export const EMPTY_PARTICIPANT_FILTERS = { q: '', avatar: '', elements: [], losses: '' }

/** Swiss record of one player, from the event's saved match history. */
export function swissRecord(entry) {
  if (!entry?.matches?.length) return null
  let wins = 0
  let losses = 0
  for (const m of entry.matches) {
    if (m.phase && m.phase !== 'Swiss') continue
    if (m.result === 'Win') wins += 1
    else if (m.result === 'Loss') losses += 1
  }
  return { wins, losses }
}

export function hasParticipantFilters(f) {
  return Boolean(f.q || f.avatar || f.elements.length || f.losses !== '')
}

/**
 * Filter the event's decks. Elements: the deck's (top two) elements must
 * include every picked element. Losses: Swiss losses at most N; players with
 * no match history only show when that filter is off.
 */
export function filterParticipants(decks, f, historyFor) {
  const q = f.q.trim().toLowerCase()
  const maxLosses = f.losses === '' ? null : Number(f.losses)
  return decks.filter((deck) => {
    if (q && !`${deck.player || ''} ${deck.deck_name || ''}`.toLowerCase().includes(q)) return false
    if (f.avatar && deck.avatar !== f.avatar) return false
    if (f.elements.length && !f.elements.every((el) => (deck.elements || []).includes(el))) return false
    if (maxLosses !== null) {
      const rec = swissRecord(historyFor(deck))
      if (!rec || rec.losses > maxLosses) return false
    }
    return true
  })
}

export default function ParticipantFilters({ decks, filters, onChange, shown, hasHistory }) {
  const avatars = useMemo(() => {
    const counts = {}
    for (const d of decks || []) if (d.avatar) counts[d.avatar] = (counts[d.avatar] || 0) + 1
    return Object.entries(counts).sort((a, b) => a[0].localeCompare(b[0]))
  }, [decks])

  const set = (patch) => onChange({ ...filters, ...patch })
  const toggleElement = (el) =>
    set({
      elements: filters.elements.includes(el)
        ? filters.elements.filter((e) => e !== el)
        : [...filters.elements, el],
    })
  const active = hasParticipantFilters(filters)
  const field = 'bg-bg-raised border border-border rounded px-2 py-1.5 text-sm text-text-primary'

  return (
    <div className="mb-3 space-y-2" data-testid="participant-filters">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        <input
          type="search"
          className={field}
          placeholder="Search player or deck"
          value={filters.q}
          onChange={(e) => set({ q: e.target.value })}
          aria-label="Search player or deck"
        />
        <select
          className={field}
          value={filters.avatar}
          onChange={(e) => set({ avatar: e.target.value })}
          aria-label="Avatar"
        >
          <option value="">All avatars</option>
          {avatars.map(([name, n]) => (
            <option key={name} value={name}>{name} ({n})</option>
          ))}
        </select>
        {hasHistory && (
          <select
            className={field}
            value={filters.losses}
            onChange={(e) => set({ losses: e.target.value })}
            aria-label="Swiss record"
          >
            <option value="">Any Swiss record</option>
            <option value="0">Undefeated in Swiss</option>
            <option value="1">1 loss or fewer</option>
            <option value="2">2 losses or fewer</option>
            <option value="3">3 losses or fewer</option>
          </select>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {ELEMENTS.map((el) => {
          const on = filters.elements.includes(el)
          return (
            <button
              key={el}
              type="button"
              onClick={() => toggleElement(el)}
              aria-pressed={on}
              className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                on ? 'bg-secondary text-black border-secondary' : 'bg-bg-raised text-text-muted border-border hover:text-text-primary'
              }`}
            >
              {el}
            </button>
          )
        })}
        <span className="text-xs text-text-muted ml-auto">
          Showing {shown} of {decks?.length || 0}
        </span>
        {active && (
          <button
            type="button"
            className="text-xs text-secondary hover:underline"
            onClick={() => onChange(EMPTY_PARTICIPANT_FILTERS)}
          >
            Clear filters
          </button>
        )}
      </div>
    </div>
  )
}
