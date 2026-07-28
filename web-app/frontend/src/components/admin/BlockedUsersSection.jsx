import { useState, useEffect, useCallback } from 'react'
import { get } from '@/api/client'
import Spinner from '@/components/ui/Spinner'

const PER_PAGE = 50

function formatDate(value) {
  if (!value) return '-'
  const d = new Date(value.includes('T') ? value : value.replace(' ', 'T') + 'Z')
  if (isNaN(d.getTime())) return value
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export default function BlockedUsersSection() {
  const [entries, setEntries] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback((p) => {
    setLoading(true)
    setError(null)
    const offset = (p - 1) * PER_PAGE
    get(`/api/admin/blocked-users?limit=${PER_PAGE}&offset=${offset}`)
      .then(d => {
        setEntries(d.entries ?? [])
        setTotal(d.total ?? 0)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load(page) }, [load, page])

  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE))

  return (
    <section className="space-y-4">
      <div className="bg-bg-raised border border-border rounded-lg overflow-hidden">
        {loading ? (
          <div className="flex justify-center py-8"><Spinner /></div>
        ) : error ? (
          <div className="px-4 py-6 text-sm text-accent-red">{error}</div>
        ) : entries.length === 0 ? (
          <div className="px-4 py-6 text-sm text-text-muted">No blocked users recorded.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-text-muted border-b border-border">
                  <th className="px-4 py-2 font-medium">Blocked User</th>
                  <th className="px-4 py-2 font-medium">Blocked By</th>
                  <th className="px-4 py-2 font-medium">Reason</th>
                  <th className="px-4 py-2 font-medium whitespace-nowrap">Date</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e, i) => (
                  <tr
                    key={`${e.blocker_id}-${e.blocked_id}-${i}`}
                    className="border-b border-border/50 last:border-b-0 hover:bg-bg-elevated/50"
                  >
                    <td className="px-4 py-2">
                      <div className="text-text-primary">{e.blocked_name}</div>
                      <div className="text-xs text-text-muted font-mono">{e.blocked_id}</div>
                    </td>
                    <td className="px-4 py-2">
                      <div className="text-text-primary">{e.blocker_name}</div>
                      <div className="text-xs text-text-muted font-mono">{e.blocker_id}</div>
                    </td>
                    <td className="px-4 py-2 text-text-muted max-w-[240px]">
                      {e.reason ? (
                        <span className="whitespace-pre-wrap break-words">{e.reason}</span>
                      ) : (
                        <span className="opacity-40">-</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-xs text-text-muted whitespace-nowrap">
                      {formatDate(e.created_at)}
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
