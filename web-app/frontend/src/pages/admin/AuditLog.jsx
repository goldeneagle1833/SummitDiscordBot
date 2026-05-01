import { useState, useEffect } from 'react'
import { get } from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

export default function AuditLog() {
  usePageTitle('Admin Audit Log')
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    get('/api/admin/audit-log')
      .then(setEntries)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      <h1 className="text-2xl font-display text-secondary mb-4">Audit Log</h1>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="py-2 px-3 font-semibold text-text-muted">Timestamp</th>
              <th className="py-2 px-3 font-semibold text-text-muted">User</th>
              <th className="py-2 px-3 font-semibold text-text-muted">Action</th>
              <th className="py-2 px-3 font-semibold text-text-muted">Details</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry, idx) => (
              <tr key={idx} className="border-b border-border/50 hover:bg-bg-surface/50">
                <td className="py-2 px-3 text-text-muted whitespace-nowrap">{entry.timestamp}</td>
                <td className="py-2 px-3">{entry.user || entry.admin || '-'}</td>
                <td className="py-2 px-3 font-medium">{entry.action}</td>
                <td className="py-2 px-3 text-text-muted">{entry.details || '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {entries.length === 0 && (
        <p className="text-center text-text-muted py-8">No audit log entries.</p>
      )}
    </div>
  )
}
