import { useState, useEffect, useCallback } from 'react'
import { get, post } from '@/api/client'
import Spinner from '@/components/ui/Spinner'

const PER_PAGE = 50

// Matches KUDOS_REASONS in discord-bot/cogs/lfg/player_kudos.py
const REASON_LABELS = {
  good_sport: 'Good sport, win or lose',
  friendly: 'Friendly and fun to play with',
  great_voice: 'Great to talk with on voice',
  helpful: 'Helped me learn or explained a rule',
  good_pace: 'Played at a good pace',
  fair_play: 'Honest and fair, reported the result right',
  great_game: 'Great game, well played',
}

function formatDate(value) {
  if (!value) return '-'
  const d = new Date(value.includes('T') ? value : value.replace(' ', 'T') + 'Z')
  if (isNaN(d.getTime())) return value
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export default function PlayerKudosSection() {
  const [entries, setEntries] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busyId, setBusyId] = useState(null)

  const load = useCallback((p) => {
    setLoading(true)
    setError(null)
    get(`/api/admin/player-kudos?limit=${PER_PAGE}&offset=${(p - 1) * PER_PAGE}`)
      .then(d => {
        setEntries(d.entries ?? [])
        setTotal(d.total ?? 0)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load(page) }, [load, page])

  const toggleHidden = (entry) => {
    setBusyId(entry.id)
    post(`/api/admin/player-kudos/${entry.id}/hidden`, { hidden: !entry.hidden })
      .then(() => setEntries(list => list.map(e => (e.id === entry.id ? { ...e, hidden: !e.hidden } : e))))
      .catch(e => setError(e.message))
      .finally(() => setBusyId(null))
  }

  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE))

  return (
    <section className="space-y-4">
      <div className="bg-bg-raised border border-border rounded-lg overflow-hidden">
        {loading ? (
          <div className="flex justify-center py-8"><Spinner /></div>
        ) : error ? (
          <div className="px-4 py-6 text-sm text-accent-red">{error}</div>
        ) : entries.length === 0 ? (
          <div className="px-4 py-6 text-sm text-text-muted">No applause yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-text-muted border-b border-border">
                  <th className="px-4 py-2 font-medium">Player</th>
                  <th className="px-4 py-2 font-medium">From</th>
                  <th className="px-4 py-2 font-medium">Why</th>
                  <th className="px-4 py-2 font-medium">Message</th>
                  <th className="px-4 py-2 font-medium whitespace-nowrap">Date</th>
                  <th className="px-4 py-2 font-medium">Homepage</th>
                </tr>
              </thead>
              <tbody>
                {entries.map(e => (
                  <tr
                    key={e.id}
                    className={`border-b border-border/50 last:border-b-0 hover:bg-bg-elevated/50 align-top ${e.hidden ? 'opacity-50' : ''}`}
                  >
                    <td className="px-4 py-2">
                      <div className="text-text-primary">{e.receiver_name}</div>
                      <div className="text-xs text-text-muted font-mono">{e.receiver_id}</div>
                    </td>
                    <td className="px-4 py-2">
                      <div className="text-text-primary">{e.giver_name}</div>
                      <div className="text-xs text-text-muted font-mono">{e.giver_id}</div>
                      {e.anonymous && <div className="text-xs mt-1 opacity-70">Name hidden on the site</div>}
                    </td>
                    <td className="px-4 py-2 text-text-muted">
                      {e.reasons?.length ? (
                        <ul className="list-disc pl-4 space-y-0.5">
                          {e.reasons.map(r => <li key={r}>{REASON_LABELS[r] ?? r}</li>)}
                        </ul>
                      ) : (
                        <span className="opacity-40">-</span>
                      )}
                      {e.source === 'sorcery-online' && (
                        <div className="text-xs mt-1 opacity-70">via Play Sorcery Online</div>
                      )}
                    </td>
                    <td className="px-4 py-2 text-text-muted max-w-[280px]">
                      {e.message ? (
                        <span className="whitespace-pre-wrap break-words">{e.message}</span>
                      ) : (
                        <span className="opacity-40">-</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-xs text-text-muted whitespace-nowrap">
                      {formatDate(e.created_at)}
                    </td>
                    <td className="px-4 py-2">
                      <button
                        onClick={() => toggleHidden(e)}
                        disabled={busyId === e.id}
                        className="px-2.5 py-1 text-xs border border-border rounded hover:bg-bg-elevated disabled:opacity-40 whitespace-nowrap"
                      >
                        {e.hidden ? 'Show again' : 'Hide'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center gap-3 text-sm">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page <= 1 || loading}
            className="px-3 py-1 border border-border rounded hover:bg-bg-elevated disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-xs text-text-muted">Page {page} of {totalPages}</span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages || loading}
            className="px-3 py-1 border border-border rounded hover:bg-bg-elevated disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </section>
  )
}
