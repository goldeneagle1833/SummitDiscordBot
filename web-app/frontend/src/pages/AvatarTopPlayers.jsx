import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getAvatarFilters, getAvatarTopPlayers } from '@/api/cards'
import { getAvatarLeaderboards } from '@/api/leaderboard'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

// Season Elo reads the running season's per-avatar ladder (Avatar-mode seasons only)
const ELO_SORT = { value: 'elo', label: 'Season Elo' }

const SORT_OPTIONS = [
  { value: 'avatar_score', label: 'Avatar Score' },
  { value: 'winrate', label: 'Win Rate' },
  { value: 'wins', label: 'Wins' },
  { value: 'games', label: 'Games' },
  { value: 'record', label: 'Record +/-' },
]

function sortPlayers(players, sortBy) {
  const sorted = [...players]
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

function SeasonEloTable({ avatar, entry }) {
  if (!entry) {
    return <p className="text-center text-text-muted py-10">No rated games on {avatar || 'this avatar'} this season yet.</p>
  }
  return (
    <section className="bg-bg-surface border border-border rounded-soft overflow-hidden">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-3 p-4 border-b border-border">
        <div>
          <h2 className="text-xl font-display text-text-primary">{avatar}</h2>
          <p className="text-sm text-text-muted">
            {entry.players} player{entry.players === 1 ? '' : 's'} rated on {avatar} this season
          </p>
        </div>
        <Link to={`/avatar/${encodeURIComponent(avatar)}`} className="text-sm text-primary hover:underline">
          View avatar profile
        </Link>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-bg-elevated border-b border-border">
            <tr>
              <th className="px-3 py-3 text-left text-xs uppercase tracking-wide text-text-muted">Rank</th>
              <th className="px-3 py-3 text-left text-xs uppercase tracking-wide text-text-muted">Player</th>
              <th className="px-3 py-3 text-right text-xs uppercase tracking-wide text-text-muted">Season Elo</th>
              <th className="px-3 py-3 text-right text-xs uppercase tracking-wide text-text-muted">Record</th>
              <th className="px-3 py-3 text-right text-xs uppercase tracking-wide text-text-muted">Win Rate</th>
              <th className="px-3 py-3 text-right text-xs uppercase tracking-wide text-text-muted">Games</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {entry.entries.map((player) => {
              const winRate = player.games ? Math.round((player.wins / player.games) * 1000) / 10 : 0
              return (
                <tr key={player.user_id} className="hover:bg-bg-elevated transition-colors">
                  <td className="px-3 py-3 font-semibold text-text-muted">#{player.rank}</td>
                  <td className="px-3 py-3">
                    <Link to={`/player/${player.user_id}`} className="text-primary hover:underline font-semibold">
                      {player.display_name}
                    </Link>
                  </td>
                  <td className="px-3 py-3 text-right font-bold text-secondary">{player.elo}</td>
                  <td className="px-3 py-3 text-right">{player.wins}W-{player.losses}L</td>
                  <td className={`px-3 py-3 text-right font-semibold ${getWinRateClass(winRate)}`}>{winRate}%</td>
                  <td className="px-3 py-3 text-right text-text-muted">{player.games}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function getWinRateClass(winRate) {
  if (winRate >= 60) return 'text-emerald-400'
  if (winRate >= 50) return 'text-amber-300'
  return 'text-rose-300'
}

export default function AvatarTopPlayers() {
  usePageTitle('Top Avatar Players')

  // ?avatar=<name>&event=<season> opens the page on one avatar and season (the
  // home leaderboard links here). With no season given it shows the running
  // season, or all seasons between seasons.
  const [searchParams, setSearchParams] = useSearchParams()
  const [data, setData] = useState({ avatars: [] })
  const [filters, setFilters] = useState({ events: [] })
  const [selectedAvatar, setSelectedAvatarState] = useState(() => searchParams.get('avatar') || '')
  const [eventFilter, setEventFilterState] = useState(() => searchParams.get('event') || 'current')
  const [sourceFilter, setSourceFilter] = useState('discord')
  // null = the page's default: Season Elo during an Avatar-mode season, else Avatar Score
  const [sortChoice, setSortChoice] = useState(() => searchParams.get('sort'))
  const [minGames, setMinGames] = useState(10)
  const [eloBoard, setEloBoard] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Keep the choice in the URL so the view can be shared or bookmarked
  const updateParam = (key, value, fallback) => {
    setSearchParams((params) => {
      const next = new URLSearchParams(params)
      if (value && value !== fallback) next.set(key, value)
      else next.delete(key)
      return next
    }, { replace: true })
  }
  const setSelectedAvatar = (value) => {
    setSelectedAvatarState(value)
    updateParam('avatar', value, '')
  }
  const setEventFilter = (value) => {
    setEventFilterState(value)
    updateParam('event', value, 'current')
  }
  const setSortBy = (value) => {
    setSortChoice(value)
    updateParam('sort', value, '')
  }

  // The running season's per-avatar Elo ladder, the same one the home page ranks by
  useEffect(() => {
    getAvatarLeaderboards()
      .then(setEloBoard)
      .catch(() => setEloBoard(null))
  }, [])

  const eloAvailable = eventFilter === 'current' && eloBoard?.elo_mode === 'avatar'
  const sortOptions = eloAvailable ? [ELO_SORT, ...SORT_OPTIONS] : SORT_OPTIONS
  const sortBy = sortOptions.some((option) => option.value === sortChoice)
    ? sortChoice
    : eloAvailable ? 'elo' : 'avatar_score'
  const eloMode = sortBy === 'elo'

  useEffect(() => {
    // The current season is public on this page (the home leaderboard links here)
    getAvatarFilters({ include_active: 1 })
      .then((result) => {
        setFilters(result)
        // Between seasons there's no current one to default to
        const hasCurrent = (result.events || []).some((ev) => ev.is_active)
        if (!hasCurrent) setEventFilterState((value) => (value === 'current' ? 'all' : value))
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    setLoading(true)
    setError(null)
    getAvatarTopPlayers({
      source: sourceFilter,
      event: eventFilter,
      min_games: minGames,
      limit: 16,
    })
      .then((result) => {
        setData({ ...result, avatars: result.avatars || [] })
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [eventFilter, sourceFilter, minGames])

  // Season Elo lists every avatar with a rated game this season; the other
  // sorts list avatars with a player past the minimum games
  const avatarNames = useMemo(() => {
    const source = eloMode ? eloBoard?.avatars || [] : data.avatars
    return source.map((avatar) => avatar.avatar || avatar.name).sort((a, b) => a.localeCompare(b))
  }, [eloMode, eloBoard, data.avatars])
  const avatarName = avatarNames.includes(selectedAvatar) ? selectedAvatar : avatarNames[0] || ''

  const selected = useMemo(
    () => data.avatars.find((avatar) => avatar.name === avatarName),
    [data.avatars, avatarName],
  )
  const eloEntry = useMemo(
    () => (eloBoard?.avatars || []).find((avatar) => avatar.avatar === avatarName),
    [eloBoard, avatarName],
  )
  const players = useMemo(
    () => sortPlayers(selected?.players || [], sortBy).map((player, index) => ({ ...player, displayRank: index + 1 })),
    [selected, sortBy],
  )

  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      <div className="mb-4">
        <Link to="/avatars" className="text-sm text-primary hover:underline">&larr; Back to Avatar Win Rates</Link>
      </div>

      <section className="text-center mb-6">
        <h1 className="text-2xl font-display text-secondary">
          {eloMode ? 'Season Elo by Avatar' : 'Top 16 Players by Avatar'}
        </h1>
        <p className="text-sm text-text-muted mt-1">
          {eloMode
            ? 'Every player rated on an avatar this season, ranked by their season Elo on it.'
            : 'Pick an avatar to see its strongest pilots ranked by Avatar Score.'}
        </p>
      </section>

      <div className="bg-bg-surface border border-border rounded-soft p-4 mb-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          <label className="block">
            <span className="text-xs uppercase tracking-wide text-text-muted">Avatar</span>
            <select
              value={avatarName}
              onChange={(e) => setSelectedAvatar(e.target.value)}
              className="mt-1 w-full bg-bg-elevated border border-border rounded px-2 py-2 text-sm"
            >
              {avatarNames.map((name) => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="text-xs uppercase tracking-wide text-text-muted">Season</span>
            <select
              value={eventFilter}
              onChange={(e) => setEventFilter(e.target.value)}
              className="mt-1 w-full bg-bg-elevated border border-border rounded px-2 py-2 text-sm"
            >
              <option value="all">All Seasons</option>
              {[...(filters.events || [])].sort((a, b) => Number(b.is_active) - Number(a.is_active)).map((ev) => (
                <option key={ev.event_id || 'current'} value={ev.is_active ? 'current' : String(ev.event_id)}>
                  {ev.is_active ? `${ev.event_name} (current)` : ev.event_name}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="text-xs uppercase tracking-wide text-text-muted">Source</span>
            <select
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value)}
              disabled={eloMode}
              title={eloMode ? 'Season Elo is the ranked ladder (online games)' : undefined}
              className="mt-1 w-full bg-bg-elevated border border-border rounded px-2 py-2 text-sm disabled:opacity-50"
            >
              <option value="discord">Online</option>
              <option value="all">All Sources</option>
            </select>
          </label>

          <label className="block">
            <span className="text-xs uppercase tracking-wide text-text-muted">Sort</span>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="mt-1 w-full bg-bg-elevated border border-border rounded px-2 py-2 text-sm"
            >
              {sortOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="text-xs uppercase tracking-wide text-text-muted">Min Games</span>
            <input
              type="number"
              min="1"
              max="100"
              value={minGames}
              onChange={(e) => setMinGames(Number(e.target.value) || 1)}
              disabled={eloMode}
              title={eloMode ? 'Season Elo lists every rated player' : undefined}
              className="mt-1 w-full bg-bg-elevated border border-border rounded px-2 py-2 text-sm disabled:opacity-50"
            />
          </label>
        </div>
      </div>

      {eloMode ? (
        <SeasonEloTable avatar={avatarName} entry={eloEntry} />
      ) : loading ? (
        <Spinner className="py-20" />
      ) : !selected ? (
        <p className="text-center text-text-muted py-10">No avatar player records found for these filters.</p>
      ) : (
        <section className="bg-bg-surface border border-border rounded-soft overflow-hidden">
          <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-3 p-4 border-b border-border">
            <div>
              <h2 className="text-xl font-display text-text-primary">{selected.name}</h2>
              <p className="text-sm text-text-muted">
                Avatar total: {selected.wins}W-{selected.losses}L, {selected.win_rate}% WR, Score {selected.avatar_score}
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
                  <th className="px-3 py-3 text-right text-xs uppercase tracking-wide text-text-muted">Avatar Score</th>
                  <th className="px-3 py-3 text-right text-xs uppercase tracking-wide text-text-muted">Record</th>
                  <th className="px-3 py-3 text-right text-xs uppercase tracking-wide text-text-muted">Win Rate</th>
                  <th className="px-3 py-3 text-right text-xs uppercase tracking-wide text-text-muted">Games</th>
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
                    <td className="px-3 py-3 text-right font-bold text-secondary">{player.avatar_score}</td>
                    <td className="px-3 py-3 text-right">{player.wins}W-{player.losses}L</td>
                    <td className={`px-3 py-3 text-right font-semibold ${getWinRateClass(player.win_rate)}`}>{player.win_rate}%</td>
                    <td className="px-3 py-3 text-right text-text-muted">{player.total}</td>
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
