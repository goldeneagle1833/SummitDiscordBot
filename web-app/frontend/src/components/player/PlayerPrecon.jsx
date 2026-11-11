import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getPreconPlayer } from '@/api/leaderboard'
import { preconSeasonText } from '@/components/leaderboard/PreconLadderContent'

const LABEL = { lavamancer: 'Lavamancer', frostmage: 'Frostmage' }
const SHORT = { lavamancer: 'LM', frostmage: 'FM' }
const TINT = { lavamancer: 'text-orange-300', frostmage: 'text-sky-300' }

/** The player's precon ladder results, or null until loaded / when they have none. */
export function usePreconPlayer(playerId) {
  const [data, setData] = useState(null)
  useEffect(() => {
    let active = true
    setData(null)
    getPreconPlayer(playerId)
      .then((d) => { if (active) setData(d) })
      .catch(() => { if (active) setData(null) })
    return () => { active = false }
  }, [playerId])
  return data
}

function PreconTag({ precon }) {
  if (!precon) return <span className="text-text-muted">-</span>
  return <span className={`font-semibold ${TINT[precon] || ''}`} title={LABEL[precon]}>{SHORT[precon]}</span>
}

/** One card per LM / FM ladder the player has played in. */
export function PreconStandings({ data }) {
  const seasons = data?.seasons || []
  if (!seasons.length) return null
  const minGames = data.min_ranked_games || 5
  return (
    <section className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold text-text-primary">LM / FM precon ladder</h3>
        <p className="text-xs text-text-muted">Lavamancer vs Frostmage, rated with Glicko-2. One rating per player.</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {seasons.map(({ season, standing, ranked_players: rankedPlayers }) => (
          <div key={season.season_id} className="bg-bg-surface border border-border rounded-soft p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <Link to={`/elo?board=precon:${season.season_id}`} className="font-semibold text-white hover:text-primary">
                  {season.name}
                </Link>
                <p className="text-xs text-text-muted mt-0.5">{preconSeasonText(season)}</p>
              </div>
              {season.is_open && (
                <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-green-900/30 text-green-400">Live</span>
              )}
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2 text-center">
              <div>
                <div className="text-2xl font-display text-secondary">{standing.rating}</div>
                <div className="text-[11px] text-text-muted">Rating</div>
              </div>
              <div>
                <div className="text-2xl font-display text-white">
                  {standing.ranked ? `#${standing.rank}` : '–'}
                </div>
                <div className="text-[11px] text-text-muted">
                  {standing.ranked ? `of ${rankedPlayers}` : `${standing.games}/${minGames} games`}
                </div>
              </div>
              <div>
                <div className="text-2xl font-display">
                  <span className="text-accent-green">{standing.wins}</span>-<span className="text-accent-red">{standing.losses}</span>
                </div>
                <div className="text-[11px] text-text-muted">W-L</div>
              </div>
            </div>
            <div className="mt-3 flex justify-center gap-6 text-sm">
              <span className="text-orange-300">LM {standing.lm_wins}-{standing.lm_losses}</span>
              <span className="text-sky-300">FM {standing.fm_wins}-{standing.fm_losses}</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function firstLabel(value) {
  const v = String(value || '').toLowerCase()
  if (v.startsWith('y')) return 'Play'
  if (v.startsWith('n')) return 'Draw'
  return '-'
}

/** Precon games for the Matches tab (shown above casual games). */
export function PreconMatchHistory({ data }) {
  const games = data?.games || []
  if (!games.length) return null
  return (
    <section>
      <h3 className="text-lg font-semibold text-text-primary mb-1">Precon (LM/FM) Match History</h3>
      <p className="text-xs text-text-muted mb-3">Lavamancer vs Frostmage ladder games. These only move the precon ladder rating.</p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm" style={{ minWidth: 640 }}>
          <thead>
            <tr className="border-b border-border text-left">
              <th className="py-2 px-2 text-text-muted font-semibold w-16">ID</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Result</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Played</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Opponent</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Rating</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Replay</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Play/Draw</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Date</th>
            </tr>
          </thead>
          <tbody>
            {games.map((g) => {
              const change = g.rating_after != null && g.rating_before != null ? g.rating_after - g.rating_before : null
              return (
                <tr key={g.match_id} className="border-b border-border/50 hover:bg-bg-elevated transition-colors">
                  <td className="py-2 px-2 text-text-muted text-xs">P{g.match_id}</td>
                  <td className={`py-2 px-3 font-semibold ${g.won ? 'text-accent-green' : 'text-accent-red'}`}>{g.won ? 'Win' : 'Loss'}</td>
                  <td className="py-2 px-3"><PreconTag precon={g.precon} /></td>
                  <td className="py-2 px-3">
                    <Link to={`/player/${g.opponent_id}`} className="hover:text-primary">{g.opponent_name}</Link>
                    {' '}<span className="text-xs"><PreconTag precon={g.opponent_precon} /></span>
                  </td>
                  <td className={`py-2 px-3 font-medium ${change == null ? 'text-text-muted' : change >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>
                    {change == null ? 'unrated' : `${change >= 0 ? '+' : ''}${change}`}
                  </td>
                  <td className="py-2 px-3 text-text-muted">
                    {g.replay_url ? (
                      <a href={g.replay_url} target="_blank" rel="noopener noreferrer" className="text-secondary hover:underline text-xs">
                        Watch
                      </a>
                    ) : '-'}
                  </td>
                  <td className="py-2 px-3 text-text-muted">{firstLabel(g.went_first)}</td>
                  <td className="py-2 px-3 text-text-muted whitespace-nowrap">
                    {g.timestamp ? new Date(g.timestamp).toLocaleDateString() : '-'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
