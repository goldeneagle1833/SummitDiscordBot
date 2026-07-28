import { useState, useEffect, useCallback } from 'react'
import { get } from '@/api/client'
import Spinner from '@/components/ui/Spinner'

const PER_PAGE = 50

const DESTRUCTIVE = new Set([
  'reset_elo', 'remove_match', 'remove_player', 'remove_community',
  'web_reset_all_elo', 'web_remove_player', 'web_remove_bot_match', 'web_remove_web_match',
])
const MODIFY = new Set([
  'correct_match', 'spot_elo_reset', 'recalculate_event_elo', 'start_event', 'end_event',
  'refresh_streamers', 'web_start_event', 'web_end_event', 'web_reset_elo', 'web_rename_player',
])

function ActionBadge({ action }) {
  const cls = DESTRUCTIVE.has(action)
    ? 'bg-accent-red/20 text-accent-red'
    : MODIFY.has(action)
    ? 'bg-yellow-500/20 text-yellow-400'
    : 'bg-accent-green/20 text-accent-green'
  return (
    <span className={`text-xs font-mono px-1.5 py-0.5 rounded whitespace-nowrap ${cls}`}>
      {action}
    </span>
  )
}

function StateCell({ value }) {
  if (!value) return <span className="opacity-40">-</span>
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 1)
  return (
    <pre className="text-xs text-text-muted max-w-[150px] overflow-auto whitespace-pre-wrap leading-tight">
      {text}
    </pre>
  )
}

export default function AuditLogTable() {
  const [entries, setEntries] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback((p) => {
    setLoading(true)
    setError(null)
    const offset = (p - 1) * PER_PAGE
    get(`/api/admin/audit-log?limit=${PER_PAGE}&offset=${offset}`)
      .then(d => {
        setEntries(d.entries ?? [])
        setTotal(d.total ?? 0)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load(1) }, [load])

  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE))

  const changePage = (p) => {
    setPage(p)
    load(p)
    window.scrollTo({ top: document.getElementById('audit-log-section')?.offsetTop ?? 0, behavior: 'smooth' })
  }

  return (
    <section id="audit-log-section" className="space-y-4">
      {total > 0 && <div className="text-xs text-text-muted">{total} total entries</div>}

      {loading ? (
        <Spinner className="py-8" />
      ) : error ? (
        <p className="text-accent-red text-sm">{error}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs" style={{ minWidth: 900 }}>
            <thead>
              <tr className="border-b border-border text-text-muted text-left">
                <th className="py-2 px-2">#</th>
                <th className="py-2 px-2 whitespace-nowrap">Time</th>
                <th className="py-2 px-2">Admin</th>
                <th className="py-2 px-2">Action</th>
                <th className="py-2 px-2">Target</th>
                <th className="py-2 px-2">Previous State</th>
                <th className="py-2 px-2">New State</th>
                <th className="py-2 px-2">Details</th>
              </tr>
            </thead>
            <tbody>
              {entries.length > 0 ? entries.map((e) => (
                <tr key={e.id} className="border-b border-border/50 hover:bg-bg-surface/50 align-top">
                  <td className="py-2 px-2 text-text-muted">{e.id}</td>
                  <td className="py-2 px-2 text-text-muted whitespace-nowrap">
                    {e.timestamp?.slice(0, 19).replace('T', ' ')}
                  </td>
                  <td className="py-2 px-2 whitespace-nowrap">{e.admin_name || '-'}</td>
                  <td className="py-2 px-2">
                    <ActionBadge action={e.action} />
                  </td>
                  <td className="py-2 px-2">
                    {e.target_name ? (
                      <div>
                        <div>{e.target_name}</div>
                        {e.target_id && (
                          <div className="text-text-muted opacity-60">ID: {e.target_id}</div>
                        )}
                      </div>
                    ) : e.target_id ? (
                      <span>{e.target_id}</span>
                    ) : (
                      <span className="opacity-40">-</span>
                    )}
                  </td>
                  <td className="py-2 px-2">
                    <StateCell value={e.previous_state} />
                  </td>
                  <td className="py-2 px-2">
                    <StateCell value={e.new_state} />
                  </td>
                  <td className="py-2 px-2 text-text-muted">{e.details || '-'}</td>
                </tr>
              )) : (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-text-muted">
                    No audit log entries.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 mt-4">
          <button
            disabled={page === 1}
            onClick={() => changePage(1)}
            className="px-3 py-1.5 text-xs bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40 disabled:cursor-not-allowed"
          >
            First
          </button>
          <button
            disabled={page === 1}
            onClick={() => changePage(page - 1)}
            className="px-3 py-1.5 text-xs bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40 disabled:cursor-not-allowed"
          >
            &larr; Prev
          </button>
          <span className="text-xs font-medium">Page {page} of {totalPages}</span>
          <button
            disabled={page === totalPages}
            onClick={() => changePage(page + 1)}
            className="px-3 py-1.5 text-xs bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Next &rarr;
          </button>
          <button
            disabled={page === totalPages}
            onClick={() => changePage(totalPages)}
            className="px-3 py-1.5 text-xs bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Last
          </button>
          <span className="text-xs text-text-muted ml-2">
            {((page - 1) * PER_PAGE) + 1}–{Math.min(page * PER_PAGE, total)} of {total}
          </span>
        </div>
      )}
    </section>
  )
}
