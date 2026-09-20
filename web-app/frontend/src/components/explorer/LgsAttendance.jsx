import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'

function parseHistory(raw) {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/**
 * What the applicant's store actually drew over the last 9 months, next to
 * what they told us. Sourced from their sorcerytcg.com store link.
 */
export default function LgsAttendance({ application, onRefresh, refreshing }) {
  const history = parseHistory(application.lgs_history)
  const median = application.lgs_median_players
  const checked = Boolean(application.lgs_checked_at)

  const chartData = history.map((point) => ({
    date: point.date?.slice(5) || '',
    players: point.player_count,
  }))

  return (
    <section className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-text-primary">Store attendance</h3>
        <button
          onClick={onRefresh}
          disabled={refreshing}
          className="text-xs text-primary hover:underline disabled:opacity-40"
        >
          {refreshing ? 'Checking…' : checked ? 'Re-check store' : 'Check store'}
        </button>
      </div>

      <div className="bg-bg-raised border border-border rounded-lg p-4 space-y-3">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-xs text-text-muted">They said</div>
            <div className="text-lg text-text-primary">
              {application.expected_attendance || application.avg_headcount || '—'}
            </div>
          </div>
          <div>
            <div className="text-xs text-text-muted">
              Actual median (last 9 months)
            </div>
            <div className="text-lg text-secondary">
              {median != null ? `${median} players` : '—'}
            </div>
          </div>
        </div>

        {application.lgs_store_name && (
          <div className="text-xs text-text-muted">
            {application.lgs_store_name} · {application.lgs_event_count || 0} event
            {application.lgs_event_count === 1 ? '' : 's'} in the window
          </div>
        )}

        {chartData.length > 1 ? (
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 5, right: 8, bottom: 0, left: -20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#ffffff14" />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#9ca3af' }} />
                <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    background: '#111827',
                    border: '1px solid #374151',
                    borderRadius: 6,
                    fontSize: 12,
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="players"
                  stroke="#f5c451"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="text-xs text-text-muted">
            {application.lgs_lookup_error
              || (checked
                ? 'Not enough events to chart.'
                : 'Not checked yet.')}
          </p>
        )}
      </div>
    </section>
  )
}
