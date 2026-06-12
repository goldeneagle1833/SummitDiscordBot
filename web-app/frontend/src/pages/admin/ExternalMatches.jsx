import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { get } from '@/api/client'
import usePageTitle from '@/hooks/usePageTitle'
import Spinner from '@/components/ui/Spinner'

function formatTime(seconds) {
  if (!seconds) return '-'
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return s > 0 ? `${m}m ${s}s` : `${m}m`
}

export default function ExternalMatches() {
  usePageTitle('External Matches')
  const [matches, setMatches] = useState([])
  const [pagination, setPagination] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [page, setPage] = useState(1)

  useEffect(() => {
    setLoading(true)
    get(`/api/admin/external-matches?page=${page}&per_page=50`)
      .then(d => {
        if (d.success) {
          setMatches(d.matches)
          setPagination(d.pagination)
        } else {
          setError(d.error || 'Failed to load')
        }
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [page])

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/admin/audit-log" className="text-text-muted hover:text-secondary transition-colors text-sm">&larr; Admin</Link>
        <div>
          <h1 className="text-2xl font-display text-secondary">External Matches</h1>
          <p className="text-sm text-text-muted">Matches reported by third-party platforms. These do not affect ELO ratings.</p>
        </div>
      </div>

      {pagination && (
        <div className="bg-bg-raised border border-border rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-secondary">{pagination.total_matches.toLocaleString()}</div>
          <div className="text-xs text-text-muted mt-1">Total External Matches</div>
        </div>
      )}

      {loading ? <Spinner className="py-12" /> : error ? (
        <p className="text-text-muted text-sm py-8 text-center">Error: {error}</p>
      ) : matches.length === 0 ? (
        <p className="text-text-muted text-sm py-8 text-center">No external matches recorded yet.</p>
      ) : (
        <div className="bg-bg-raised border border-border rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm" style={{ minWidth: 600 }}>
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="py-2 px-3 text-text-muted font-semibold">Winner</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Loser</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Source</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">First</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Time</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Date</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Comment</th>
                </tr>
              </thead>
              <tbody>
                {matches.map((m) => (
                  <tr key={m.id} className="border-b border-border/50 hover:bg-bg-surface/50">
                    <td className="py-2 px-3 text-accent-green font-semibold whitespace-nowrap">
                      {m.winner_display_name || m.winner_id}
                    </td>
                    <td className="py-2 px-3 text-accent-red whitespace-nowrap">
                      {m.loser_display_name || m.loser_id}
                    </td>
                    <td className="py-2 px-3 text-text-muted text-xs">{m.source || '-'}</td>
                    <td className="py-2 px-3 text-text-muted text-xs">
                      {m.winner_went_first === 'y' ? 'Winner' : m.winner_went_first === 'n' ? 'Loser' : '-'}
                    </td>
                    <td className="py-2 px-3 text-text-muted">{formatTime(m.match_time)}</td>
                    <td className="py-2 px-3 text-text-muted whitespace-nowrap">
                      {m.timestamp ? new Date(m.timestamp).toLocaleDateString() : '-'}
                    </td>
                    <td className="py-2 px-3 text-text-muted text-xs max-w-[200px] truncate" title={m.match_comment || ''}>
                      {m.match_comment || '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {pagination && pagination.total_pages > 1 && (
        <div className="flex items-center justify-center gap-3">
          <button
            disabled={!pagination.has_previous}
            onClick={() => setPage(1)}
            className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40 disabled:cursor-not-allowed"
          >
            First
          </button>
          <button
            disabled={!pagination.has_previous}
            onClick={() => setPage(p => p - 1)}
            className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40 disabled:cursor-not-allowed"
          >
            &larr; Prev
          </button>
          <span className="text-sm font-medium">
            Page {pagination.current_page} of {pagination.total_pages}
          </span>
          <button
            disabled={!pagination.has_next}
            onClick={() => setPage(p => p + 1)}
            className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Next &rarr;
          </button>
          <button
            disabled={!pagination.has_next}
            onClick={() => setPage(pagination.total_pages)}
            className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Last
          </button>
          <span className="text-xs text-text-muted ml-2">
            {((pagination.current_page - 1) * pagination.per_page) + 1}-{Math.min(pagination.current_page * pagination.per_page, pagination.total_matches)} of {pagination.total_matches}
          </span>
        </div>
      )}
    </div>
  )
}
