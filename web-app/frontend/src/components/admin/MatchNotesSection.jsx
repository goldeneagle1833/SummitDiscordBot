import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getMatchesWithNotes } from '@/api/admin'

const SOURCE_LABEL = {
  online: 'Online',
  paper: 'Paper',
  archive: 'Archive',
}

export default function MatchNotesSection() {
  const [matches, setMatches] = useState([])
  const [pagination, setPagination] = useState(null)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const data = await getMatchesWithNotes(page, 50)
        if (cancelled) return
        setMatches(data.matches || [])
        setPagination(data.pagination || null)
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load')
      }
      if (!cancelled) setLoading(false)
    }
    load()
    return () => { cancelled = true }
  }, [page])

  const handlePageChange = (p) => {
    setPage(p)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <section className="space-y-4">
      {error && (
        <p className="text-sm text-accent-red">{error}</p>
      )}

      {loading ? (
        <p className="text-sm text-text-muted py-4 text-center">Loading...</p>
      ) : matches.length === 0 ? (
        <p className="text-sm text-text-muted py-4 text-center">No matches with notes found.</p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" style={{ minWidth: 700 }}>
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="py-2 px-3 text-text-muted font-semibold">ID</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Winner</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Loser</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">ELO</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Time</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Date</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Source</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Notes</th>
                </tr>
              </thead>
              <tbody>
                {matches.map((m, idx) => (
                  <tr key={`${m.match_id}-${m.source}-${idx}`} className="border-b border-border/50 hover:bg-bg-surface/50">
                    <td className="py-2 px-3 text-text-muted">#{m.match_id}</td>
                    <td className="py-2 px-3">
                      <Link to={`/player/${m.winner_id}`} className="text-secondary hover:underline">
                        {m.winner_name || m.winner_id}
                      </Link>
                    </td>
                    <td className="py-2 px-3">
                      <Link to={`/player/${m.loser_id}`} className="text-secondary hover:underline">
                        {m.loser_name || m.loser_id}
                      </Link>
                    </td>
                    <td className="py-2 px-3 text-text-muted">
                      <span className="text-accent-green">+{m.winner_elo_change}</span>
                      {' / '}
                      <span className="text-accent-red">{m.loser_elo_change}</span>
                    </td>
                    <td className="py-2 px-3 text-text-muted">{m.match_time ? `${m.match_time} min` : '-'}</td>
                    <td className="py-2 px-3 text-text-muted whitespace-nowrap">{m.date ? new Date(m.date).toLocaleDateString() : '-'}</td>
                    <td className="py-2 px-3">
                      <span className="text-xs px-1.5 py-0.5 rounded bg-bg-surface border border-border">
                        {SOURCE_LABEL[m.source] || m.source}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-text-muted max-w-[200px]">
                      <span className="relative group cursor-default">
                        <span className="truncate block max-w-[200px]">
                          {m.match_comment.split(/\s+/).slice(0, 5).join(' ')}{m.match_comment.split(/\s+/).length > 5 ? '...' : ''}
                        </span>
                        <span className="absolute z-20 hidden group-hover:block bg-bg-surface border border-border rounded px-3 py-2 text-xs text-text-primary shadow-lg whitespace-normal min-w-[200px] max-w-[400px] bottom-full left-0 mb-1">
                          {m.match_comment}
                        </span>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {pagination && pagination.total_pages > 1 && (
            <div className="flex items-center justify-center gap-3 mt-4">
              <button
                disabled={!pagination.has_previous}
                onClick={() => handlePageChange(1)}
                className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40 disabled:cursor-not-allowed"
              >
                First
              </button>
              <button
                disabled={!pagination.has_previous}
                onClick={() => handlePageChange(pagination.current_page - 1)}
                className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40 disabled:cursor-not-allowed"
              >
                &larr; Prev
              </button>
              <span className="text-sm font-medium">
                Page {pagination.current_page} of {pagination.total_pages}
              </span>
              <button
                disabled={!pagination.has_next}
                onClick={() => handlePageChange(pagination.current_page + 1)}
                className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Next &rarr;
              </button>
              <button
                disabled={!pagination.has_next}
                onClick={() => handlePageChange(pagination.total_pages)}
                className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Last
              </button>
              <span className="text-xs text-text-muted ml-2">
                {((pagination.current_page - 1) * pagination.per_page) + 1}-{Math.min(pagination.current_page * pagination.per_page, pagination.total_matches)} of {pagination.total_matches}
              </span>
            </div>
          )}
        </>
      )}
    </section>
  )
}
