import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { getAvatarFilters, getAvatarTopPlayers } from '@/api/cards'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

const SORT_OPTIONS = [
  { value: 'avatar_score', label: 'Avatar Score' },
  { value: 'winrate', label: 'Win Rate' },
  { value: 'wins', label: 'Wins' },
  { value: 'games', label: 'Games' },
  { value: 'record', label: 'Record +/-' },
]

function sortPlayers(players, sortBy) {
  const sorted = [...players]
  if (players.some((player) => player.event_elo != null)) {
    return sorted.sort((a, b) => b.event_elo - a.event_elo || a.name.localeCompare(b.name))
  }
  switch (sortBy) {
    case 'winrate':
      return sorted.sort((a, b) => b.win_rate - a.win_rate || b.total - a.total)
    case 'wins':
      return sorted.sort((a, b) => b.wins - a.wins || b.win_rate - a.win_rate)
    case 'games':
      return sorted.sort((a, b) => b.total - a.total || b.avatar_score - a.avatar_score)
    case 'record':
      return sorted.sort((a, b) => (b.wins - b.losses) - (a.wins - a.losses) || b.total - a.total)
    case 'avatar_score':
    default:
      return sorted.sort((a, b) => b.avatar_score - a.avatar_score || b.win_rate - a.win_rate)
  }
}

function getWinRateClass(winRate) {
  if (winRate >= 60) return 'text-emerald-400'
  if (winRate >= 50) return 'text-amber-300'
  return 'text-rose-300'
}

export default function AvatarTopPlayers() {
  usePageTitle('Top Avatar Players')

  const [data, setData] = useState({ avatars: [] })
  const [filters, setFilters] = useState({ events: [] })
  const [filtersReady, setFiltersReady] = useState(false)
  const [selectedAvatar, setSelectedAvatar] = useState('')
  const [eventFilter, setEventFilter] = useState('all')
  const [sourceFilter, setSourceFilter] = useState('discord')
  const [sortBy, setSortBy] = useState('avatar_score')
  const [minGames, setMinGames] = useState(10)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getAvatarFilters()
      .then((result) => {
        setFilters(result)
        if (result.active_event?.avatar_specific) {
          setEventFilter('current')
          setSourceFilter('discord')
        }
      })
      .catch(() => {})
      .finally(() => setFiltersReady(true))
  }, [])

  useEffect(() => {
    if (!filtersReady) return
    setLoading(true)
    setError(null)
    getAvatarTopPlayers({
      source: sourceFilter,
      event: eventFilter,
      min_games: minGames,
      limit: 16,
    })
      .then((result) => {
        const avatars = result.avatars || []
        setData({ ...result, avatars })
        setSelectedAvatar((current) => {
          if (avatars.some((avatar) => avatar.name === current)) return current
          return avatars[0]?.name || ''
        })
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [eventFilter, sourceFilter, minGames, filtersReady])

  const selected = useMemo(
    () => data.avatars.find((avatar) => avatar.name === selectedAvatar) || data.avatars[0],
    [data.avatars, selectedAvatar],
  )
  const avatarOptions = useMemo(
    () => [...data.avatars].sort((a, b) => a.name.localeCompare(b.name)),
    [data.avatars],
  )
  const players = useMemo(
    () => sortPlayers(selected?.players || [], sortBy).map((player, index) => ({ ...player, displayRank: index + 1 })),
    [selected, sortBy],
  )
  const isEventElo = data.ranking === 'event_elo'
  const selectedEventConfig = (filters.events || []).find((event) => (
    eventFilter === 'current'
      ? event.is_active
      : String(event.event_id) === String(eventFilter)
  ))
  const isAvatarEloFilter = Boolean(selectedEventConfig?.avatar_specific)

  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      <div className="mb-4">
        <Link to="/avatars" className="text-sm text-primary hover:underline">&larr; Back to Avatar Win Rates</Link>
      </div>

      <section className="text-center mb-6">
        <h1 className="text-2xl font-display text-secondary">Top 16 Players by Avatar</h1>
        <p className="text-sm text-text-muted mt-1">
          {isEventElo
            ? `${data.event_info?.is_active ? 'Current ' : ''}${data.event_info?.event_name || 'Event'} standings, ranked by avatar ELO.`
            : 'Pick an avatar to see its strongest pilots ranked by Avatar Score.'}
        </p>
      </section>

      <div className="bg-bg-surface border border-border rounded-soft p-4 mb-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          <label className="block">
            <span className="text-xs uppercase tracking-wide text-text-muted">Avatar</span>
            <select
              value={selectedAvatar}
              onChange={(e) => setSelectedAvatar(e.target.value)}
              className="mt-1 w-full bg-bg-elevated border border-border rounded px-2 py-2 text-sm"
            >
              {avatarOptions.map((avatar) => (
                <option key={avatar.name} value={avatar.name}>{avatar.name}</option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="text-xs uppercase tracking-wide text-text-muted">Event</span>
            <select
              value={eventFilter}
              onChange={(e) => {
                const nextEvent = e.target.value
                const eventConfig = (filters.events || []).find((event) => (
                  nextEvent === 'current'
                    ? event.is_active
                    : String(event.event_id) === nextEvent
                ))
                setEventFilter(nextEvent)
                if (eventConfig?.avatar_specific && sourceFilter === 'all') {
                  setSourceFilter('discord')
                }
              }}
              className="mt-1 w-full bg-bg-elevated border border-border rounded px-2 py-2 text-sm"
            >
              <option value="all">All Events</option>
              {(filters.events || []).map((ev) => (
                <option key={ev.event_id || 'current'} value={ev.is_active ? 'current' : String(ev.event_id)}>
                  {ev.event_name}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="text-xs uppercase tracking-wide text-text-muted">Source</span>
            <select
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value)}
              className="mt-1 w-full bg-bg-elevated border border-border rounded px-2 py-2 text-sm"
            >
              <option value="discord">Online</option>
              <option value="web">Paper</option>
              {!isAvatarEloFilter && <option value="all">All Sources</option>}
            </select>
          </label>

          {!isEventElo && <label className="block">
            <span className="text-xs uppercase tracking-wide text-text-muted">Sort</span>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="mt-1 w-full bg-bg-elevated border border-border rounded px-2 py-2 text-sm"
            >
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>}

          {!isEventElo && <label className="block">
            <span className="text-xs uppercase tracking-wide text-text-muted">Min Games</span>
            <input
              type="number"
              min="1"
              max="100"
              value={minGames}
              onChange={(e) => setMinGames(Number(e.target.value) || 1)}
              className="mt-1 w-full bg-bg-elevated border border-border rounded px-2 py-2 text-sm"
            />
          </label>}
        </div>
      </div>

      {loading ? (
        <Spinner className="py-20" />
      ) : !selected ? (
        <p className="text-center text-text-muted py-10">No avatar player records found for these filters.</p>
      ) : (
        <section className="bg-bg-surface border border-border rounded-soft overflow-hidden">
          <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-3 p-4 border-b border-border">
            <div>
              <h2 className="text-xl font-display text-text-primary">{selected.name}</h2>
              <p className="text-sm text-text-muted">
                {isEventElo
                  ? `${players.length} ranked ${players.length === 1 ? 'player' : 'players'} in this event`
                  : `Avatar total: ${selected.wins}W-${selected.losses}L, ${selected.win_rate}% WR, Score ${selected.avatar_score}`}
              </p>
            </div>
            <Link
              to={`/avatar/${encodeURIComponent(selected.name)}`}
              className="text-sm text-primary hover:underline"
            >
              View avatar profile
            </Link>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-bg-elevated border-b border-border">
                <tr>
                  <th className="px-3 py-3 text-left text-xs uppercase tracking-wide text-text-muted">Rank</th>
                  <th className="px-3 py-3 text-left text-xs uppercase tracking-wide text-text-muted">Player</th>
                  {isEventElo ? (
                    <>
                      <th className="px-3 py-3 text-right text-xs uppercase tracking-wide text-text-muted">Event ELO</th>
                      <th className="px-3 py-3 text-right text-xs uppercase tracking-wide text-text-muted">Overall Rank</th>
                      <th className="px-3 py-3 text-right text-xs uppercase tracking-wide text-text-muted">Record</th>
                      <th className="px-3 py-3 text-right text-xs uppercase tracking-wide text-text-muted">Qualification</th>
                    </>
                  ) : (
                    <>
                      <th className="px-3 py-3 text-right text-xs uppercase tracking-wide text-text-muted">Avatar Score</th>
                      <th className="px-3 py-3 text-right text-xs uppercase tracking-wide text-text-muted">Record</th>
                      <th className="px-3 py-3 text-right text-xs uppercase tracking-wide text-text-muted">Win Rate</th>
                      <th className="px-3 py-3 text-right text-xs uppercase tracking-wide text-text-muted">Games</th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {players.map((player) => (
                  <tr key={player.player_id} className="hover:bg-bg-elevated transition-colors">
                    <td className="px-3 py-3 font-semibold text-text-muted">#{player.displayRank}</td>
                    <td className="px-3 py-3">
                      <Link to={`/player/${player.player_id}`} className="text-primary hover:underline font-semibold">
                        {player.name}
                      </Link>
                    </td>
                    {isEventElo ? (
                      <>
                        <td className="px-3 py-3 text-right font-bold text-secondary">{player.event_elo}</td>
                        <td className="px-3 py-3 text-right text-text-muted">#{player.ladder_rank}</td>
                        <td className="px-3 py-3 text-right">
                          {player.wins}W-{player.losses}L ({player.games}g)
                        </td>
                        <td className="px-3 py-3 text-right">
                          {player.qualification_path === 'avatar_leader' ? (
                            <span className="text-emerald-400 font-semibold">Avatar Leader</span>
                          ) : player.qualification_path === 'overall' ? (
                            <span className="text-primary font-semibold">Overall</span>
                          ) : player.qualification_path === 'fallback' ? (
                            <span className="text-amber-300 font-semibold">ELO Fallback</span>
                          ) : player.absolute_avatar_leader ? (
                            <span className="text-text-muted">
                              {player.qualification_reasons.includes('needs_three_ranked_games')
                                ? `${Math.max(0, 3 - player.games)} more game${Math.max(0, 3 - player.games) === 1 ? '' : 's'}`
                                : player.qualification_reasons.includes('needs_positive_win_rate')
                                  ? 'Needs positive record'
                                  : player.qualification_reasons.includes('already_qualified_overall')
                                    ? 'Already qualified'
                                    : 'Not eligible'}
                            </span>
                          ) : (
                            <span className="text-text-muted">—</span>
                          )}
                        </td>
                      </>
                    ) : (
                      <>
                        <td className="px-3 py-3 text-right font-bold text-secondary">{player.avatar_score}</td>
                        <td className="px-3 py-3 text-right">{player.wins}W-{player.losses}L</td>
                        <td className={`px-3 py-3 text-right font-semibold ${getWinRateClass(player.win_rate)}`}>{player.win_rate}%</td>
                        <td className="px-3 py-3 text-right text-text-muted">{player.total}</td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {isEventElo && !loading && (data.projected_top_cut || []).length > 0 && (
        <section className="mt-6 bg-bg-surface border border-border rounded-soft overflow-hidden">
          <div className="p-4 border-b border-border">
            <h2 className="text-xl font-display text-text-primary">Projected Top Cut</h2>
            <p className="text-sm text-text-muted mt-1">
              First 16 unique players by the overall ladder, then up to eight eligible absolute avatar leaders, with remaining seats falling back to ELO.
            </p>
            {!data.top_cut_eligibility_applied && (
              <p className="text-xs text-amber-300 mt-2">
                Provisional ladder view: ticket eligibility is applied by admins when the top cut is locked.
              </p>
            )}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-bg-elevated border-b border-border">
                <tr>
                  <th className="px-3 py-3 text-left text-xs uppercase tracking-wide text-text-muted">Seat</th>
                  <th className="px-3 py-3 text-left text-xs uppercase tracking-wide text-text-muted">Player</th>
                  <th className="px-3 py-3 text-left text-xs uppercase tracking-wide text-text-muted">Qualifying Avatar</th>
                  <th className="px-3 py-3 text-right text-xs uppercase tracking-wide text-text-muted">ELO</th>
                  <th className="px-3 py-3 text-right text-xs uppercase tracking-wide text-text-muted">Path</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.projected_top_cut.map((seat) => (
                  <tr key={seat.player_id} className="hover:bg-bg-elevated transition-colors">
                    <td className="px-3 py-3 font-semibold text-text-muted">#{seat.seat}</td>
                    <td className="px-3 py-3">
                      <Link to={`/player/${seat.player_id}`} className="text-primary hover:underline font-semibold">
                        {seat.player_name}
                      </Link>
                    </td>
                    <td className="px-3 py-3">{seat.qualifying_avatar}</td>
                    <td className="px-3 py-3 text-right font-bold text-secondary">{seat.qualifying_elo}</td>
                    <td className="px-3 py-3 text-right text-text-muted">
                      {seat.qualification_path === 'avatar_leader'
                        ? 'Avatar Leader'
                        : seat.qualification_path === 'fallback'
                          ? 'ELO Fallback'
                          : 'Overall'}
                      {seat.requires_tiebreak ? ' — Tiebreak required' : ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}
