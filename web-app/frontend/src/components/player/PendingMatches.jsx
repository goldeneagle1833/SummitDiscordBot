import { useState } from 'react'
import { Link } from 'react-router-dom'

export default function PendingMatches({ matches, playerId, isOwner, onDispute }) {
  if (!matches?.length) return null

  const [disputingId, setDisputingId] = useState(null)
  const [disputeError, setDisputeError] = useState(null)

  const handleDispute = async (confirmationId) => {
    setDisputingId(confirmationId)
    setDisputeError(null)
    try {
      const resp = await fetch(`/api/match-report/deny/${confirmationId}`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'Disputed from player profile' }),
      })
      if (resp.ok) {
        if (onDispute) onDispute()
      } else {
        const data = await resp.json()
        setDisputeError(data?.error?.message || 'Failed to dispute')
      }
    } catch {
      setDisputeError('Network error')
    } finally {
      setDisputingId(null)
    }
  }

  const formatTimeLeft = (expiresAt) => {
    const now = Math.floor(Date.now() / 1000)
    const diff = expiresAt - now
    if (diff <= 0) return 'Expiring soon'
    const hours = Math.floor(diff / 3600)
    const mins = Math.floor((diff % 3600) / 60)
    if (hours > 0) return `${hours}h ${mins}m left`
    return `${mins}m left`
  }

  return (
    <section>
      <h3 className="text-lg font-semibold text-text-primary mb-1">Pending Match Reports</h3>
      <p className="text-xs text-text-muted mb-3">
        These matches are awaiting confirmation. They will auto-confirm when the timer expires.
      </p>

      {disputeError && (
        <p className="text-xs text-accent-red mb-2">{disputeError}</p>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm" style={{ minWidth: 500 }}>
          <thead>
            <tr className="border-b border-border text-left">
              <th className="py-2 px-3 text-text-muted font-semibold">Result</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Opponent</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Source</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Auto-confirm</th>
              {isOwner && <th className="py-2 px-3 text-text-muted font-semibold">Action</th>}
            </tr>
          </thead>
          <tbody>
            {matches.map((m) => (
              <tr key={m.confirmation_id} className="border-b border-border/50 hover:bg-bg-surface/50">
                <td className="py-2 px-3">
                  <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${
                    m.result === 'Win'
                      ? 'bg-accent-green/20 text-accent-green'
                      : 'bg-accent-red/20 text-accent-red'
                  }`}>
                    {m.result}
                  </span>
                </td>
                <td className="py-2 px-3">
                  <Link
                    to={`/player/${m.opponent_id}`}
                    className="text-text-primary hover:text-accent-blue transition-colors"
                  >
                    {m.opponent_name}
                  </Link>
                </td>
                <td className="py-2 px-3 text-text-muted text-xs">{m.source}</td>
                <td className="py-2 px-3 text-text-muted text-xs">
                  <span className="inline-flex items-center gap-1 text-amber-400">
                    <span className="inline-block w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                    {formatTimeLeft(m.expires_at)}
                  </span>
                </td>
                {isOwner && (
                  <td className="py-2 px-3">
                    <button
                      onClick={() => handleDispute(m.confirmation_id)}
                      disabled={disputingId === m.confirmation_id}
                      className="text-xs px-2 py-1 rounded bg-accent-red/20 text-accent-red hover:bg-accent-red/30 transition-colors disabled:opacity-50"
                    >
                      {disputingId === m.confirmation_id ? 'Disputing...' : 'Dispute'}
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
