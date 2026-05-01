import { useState, useEffect } from 'react'
import { get } from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

function StatCard({ title, children }) {
  return (
    <div className="bg-bg-surface border border-border rounded-lg p-4">
      <h3 className="text-base font-semibold text-text-primary mb-3">{title}</h3>
      {children}
    </div>
  )
}

function RankTable({ headers, rows }) {
  if (!rows?.length) return <p className="text-sm text-text-muted text-center py-3">No data.</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left">
            <th className="py-1.5 px-2 text-text-muted font-semibold w-8">#</th>
            {headers.map((h) => (
              <th key={h} className="py-1.5 px-2 text-text-muted font-semibold">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-border/50">
              <td className="py-1.5 px-2 text-text-muted">{i + 1}</td>
              {row.map((cell, j) => (
                <td key={j} className="py-1.5 px-2">{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function WinStreaks({ data }) {
  const [view, setView] = useState('best')
  if (!data?.best?.length && !data?.active?.length) return null

  return (
    <StatCard title="Win Streaks">
      <div className="inline-flex bg-bg-raised border border-border rounded-lg overflow-hidden mb-3">
        <button onClick={() => setView('best')} className={`px-3 py-1 text-xs font-medium transition-colors ${view === 'best' ? 'bg-secondary text-white' : 'text-text-muted hover:text-text-primary'}`}>
          Best All-Time
        </button>
        <button onClick={() => setView('active')} className={`px-3 py-1 text-xs font-medium transition-colors ${view === 'active' ? 'bg-secondary text-white' : 'text-text-muted hover:text-text-primary'}`}>
          Active Streaks
        </button>
      </div>
      {view === 'best' ? (
        <RankTable
          headers={['Player', 'Best', 'Current']}
          rows={(data.best || []).map((p) => [
            p.name,
            <span key="b" className="font-medium">{p.best_streak}</span>,
            p.current_streak > 0 ? <span key="c" className="text-accent-green">{p.current_streak}</span> : '-',
          ])}
        />
      ) : (
        <RankTable
          headers={['Player', 'Streak']}
          rows={(data.active || []).map((p) => [
            p.name,
            <span key="s" className="text-accent-green font-medium">{p.current_streak}</span>,
          ])}
        />
      )}
    </StatCard>
  )
}

function MostDiverse({ data }) {
  if (!data?.length) return null
  return (
    <StatCard title="Most Diverse">
      <RankTable
        headers={['Player', 'Avatars', 'Used']}
        rows={data.map((p) => [
          p.name,
          <span key="n" className="font-medium">{p.unique_avatars}</span>,
          <span key="a" className="text-xs text-text-muted">{(p.avatars || []).join(', ')}</span>,
        ])}
      />
    </StatCard>
  )
}

function MostActive({ data }) {
  if (!data?.length) return null
  return (
    <StatCard title="Most Active">
      <RankTable
        headers={['Player', 'Games', 'Record']}
        rows={data.map((p) => [
          p.name,
          <span key="g" className="font-medium">{p.games}</span>,
          <span key="r"><span className="text-accent-green">{p.wins}</span>{'-'}<span className="text-accent-red">{p.losses}</span></span>,
        ])}
      />
    </StatCard>
  )
}

function BiggestUpsets({ data }) {
  if (!data?.length) return null
  return (
    <StatCard title="Biggest Upsets">
      <RankTable
        headers={['Player', 'ELO Gained']}
        rows={data.map((m) => [
          m.winner_name,
          <span key="e" className="text-accent-green font-medium">+{m.elo_change}</span>,
        ])}
      />
    </StatCard>
  )
}

function NemesisPairs({ data }) {
  if (!data?.length) return null
  return (
    <StatCard title="Nemesis Pairs">
      <RankTable
        headers={['Player', '', 'Player', 'Games', 'H2H']}
        rows={data.map((p) => [
          p.player1_name,
          <span key="vs" className="text-text-muted">vs</span>,
          p.player2_name,
          <span key="e" className="font-medium">{p.encounters}</span>,
          `${p.p1_wins}-${p.p2_wins}`,
        ])}
      />
    </StatCard>
  )
}

function MatchDuration({ data }) {
  if (!data) return null
  return (
    <StatCard title="Match Duration">
      <div className="text-center py-2">
        <div className="text-3xl font-display text-secondary">{data.average_minutes} min</div>
        <div className="text-xs text-text-muted mb-4">Average match time</div>
        <div className="grid grid-cols-3 gap-4">
          <div>
            <div className="text-lg font-semibold text-text-primary">{data.fastest_minutes} min</div>
            <div className="text-xs text-text-muted">Fastest</div>
          </div>
          <div>
            <div className="text-lg font-semibold text-text-primary">{data.longest_minutes} min</div>
            <div className="text-xs text-text-muted">Longest</div>
          </div>
          <div>
            <div className="text-lg font-semibold text-text-primary">{data.total_with_data}</div>
            <div className="text-xs text-text-muted">Matches</div>
          </div>
        </div>
      </div>
    </StatCard>
  )
}

function MostImproved({ data }) {
  if (!data?.length) return null
  return (
    <StatCard title={<>Most Improved <span className="text-xs text-text-muted font-normal">Last 7 Days</span></>}>
      <RankTable
        headers={['Player', 'ELO']}
        rows={data.map((p) => [
          p.name,
          <span key="e" className="text-accent-green font-medium">+{p.elo_change}</span>,
        ])}
      />
    </StatCard>
  )
}

function IronmanStreak({ data }) {
  if (!data?.length) return null
  return (
    <StatCard title="Ironman Streak">
      <RankTable
        headers={['Player', 'Streak']}
        rows={data.map((p) => [
          p.name,
          <span key="d" className="font-medium">{p.consecutive_days} days</span>,
        ])}
      />
    </StatCard>
  )
}

export default function FunStats() {
  usePageTitle('Fun Stats')
  const [stats, setStats] = useState(null)
  const [filters, setFilters] = useState(null)
  const [eventFilter, setEventFilter] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    get('/api/fun-stats/filters').then(setFilters).catch(() => {})
  }, [])

  useEffect(() => {
    setLoading(true)
    const params = new URLSearchParams()
    if (eventFilter) params.set('event', eventFilter)
    if (sourceFilter) params.set('source', sourceFilter)
    const qs = params.toString()
    get(`/api/fun-stats${qs ? '?' + qs : ''}`)
      .then((d) => { setStats(d.stats); setError(null) })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [eventFilter, sourceFilter])

  return (
    <div className="space-y-6">
      {/* Hero */}
      <div className="text-center py-6">
        <h1 className="text-3xl font-display text-secondary">Fun Stats</h1>
        <p className="text-text-muted mt-1">Community records, rivalries, and bragging rights</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4 justify-center">
        <div className="flex items-center gap-2">
          <label className="text-sm text-text-muted">Event</label>
          <select
            value={eventFilter}
            onChange={(e) => setEventFilter(e.target.value)}
            className="bg-bg-raised border border-border rounded px-3 py-1.5 text-sm"
          >
            <option value="">Current</option>
            {filters?.events?.map((ev) => (
              <option key={ev.event_id} value={ev.event_id}>
                {ev.event_name}{ev.is_active ? ' (Active)' : ''}
              </option>
            ))}
            <option value="all">All Time</option>
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-text-muted">Source</label>
          <select
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
            className="bg-bg-raised border border-border rounded px-3 py-1.5 text-sm"
          >
            <option value="">All Sources</option>
            {filters?.sources?.map((src) => (
              <option key={src} value={src}>{src}</option>
            ))}
          </select>
        </div>
      </div>

      {loading && <Spinner className="py-12" />}
      {error && <p className="text-center text-accent-red py-8">{error}</p>}

      {stats && !loading && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <WinStreaks data={stats.win_streaks} />
          <MostActive data={stats.most_active} />
          <MatchDuration data={stats.match_duration} />
          <BiggestUpsets data={stats.biggest_upsets} />
          <NemesisPairs data={stats.nemesis_pairs} />
          <MostDiverse data={stats.most_diverse} />
          <MostImproved data={stats.most_improved} />
          <IronmanStreak data={stats.ironman_streak} />
        </div>
      )}
    </div>
  )
}
