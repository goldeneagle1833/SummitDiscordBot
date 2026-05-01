import StatCard from './StatCard'

export default function OverallStats({ data, stats, statsType, onStatsTypeChange }) {
  return (
    <section>
      <div className="flex items-center gap-3 mb-3">
        <h3 className="text-lg font-semibold text-text-primary">Overall Stats</h3>
        <div className="inline-flex bg-bg-raised border border-border rounded-lg overflow-hidden">
          <button
            onClick={() => onStatsTypeChange('ranked')}
            className={`px-3 py-1 text-xs font-medium transition-colors ${
              statsType === 'ranked' ? 'bg-secondary text-white' : 'text-text-muted hover:text-text-primary'
            }`}
          >
            Ranked
          </button>
          <button
            onClick={() => onStatsTypeChange('casual')}
            className={`px-3 py-1 text-xs font-medium transition-colors ${
              statsType === 'casual' ? 'bg-secondary text-white' : 'text-text-muted hover:text-text-primary'
            }`}
          >
            Casual
          </button>
        </div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <StatCard label="Wins" value={stats?.wins ?? '-'} />
        <StatCard label="Losses" value={stats?.losses ?? '-'} />
        <StatCard label="Win Rate" value={stats?.win_rate != null ? `${stats.win_rate}%` : '-'} />
        <StatCard label="Total Matches" value={statsType === 'casual' ? (stats?.total ?? '-') : (data.wins + data.losses || '-')} />
        <StatCard label="Avg Match Time" value={stats?.avg_match_time ? `${stats.avg_match_time} min` : '-'} />
        {stats?.on_play_matches > 0 && (
          <StatCard label="On the Play" value={`${stats.on_play_win_rate}% (${stats.on_play_wins}/${stats.on_play_matches})`} />
        )}
        {stats?.on_draw_matches > 0 && (
          <StatCard label="On the Draw" value={`${stats.on_draw_win_rate}% (${stats.on_draw_wins}/${stats.on_draw_matches})`} />
        )}
      </div>
    </section>
  )
}
