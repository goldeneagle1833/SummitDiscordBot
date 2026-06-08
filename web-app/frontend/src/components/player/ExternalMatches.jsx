export default function ExternalMatches({ matches, stats, pagination, playerId, onPageChange }) {
  if (!matches?.length && !stats?.total) return null

  const formatTime = (seconds) => {
    if (!seconds) return '-'
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    return s > 0 ? `${m}m ${s}s` : `${m}m`
  }

  return (
    <section>
      <h3 className="text-lg font-semibold text-text-primary mb-1">External Matches</h3>
      <p className="text-xs text-text-muted mb-3">
        Matches reported by third-party platforms. These do not affect ELO ratings.
      </p>

      {stats && stats.total > 0 && (
        <div className="flex gap-4 mb-4 text-sm">
          <span className="text-text-muted">
            Record: <span className="text-accent-green font-semibold">{stats.wins}W</span>
            {' - '}
            <span className="text-accent-red font-semibold">{stats.losses}L</span>
          </span>
          <span className="text-text-muted">Win Rate: <span className="text-text-primary font-semibold">{stats.win_rate}%</span></span>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm" style={{ minWidth: 500 }}>
          <thead>
            <tr className="border-b border-border text-left">
              <th className="py-2 px-3 text-text-muted font-semibold">Result</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Opponent</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Source</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Time</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Date</th>
            </tr>
          </thead>
          <tbody>
            {matches.map((m) => {
              const isWin = m.did_win
              const opponent = isWin ? m.loser : m.winner
              return (
                <tr key={m.match_id} className="border-b border-border/50 hover:bg-bg-surface/50">
                  <td className="py-2 px-3">
                    <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${isWin ? 'bg-accent-green/20 text-accent-green' : 'bg-accent-red/20 text-accent-red'}`}>
                      {isWin ? 'Win' : 'Loss'}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-text-primary">{opponent}</td>
                  <td className="py-2 px-3 text-text-muted text-xs">{m.source || '-'}</td>
                  <td className="py-2 px-3 text-text-muted">{formatTime(m.match_time)}</td>
                  <td className="py-2 px-3 text-text-muted">{m.timestamp ? new Date(m.timestamp).toLocaleDateString() : '-'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {pagination && pagination.total_pages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-4">
          <button
            disabled={!pagination.has_previous}
            onClick={() => onPageChange(1)}
            className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40 disabled:cursor-not-allowed"
          >
            First
          </button>
          <button
            disabled={!pagination.has_previous}
            onClick={() => onPageChange(pagination.current_page - 1)}
            className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40 disabled:cursor-not-allowed"
          >
            &larr; Prev
          </button>
          <span className="text-sm font-medium">
            Page {pagination.current_page} of {pagination.total_pages}
          </span>
          <button
            disabled={!pagination.has_next}
            onClick={() => onPageChange(pagination.current_page + 1)}
            className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Next &rarr;
          </button>
          <button
            disabled={!pagination.has_next}
            onClick={() => onPageChange(pagination.total_pages)}
            className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Last
          </button>
          <span className="text-xs text-text-muted ml-2">
            {((pagination.current_page - 1) * pagination.per_page) + 1}-{Math.min(pagination.current_page * pagination.per_page, pagination.total_matches)} of {pagination.total_matches}
          </span>
        </div>
      )}
    </section>
  )
}
