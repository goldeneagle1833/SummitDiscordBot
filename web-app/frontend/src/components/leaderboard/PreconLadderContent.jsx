import { Link } from 'react-router-dom'
import { StatBox } from '@/components/leaderboard/LimitedLeaderboardContent'

const RANK_MEDALS = ['\u{1F947}', '\u{1F948}', '\u{1F949}']
const SHORT = { lavamancer: 'LM', frostmage: 'FM' }
// Fire and ice tints for the two precons (text only, no official art)
const PRECON_TINT = { lavamancer: 'text-orange-300', frostmage: 'text-sky-300' }

function formatDay(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

/** "Runs Nov 12 – Dec 10 · 3 days left" or "Ended Dec 10". */
export function preconSeasonText(season, now = new Date()) {
  if (!season) return ''
  const range = `${formatDay(season.starts_at)} – ${formatDay(season.last_day || season.ends_at)}`
  if (season.is_open) {
    const ms = new Date(season.ends_at).getTime() - now.getTime()
    const days = Math.max(0, Math.ceil(ms / 86400000))
    return `Runs ${range} · ${days === 1 ? '1 day' : `${days} days`} left`
  }
  if (new Date(season.starts_at).getTime() > now.getTime()) return `Starts ${formatDay(season.starts_at)}`
  return `Ended ${formatDay(season.last_day || season.ends_at)} · ${range}`
}

function Record({ wins, losses, muted = false }) {
  if (!wins && !losses) return <span className="text-text-muted">–</span>
  return (
    <span className={muted ? 'text-text-muted' : ''}>
      <span className="text-accent-green">{wins}</span>-<span className="text-accent-red">{losses}</span>
    </span>
  )
}

function winPct(row) {
  const games = (row.wins || 0) + (row.losses || 0)
  return games ? `${((row.wins / games) * 100).toFixed(0)}%` : '–'
}

function StandingsTable({ rows, unranked = false }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead className="border-b border-border">
          <tr>
            <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase tracking-wider w-12">#</th>
            <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase tracking-wider">Player</th>
            <th className="px-3 py-2 text-right text-xs font-semibold text-text-muted uppercase tracking-wider">Rating</th>
            <th className="px-3 py-2 text-right text-xs font-semibold text-text-muted uppercase tracking-wider">W-L</th>
            <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wider hidden sm:table-cell text-orange-300">LM</th>
            <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wider hidden sm:table-cell text-sky-300">FM</th>
            <th className="px-3 py-2 text-right text-xs font-semibold text-text-muted uppercase tracking-wider hidden sm:table-cell">Win %</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {rows.map((row) => (
            <tr key={row.user_id} className="hover:bg-bg-elevated transition-colors">
              <td className="px-3 py-2 text-sm text-text-muted">
                {unranked ? '–' : row.rank <= 3 ? RANK_MEDALS[row.rank - 1] : `#${row.rank}`}
              </td>
              <td className="px-3 py-2">
                <Link to={`/player/${row.user_id}`} className="text-sm font-medium hover:text-primary transition-colors">
                  {row.name}
                </Link>
                {/* Phone: the per-precon records fold under the name */}
                <div className="sm:hidden text-[11px] text-text-muted mt-0.5">
                  {(row.lm_wins || row.lm_losses) ? <span className="text-orange-300 mr-2">LM {row.lm_wins}-{row.lm_losses}</span> : null}
                  {(row.fm_wins || row.fm_losses) ? <span className="text-sky-300">FM {row.fm_wins}-{row.fm_losses}</span> : null}
                </div>
              </td>
              <td className={`px-3 py-2 text-sm text-right font-semibold ${unranked ? 'text-text-muted' : 'text-white'}`}>
                {row.rating}
              </td>
              <td className="px-3 py-2 text-sm text-right"><Record wins={row.wins} losses={row.losses} /></td>
              <td className="px-3 py-2 text-sm text-right hidden sm:table-cell"><Record wins={row.lm_wins} losses={row.lm_losses} /></td>
              <td className="px-3 py-2 text-sm text-right hidden sm:table-cell"><Record wins={row.fm_wins} losses={row.fm_losses} /></td>
              <td className="px-3 py-2 text-sm text-right hidden sm:table-cell">{winPct(row)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RecentGames({ games }) {
  if (!games?.length) return null
  return (
    <section className="mt-8">
      <h3 className="text-xl font-display text-secondary mb-3">Latest games</h3>
      <ul className="divide-y divide-border bg-bg-surface border border-border rounded-soft">
        {games.map((g) => (
          <li key={g.match_id} className="px-4 py-2.5 text-sm flex flex-wrap items-center gap-x-2 gap-y-1">
            <Link to={`/player/${g.winner_id}`} className="font-medium text-white hover:text-primary">{g.winner_display_name}</Link>
            {g.winner_precon && <span className={`text-xs font-semibold ${PRECON_TINT[g.winner_precon] || ''}`}>{SHORT[g.winner_precon]}</span>}
            <span className="text-text-muted">beat</span>
            <Link to={`/player/${g.loser_id}`} className="font-medium hover:text-primary">{g.loser_display_name}</Link>
            {g.loser_precon && <span className={`text-xs font-semibold ${PRECON_TINT[g.loser_precon] || ''}`}>{SHORT[g.loser_precon]}</span>}
            {g.winner_rating_after != null && (
              <span className="ml-auto text-xs text-text-muted">
                <span className="text-accent-green">+{g.winner_rating_after - g.winner_rating_before}</span>
                {' / '}
                <span className="text-accent-red">{g.loser_rating_after - g.loser_rating_before}</span>
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

/** The Lavamancer vs Frostmage ladder: stats, standings, unranked players, latest games. */
export function PreconLadder({ data }) {
  const season = data?.season
  if (!season) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-10 bg-bg-surface border border-border rounded-[10px] text-center">
        <h3 className="text-2xl font-display text-white mb-2">No precon ladder yet</h3>
        <p className="text-text-muted">
          The Lavamancer vs Frostmage ladder runs for four weeks at a time. Standings show up here once it starts.
        </p>
      </div>
    )
  }
  const standings = data.standings || []
  const ranked = standings.filter((r) => r.ranked)
  const unranked = standings.filter((r) => !r.ranked)
  const stats = data.stats || {}
  const matchup = stats.lm_vs_fm || {}
  const crossGames = (matchup.lm_wins || 0) + (matchup.fm_wins || 0)
  const minGames = data.min_ranked_games || 5

  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <StatBox label="Players" value={stats.players || 0} />
        <StatBox label="Games" value={stats.games || 0} />
        <StatBox label="LM wins vs FM" value={matchup.lm_wins || 0} />
        <StatBox label="FM wins vs LM" value={matchup.fm_wins || 0} />
      </div>
      {crossGames > 0 && (
        <div className="mb-6" aria-label="Lavamancer against Frostmage">
          <div className="flex justify-between text-xs font-semibold mb-1">
            <span className="text-orange-300">Lavamancer {Math.round((matchup.lm_wins / crossGames) * 100)}%</span>
            <span className="text-sky-300">Frostmage {Math.round((matchup.fm_wins / crossGames) * 100)}%</span>
          </div>
          <div className="h-2 rounded-full overflow-hidden flex bg-bg-elevated">
            <div className="bg-orange-400" style={{ width: `${(matchup.lm_wins / crossGames) * 100}%` }} />
            <div className="bg-sky-400 flex-1" />
          </div>
        </div>
      )}
      {ranked.length ? (
        <StandingsTable rows={ranked} />
      ) : (
        <p className="text-text-muted text-center py-6">
          Nobody has played {minGames} games yet. Players show up here once they have.
        </p>
      )}
      {unranked.length > 0 && (
        <section className="mt-8">
          <h3 className="text-xl font-display text-secondary mb-1">Not yet ranked</h3>
          <p className="text-sm text-text-muted mb-3">Players with fewer than {minGames} games this ladder.</p>
          <StandingsTable rows={unranked} unranked />
        </section>
      )}
      <RecentGames games={data.recent} />
      <p className="mt-6 text-xs text-text-muted leading-relaxed">
        One Glicko-2 rating per player, whichever precon they play; everyone starts at 1500. Queue with
        the 🧙 Precon (LM/FM) button in Discord or on Play Sorcery Online, and check your spot with <code>!precon</code>.
      </p>
    </div>
  )
}
