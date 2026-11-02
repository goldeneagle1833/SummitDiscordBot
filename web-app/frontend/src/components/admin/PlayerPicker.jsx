import { useEffect, useRef, useState } from 'react'
import { searchPlayers } from '@/api/players'

/** A button that opens a Summit player search; picking one calls onPick(player). */
export default function PlayerPicker({ onPick, label = 'Pick player', buttonClassName = 'text-sm' }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const timer = useRef(null)

  useEffect(() => {
    clearTimeout(timer.current)
    if (q.trim().length < 2) {
      setResults([])
      return undefined
    }
    timer.current = setTimeout(() => {
      searchPlayers(q.trim())
        .then((res) => setResults(res.players || []))
        .catch(() => setResults([]))
    }, 250)
    return () => clearTimeout(timer.current)
  }, [q])

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className={`px-2.5 py-1 rounded-lg border border-border hover:border-secondary ${buttonClassName}`}>
        {label}
      </button>
    )
  }
  return (
    <div className="relative">
      <input
        autoFocus
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => e.key === 'Escape' && setOpen(false)}
        placeholder="Search Summit players..."
        className="h-9 w-56 rounded-lg border border-border bg-bg-raised px-3 text-sm text-text-primary"
      />
      {results.length > 0 && (
        <ul className="absolute z-20 mt-1 w-64 max-h-64 overflow-auto rounded-lg border border-border bg-bg-surface shadow-lg">
          {results.map((p) => (
            <li key={p.user_id}>
              <button
                type="button"
                onClick={() => {
                  setOpen(false)
                  setQ('')
                  onPick(p)
                }}
                className="w-full text-left px-3 py-2 text-sm hover:bg-white/5"
              >
                {p.display_name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
