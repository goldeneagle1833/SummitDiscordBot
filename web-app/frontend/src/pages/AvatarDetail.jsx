import { useState, useEffect, useMemo, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { get } from '@/api/client'
import { getAvatarFilters, getAvatarImageFiles } from '@/api/cards'
import { getAvatarImageSettings } from '@/api/admin'
import { useAuth } from '@/context/AuthContext'
import AvatarImageAdmin from '@/components/ui/AvatarImageAdmin'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

// ── Helpers ───────────────────────────────────────────────────

function getWinRateColor(pct) {
  const p = Math.max(0, Math.min(100, pct))
  if (p <= 50) {
    const r = p / 50
    return `rgb(${Math.round(231 + 24 * r)}, ${Math.round(76 + 179 * r)}, ${Math.round(60 + 195 * r)})`
  }
  const r = (p - 50) / 50
  return `rgb(${Math.round(255 - 209 * r)}, ${Math.round(255 - 51 * r)}, ${Math.round(255 - 142 * r)})`
}

function getMatchupClass(wr) {
  if (wr <= 40) return 'text-red-500'
  if (wr <= 50) return 'text-red-400'
  if (wr <= 60) return 'text-green-300'
  if (wr <= 70) return 'text-green-400'
  return 'text-green-500'
}

function getAvatarImagePath(name, files) {
  const norm = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, '')
  const n = norm(name)
  for (const f of files) { if (norm(f.replace(/\.\w+$/, '')) === n) return f }
  for (const f of files) { if (norm(f.replace(/\.\w+$/, '')).includes(n)) return f }
  for (const f of files) { if (n.includes(norm(f.replace(/\.\w+$/, '')))) return f }
  return null
}

const ELEMENT_COLORS = {
  Fire: { bar: 'from-red-600 to-red-800', text: 'text-red-500' },
  Water: { bar: 'from-blue-500 to-blue-700', text: 'text-blue-400' },
  Earth: { bar: 'from-amber-800 to-amber-950', text: 'text-amber-700' },
  Air: { bar: 'from-sky-300 to-sky-500', text: 'text-sky-300' },
}

function getElementStyle(elements) {
  const single = Object.keys(ELEMENT_COLORS).find((e) => elements.toLowerCase() === e.toLowerCase())
  if (single) return ELEMENT_COLORS[single]
  return { bar: 'from-purple-500 to-purple-700', text: 'text-purple-400' }
}

// ── Source Toggle ─────────────────────────────────────────────

const SOURCE_KEY = 'avatars_source_preference'

function SourceToggle({ source, onChange }) {
  return (
    <div className="inline-flex bg-bg-surface border border-border rounded-soft overflow-hidden">
      {[['discord', 'Online'], ['web', 'Paper']].map(([val, label]) => (
        <button
          key={val}
          onClick={() => onChange(val)}
          className={`px-4 py-1.5 text-xs font-medium transition-colors ${
            source === val ? 'bg-primary text-black' : 'text-text-muted hover:bg-bg-elevated hover:text-primary'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

// ── Stat Card ─────────────────────────────────────────────────

function StatCard({ value, label, sub }) {
  return (
    <div className="bg-bg-elevated rounded-soft p-4 text-center">
      <div className="text-xl font-bold text-secondary">{value}</div>
      <div className="text-xs text-text-muted mt-0.5">{label}</div>
      {sub && <div className="text-xs text-text-muted mt-1">{sub}</div>}
    </div>
  )
}

// ── Match History Table ───────────────────────────────────────

function MatchTable({ matches, emptyText }) {
  if (!matches?.length) return <p className="text-text-muted text-center py-4 text-sm">{emptyText}</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left">
            <th className="px-3 py-2 text-xs font-semibold text-text-muted uppercase">Winner</th>
            <th className="px-3 py-2 text-xs font-semibold text-text-muted uppercase">Loser</th>
            <th className="px-3 py-2 text-xs font-semibold text-text-muted uppercase">ELO</th>
          </tr>
        </thead>
        <tbody>
          {matches.map((m, i) => (
            <tr key={i} className="border-b border-border/50 hover:bg-bg-elevated/50 transition-colors">
              <td className="px-3 py-2">
                <Link to={`/player/${m.winner_id}`} className="hover:text-primary transition-colors">{m.winner_name}</Link>
              </td>
              <td className="px-3 py-2">
                <Link to={`/player/${m.loser_id}`} className="hover:text-primary transition-colors">{m.loser_name}</Link>
              </td>
              <td className="px-3 py-2 text-text-muted whitespace-nowrap">
                <span className="text-accent-green">+{m.winner_elo_change || 0}</span>
                {' / '}
                <span className="text-accent-red">{m.loser_elo_change || 0}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Matchups Table ────────────────────────────────────────────

function MatchupsSection({ avatarName, source, eventFilter }) {
  const [matchups, setMatchups] = useState(null)
  const [sortKey, setSortKey] = useState('total')
  const [sortAsc, setSortAsc] = useState(false)

  useEffect(() => {
    const params = new URLSearchParams({ source })
    if (eventFilter !== 'all') params.set('event', eventFilter)
    get(`/api/avatar/${encodeURIComponent(avatarName)}/matchups?${params}`)
      .then((data) => setMatchups(data.matchups || []))
      .catch(() => setMatchups([]))
  }, [avatarName, source, eventFilter])

  const sorted = useMemo(() => {
    if (!matchups) return []
    const d = [...matchups]
    d.sort((a, b) => sortAsc ? a[sortKey] - b[sortKey] : b[sortKey] - a[sortKey])
    return d
  }, [matchups, sortKey, sortAsc])

  const toggleSort = (key) => {
    if (sortKey === key) setSortAsc(!sortAsc)
    else { setSortKey(key); setSortAsc(false) }
  }

  const sortIcon = (key) => sortKey === key ? (sortAsc ? ' \u25B2' : ' \u25BC') : ''

  if (matchups === null) return <p className="text-text-muted text-sm py-4">Loading matchup data...</p>
  if (!matchups.length) return <p className="text-text-muted text-sm py-4">Not enough data for matchup analysis (need 10+ games per matchup)</p>

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left">
            <th className="px-3 py-2 text-xs font-semibold text-text-muted uppercase cursor-pointer" onClick={() => toggleSort('opponent')}>Opponent{sortIcon('opponent')}</th>
            <th className="px-3 py-2 text-xs font-semibold text-text-muted uppercase text-center cursor-pointer" onClick={() => toggleSort('wins')}>Wins{sortIcon('wins')}</th>
            <th className="px-3 py-2 text-xs font-semibold text-text-muted uppercase text-center cursor-pointer" onClick={() => toggleSort('losses')}>Losses{sortIcon('losses')}</th>
            <th className="px-3 py-2 text-xs font-semibold text-text-muted uppercase text-center cursor-pointer" onClick={() => toggleSort('total')}>Games{sortIcon('total')}</th>
            <th className="px-3 py-2 text-xs font-semibold text-text-muted uppercase text-right cursor-pointer" onClick={() => toggleSort('win_rate')}>Win Rate{sortIcon('win_rate')}</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((mu) => (
            <tr key={mu.opponent} className="border-b border-border/50 hover:bg-bg-elevated/50 transition-colors">
              <td className="px-3 py-2">
                <Link to={`/avatar/${encodeURIComponent(mu.opponent)}`} className="hover:text-primary transition-colors">{mu.opponent}</Link>
              </td>
              <td className="px-3 py-2 text-center text-accent-green">{mu.wins}</td>
              <td className="px-3 py-2 text-center text-accent-red">{mu.losses}</td>
              <td className="px-3 py-2 text-center text-text-muted">{mu.total}</td>
              <td className={`px-3 py-2 text-right font-bold ${getMatchupClass(mu.win_rate)}`}>{mu.win_rate}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── ELO Win Rate Matrix (admin only) ─────────────────────────

function EloMatrix({ avatarName, source, eventFilter }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    const params = new URLSearchParams({ source })
    if (eventFilter !== 'all') params.set('event', eventFilter)
    get(`/api/avatar/${encodeURIComponent(avatarName)}/elo-matrix?${params}`)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [avatarName, source, eventFilter])

  if (loading) return <p className="text-text-muted text-sm py-4">Loading ELO matrix...</p>
  if (!data || !data.matrix?.length) return <p className="text-text-muted text-sm py-4">Not enough data for ELO breakdown.</p>

  const { brackets, matrix } = data

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-border">
            <th className="px-2 py-2 text-left text-xs font-semibold text-text-muted uppercase whitespace-nowrap">
              Player ELO ↓ / Opp →
            </th>
            {brackets.map((b) => (
              <th key={b} className="px-2 py-2 text-center text-xs font-semibold text-text-muted uppercase whitespace-nowrap">
                {b}-{b + 99}
              </th>
            ))}
            <th className="px-2 py-2 text-center text-xs font-bold text-secondary uppercase whitespace-nowrap">Total</th>
          </tr>
        </thead>
        <tbody>
          {matrix.map((row) => (
            <tr key={row.player_bracket} className="border-b border-border/50 hover:bg-bg-elevated/50 transition-colors">
              <td className="px-2 py-2 text-xs font-bold whitespace-nowrap">
                {row.player_bracket}-{row.player_bracket + 99}
              </td>
              {row.cells.map((cell, i) => (
                <td key={brackets[i]} className="px-2 py-2 text-center whitespace-nowrap">
                  {cell.total > 0 ? (
                    <>
                      <span className="font-bold" style={{ color: getWinRateColor(cell.win_rate) }}>
                        {cell.win_rate}%
                      </span>
                      <div className="text-xs text-text-muted">({cell.wins}W-{cell.losses}L)</div>
                    </>
                  ) : (
                    <span className="text-text-muted">—</span>
                  )}
                </td>
              ))}
              <td className="px-2 py-2 text-center whitespace-nowrap bg-bg-elevated/30">
                {row.total.total > 0 ? (
                  <>
                    <span className="font-bold" style={{ color: getWinRateColor(row.total.win_rate) }}>
                      {row.total.win_rate}%
                    </span>
                    <div className="text-xs text-text-muted">({row.total.wins}W-{row.total.losses}L)</div>
                  </>
                ) : (
                  <span className="text-text-muted">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Deck Composition (element bars) ───────────────────────────

function DeckComposition({ avatarName }) {
  const [data, setData] = useState(null)

  useEffect(() => {
    get(`/api/avatar/${encodeURIComponent(avatarName)}/deck-composition`)
      .then(setData)
      .catch(() => setData(null))
  }, [avatarName])

  if (!data || !data.composition?.length) return null

  return (
    <div className="space-y-3">
      {data.composition.map((c) => {
        const style = getElementStyle(c.elements)
        return (
          <div key={c.elements} className="flex items-center gap-3">
            <span className={`min-w-[180px] text-sm font-semibold ${style.text}`}>{c.elements}</span>
            <div className="flex-1 h-7 bg-bg-elevated rounded relative">
              <div
                className={`h-full rounded bg-gradient-to-r ${style.bar} transition-all duration-700`}
                style={{ width: `${c.percent}%` }}
              />
              <span className="absolute right-2 top-0.5 text-xs font-bold text-white/80">{c.percent}%</span>
            </div>
            <span className="min-w-[70px] text-right text-xs text-text-muted">{c.count} decks</span>
          </div>
        )
      })}
    </div>
  )
}

// ── Staff Pick Decks ──────────────────────────────────────────

function StaffPicks({ avatarName }) {
  const [decks, setDecks] = useState(null)

  useEffect(() => {
    get('/api/deck-rec/decks')
      .then((data) => {
        const filtered = (data.decks || data || []).filter(
          (d) => d.is_admin_rec && d.avatar_name && d.avatar_name.toLowerCase() === avatarName.toLowerCase()
        )
        setDecks(filtered)
      })
      .catch(() => setDecks([]))
  }, [avatarName])

  if (decks === null) return <p className="text-text-muted text-sm">Loading decks...</p>
  if (!decks.length) return <p className="text-text-muted text-sm">No staff pick decks for this avatar yet.</p>

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {decks.map((d) => (
        <Link
          key={d.deck_id}
          to={`/deck-rec/${encodeURIComponent(d.deck_id)}`}
          className="bg-bg-elevated border border-border rounded-soft p-3 hover:border-primary/50 transition-colors"
        >
          <div className="text-sm font-semibold truncate">{d.deck_name}</div>
          {d.event_name && <div className="text-xs text-text-muted truncate mt-0.5">{d.event_name}</div>}
          {d.stars > 0 && <div className="text-amber-400 text-sm mt-1">{'★'.repeat(d.stars)}{'☆'.repeat(3 - d.stars)}</div>}
          {d.primer && <p className="text-xs text-text-muted mt-1 line-clamp-2">{d.primer}</p>}
        </Link>
      ))}
    </div>
  )
}

// ── Top Player Badge ──────────────────────────────────────────

function TopPlayerBadge({ topPlayers }) {
  const [sortBy, setSortBy] = useState('avatar_score')
  if (!topPlayers) return null

  const player = topPlayers[sortBy]
  if (!player) return null

  let record
  if (sortBy === 'avatar_score') record = `Avatar Score: ${player.avatar_score ?? 0} (${player.win_rate}% WR, ${player.total} games)`
  else if (sortBy === 'winrate') record = `${player.win_rate}% (${player.wins}W-${player.losses}L)`
  else record = `${player.wins} wins (${player.win_rate}% WR)`

  return (
    <div className="text-right flex-shrink-0">
      <div className="flex items-center justify-end gap-2 mb-1">
        <span className="text-xs uppercase tracking-wide text-text-muted">Top Player</span>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="text-xs bg-bg-elevated border border-border rounded px-1.5 py-0.5 text-text-muted"
        >
          <option value="avatar_score">Avatar Score</option>
          <option value="winrate">Win Rate</option>
          <option value="total_wins">Wins</option>
        </select>
      </div>
      <Link to={`/player/${player.player_id}`} className="text-base font-semibold text-primary hover:underline block">
        {player.name}
      </Link>
      <div className="text-xs text-text-muted">{record}</div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────

export default function AvatarDetail() {
  const { name } = useParams()
  usePageTitle(`${decodeURIComponent(name)} - Avatar Profile`)
  const { user } = useAuth()
  const isAdmin = user?.is_admin === true

  const [avatar, setAvatar] = useState(null)
  const [imageFiles, setImageFiles] = useState([])
  const [imageSettings, setImageSettings] = useState({})
  const [filters, setFilters] = useState({ events: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [source, setSource] = useState(() => localStorage.getItem(SOURCE_KEY) || 'discord')
  const [eventFilter, setEventFilter] = useState('all')

  // Load filters + image files once
  useEffect(() => {
    Promise.allSettled([getAvatarFilters(), getAvatarImageFiles()])
      .then(([flt, imgs]) => {
        if (flt.status === 'fulfilled') setFilters(flt.value)
        if (imgs.status === 'fulfilled') setImageFiles(imgs.value)
      })
  }, [])

  // Load image settings only for admins
  useEffect(() => {
    if (!isAdmin) return
    getAvatarImageSettings()
      .then((data) => setImageSettings(data.settings || {}))
      .catch(() => {})
  }, [isAdmin])

  // Fetch avatar data on source/event change
  const fetchAvatar = useCallback(() => {
    setLoading(true)
    const params = new URLSearchParams({ source })
    if (eventFilter !== 'all') params.set('event', eventFilter)
    get(`/api/avatar/${encodeURIComponent(name)}?${params}`)
      .then(setAvatar)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [name, source, eventFilter])

  useEffect(() => { fetchAvatar() }, [fetchAvatar])

  const handleSourceChange = (s) => {
    setSource(s)
    localStorage.setItem(SOURCE_KEY, s)
  }

  if (loading && !avatar) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>
  if (!avatar) return null

  const imgFile = getAvatarImagePath(name, imageFiles)
  const imgSrc = imgFile ? `/avatar-images/${imgFile}` : null
  const avatarImgSettings = imageSettings[decodeURIComponent(name)] || imageSettings[avatar?.name] || {}
  const imgPos = `${avatarImgSettings.position_x ?? 50}% ${avatarImgSettings.position_y ?? 25}%`
  const imgBrightness = avatarImgSettings.brightness ?? 1.0

  const handleImageSettingsSaved = (avatarName, newSettings) => {
    setImageSettings((prev) => {
      const next = { ...prev }
      if (newSettings) next[avatarName] = newSettings
      else delete next[avatarName]
      return next
    })
  }

  return (
    <div className="space-y-0">
      <Link to="/avatars" className="text-primary hover:text-primary/80 text-sm inline-block mb-4">&larr; Back to Avatar Win Rates</Link>

      {/* Filters */}
      <div className="flex flex-wrap items-center justify-center gap-4 mb-6">
        <div className="flex items-center gap-2">
          <label className="text-sm text-text-muted">Event:</label>
          <select
            value={eventFilter}
            onChange={(e) => setEventFilter(e.target.value)}
            className="bg-bg-surface border border-border rounded px-2 py-1 text-sm"
          >
            <option value="all">All Events</option>
            {(filters.events || []).map((ev) => (
              <option key={ev.event_id || 'current'} value={ev.is_active ? 'current' : String(ev.event_id)}>
                {ev.event_name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-text-muted">Source:</label>
          <SourceToggle source={source} onChange={handleSourceChange} />
        </div>
      </div>

      {/* Profile Card */}
      <div className="bg-bg-surface border border-border rounded-soft overflow-hidden">
        {/* Header */}
        <div className="p-6 border-b border-border flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4 flex-1 min-w-0">
            {imgSrc && (
              <img
                src={imgSrc}
                alt={avatar.name}
                className="w-16 h-16 object-cover rounded flex-shrink-0"
                style={isAdmin && Object.keys(avatarImgSettings).length > 0 ? {
                  objectPosition: imgPos,
                  filter: `brightness(${imgBrightness})`,
                } : undefined}
              />
            )}
            <div>
              <h1 className="text-2xl sm:text-3xl font-semibold capitalize">{avatar.name}</h1>
              <div className="text-text-muted">{avatar.total_matches} matches played</div>
              {isAdmin && imgSrc && (
                <AvatarImageAdmin
                  avatarName={avatar.name}
                  imgSrc={imgSrc}
                  currentSettings={avatarImgSettings}
                  onSaved={handleImageSettingsSaved}
                />
              )}
            </div>
          </div>
          <TopPlayerBadge topPlayers={avatar.top_players} />
        </div>

        {/* Overall Stats */}
        <div className="p-6">
          <h3 className="text-lg font-semibold mb-4">Overall Stats</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard value={avatar.wins} label="Wins" />
            <StatCard value={avatar.losses} label="Losses" />
            <StatCard value={`${avatar.win_rate}%`} label="Win Rate" />
            <StatCard value={avatar.total_matches} label="Total Matches" />
          </div>
        </div>

        {/* Play vs Draw */}
        {avatar.play_stats && avatar.draw_stats && (
          <div className="p-6 border-t border-border">
            <h3 className="text-lg font-semibold mb-1">On the Play vs On the Draw</h3>
            <p className="text-xs text-text-muted mb-4">Statistics from February 7, 2026 onward</p>
            <div className="grid grid-cols-2 gap-3">
              <StatCard
                value={`${avatar.play_stats.win_rate}%`}
                label="Win Rate on the Play"
                sub={`${avatar.play_stats.wins}-${avatar.play_stats.losses} (${avatar.play_stats.total} matches)`}
              />
              <StatCard
                value={`${avatar.draw_stats.win_rate}%`}
                label="Win Rate on the Draw"
                sub={`${avatar.draw_stats.wins}-${avatar.draw_stats.losses} (${avatar.draw_stats.total} matches)`}
              />
            </div>
          </div>
        )}

        {/* Staff Pick Decks */}
        <div className="p-6 border-t border-border">
          <h3 className="text-lg font-semibold mb-1">Staff Pick Decks</h3>
          <p className="text-xs text-text-muted mb-4">Tournament and community builds for this avatar</p>
          <StaffPicks avatarName={avatar.name} />
        </div>

        {/* Matchups */}
        <div className="p-6 border-t border-border">
          <h3 className="text-lg font-semibold mb-1">Matchups vs Other Avatars</h3>
          <p className="text-xs text-text-muted mb-4">Showing matchups with 10+ games for statistical significance</p>
          <MatchupsSection avatarName={name} source={source} eventFilter={eventFilter} />
        </div>

        {/* ELO Win Rate Matrix (admin only) */}
        {isAdmin && (
          <div className="p-6 border-t border-border">
            <h3 className="text-lg font-semibold mb-1">Win Rate by ELO Bracket</h3>
            <p className="text-xs text-text-muted mb-4">How this avatar performs across different ELO ranges (using current player ratings)</p>
            <EloMatrix avatarName={name} source={source} eventFilter={eventFilter} />
          </div>
        )}

        {/* Deck Composition */}
        <div className="p-6 border-t border-border">
          <h3 className="text-lg font-semibold mb-1">Deck Element Composition</h3>
          <p className="text-xs text-text-muted mb-3">Element breakdown across all decks played with this avatar</p>
          <DeckComposition avatarName={name} />
        </div>

        {/* Wins History */}
        <div className="p-6 border-t border-border">
          <h3 className="text-lg font-semibold mb-4">Wins</h3>
          <MatchTable matches={avatar.wins_matches} emptyText="No wins recorded" />
        </div>

        {/* Losses History */}
        <div className="p-6 border-t border-border">
          <h3 className="text-lg font-semibold mb-4">Losses</h3>
          <MatchTable matches={avatar.losses_matches} emptyText="No losses recorded" />
        </div>
      </div>
    </div>
  )
}
