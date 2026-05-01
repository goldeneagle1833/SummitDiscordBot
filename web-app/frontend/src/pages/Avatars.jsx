import { useState, useEffect, useMemo, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { getAvatars, getAvatarImageFiles, getAvatarFilters, getPlayDrawStats } from '@/api/cards'
import { getAvatarImageSettings } from '@/api/admin'
import { useAuth } from '@/context/AuthContext'
import AvatarImageAdmin from '@/components/ui/AvatarImageAdmin'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

const SORT_OPTIONS = [
  { value: 'accuracy', label: 'Accuracy Score' },
  { value: 'winrate', label: 'Win Rate' },
  { value: 'alphabetical', label: 'Alphabetical' },
  { value: 'most-played', label: 'Most Played' },
  { value: 'most-wins', label: 'Most Wins' },
  { value: 'best-record', label: 'Best Record (+/-)' },
]

const SORT_LABELS = {
  accuracy: 'accuracy score (win rate \u00d7 games played)',
  winrate: 'win rate',
  alphabetical: 'name (A\u2013Z)',
  'most-played': 'most games played',
  'most-wins': 'most wins',
  'best-record': 'best record (wins \u2212 losses)',
}

function getWinRateColor(winRate) {
  const pct = Math.max(0, Math.min(100, winRate))
  if (pct <= 50) {
    const ratio = pct / 50
    return `rgb(${Math.round(231 + 24 * ratio)}, ${Math.round(76 + 179 * ratio)}, ${Math.round(60 + 195 * ratio)})`
  }
  const ratio = (pct - 50) / 50
  return `rgb(${Math.round(255 - 209 * ratio)}, ${Math.round(255 - 51 * ratio)}, ${Math.round(255 - 142 * ratio)})`
}

function getAvatarImagePath(name, files) {
  const norm = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, '')
  const n = norm(name)
  for (const f of files) { if (norm(f.replace(/\.\w+$/, '')) === n) return f }
  for (const f of files) { if (norm(f.replace(/\.\w+$/, '')).includes(n)) return f }
  for (const f of files) { if (n.includes(norm(f.replace(/\.\w+$/, '')))) return f }
  return null
}

function sortAvatars(data, key) {
  const d = [...data]
  switch (key) {
    case 'winrate': return d.sort((a, b) => b.win_rate - a.win_rate || b.total - a.total)
    case 'alphabetical': return d.sort((a, b) => a.name.localeCompare(b.name))
    case 'most-played': return d.sort((a, b) => b.total - a.total || b.win_rate - a.win_rate)
    case 'most-wins': return d.sort((a, b) => b.wins - a.wins || b.win_rate - a.win_rate)
    case 'best-record': return d.sort((a, b) => (b.wins - b.losses) - (a.wins - a.losses) || b.total - a.total)
    default: return d.sort((a, b) => (b.win_rate * b.total) - (a.win_rate * a.total))
  }
}

export default function Avatars() {
  usePageTitle('Avatar Win Rates')
  const { user } = useAuth()
  const isAdmin = user?.is_admin === true
  const [avatars, setAvatars] = useState([])
  const [imageFiles, setImageFiles] = useState([])
  const [imageSettings, setImageSettings] = useState({})
  const [filters, setFilters] = useState({ events: [], sources: [] })
  const [playDraw, setPlayDraw] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [eventFilter, setEventFilter] = useState('all')
  const [sourceFilter, setSourceFilter] = useState('discord')
  const [sortBy, setSortBy] = useState('accuracy')

  useEffect(() => {
    Promise.allSettled([getAvatarImageFiles(), getAvatarFilters(), getPlayDrawStats()])
      .then(([imgs, flt, pd]) => {
        if (imgs.status === 'fulfilled') setImageFiles(imgs.value)
        if (flt.status === 'fulfilled') setFilters(flt.value)
        if (pd.status === 'fulfilled') setPlayDraw(pd.value)
      })
  }, [])

  useEffect(() => {
    if (!isAdmin) return
    getAvatarImageSettings()
      .then((data) => setImageSettings(data.settings || {}))
      .catch(() => {})
  }, [isAdmin])

  const handleImageSettingsSaved = useCallback((avatarName, newSettings) => {
    setImageSettings((prev) => {
      const next = { ...prev }
      if (newSettings) next[avatarName] = newSettings
      else delete next[avatarName]
      return next
    })
  }, [])

  useEffect(() => {
    setLoading(true)
    const params = { source: sourceFilter }
    if (eventFilter !== 'all') params.event = eventFilter
    getAvatars(params)
      .then(setAvatars)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [eventFilter, sourceFilter])

  const sorted = useMemo(() => sortAvatars(avatars, sortBy), [avatars, sortBy])
  const totalGames = useMemo(() => avatars.reduce((s, a) => s + a.total, 0), [avatars])

  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      <section className="text-center mb-6">
        <h1 className="text-2xl font-display text-secondary">Avatar Win Rates</h1>
        <p className="text-sm text-text-muted mt-1">
          Global statistics from all matches reported with decklists, sorted by {SORT_LABELS[sortBy]}
        </p>
        {playDraw?.play_stats && playDraw?.draw_stats && (
          <p className="text-xs text-text-muted mt-2">
            Overall (from 2/7/2026 onward):&nbsp;
            On the Play: <span style={{ color: getWinRateColor(playDraw.play_stats.win_rate) }}>{playDraw.play_stats.win_rate}%</span> ({playDraw.play_stats.wins}W-{playDraw.play_stats.losses}L, {playDraw.play_stats.total} games) |&nbsp;
            On the Draw: <span style={{ color: getWinRateColor(playDraw.draw_stats.win_rate) }}>{playDraw.draw_stats.win_rate}%</span> ({playDraw.draw_stats.wins}W-{playDraw.draw_stats.losses}L, {playDraw.draw_stats.total} games)
          </p>
        )}
      </section>

      <div className="flex flex-wrap justify-center gap-4 mb-6">
        <div className="flex items-center gap-2">
          <label className="text-sm text-text-muted">Event:</label>
          <select value={eventFilter} onChange={(e) => setEventFilter(e.target.value)} className="bg-bg-surface border border-border rounded px-2 py-1 text-sm">
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
          <div className="inline-flex bg-bg-surface border border-border rounded-lg overflow-hidden">
            {[['discord', 'Online'], ['web', 'Paper']].map(([val, label]) => (
              <button
                key={val}
                className={`px-3 py-1 text-xs font-medium transition-colors ${sourceFilter === val ? 'bg-primary text-bg' : 'text-text-muted hover:text-text'}`}
                onClick={() => setSourceFilter(val)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-text-muted">Sort by:</label>
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} className="bg-bg-surface border border-border rounded px-2 py-1 text-sm">
            {SORT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
      </div>

      {loading ? <Spinner className="py-20" /> : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 mb-8">
            {sorted.map((avatar, i) => {
              const imgFile = getAvatarImagePath(avatar.name, imageFiles)
              const imgSrc = imgFile ? `/avatar-images/${imgFile}` : null
              const settings = imageSettings[avatar.name] || {}
              const bgPos = `${settings.position_x ?? 50}% ${settings.position_y ?? 25}%`
              const bgBrightness = settings.brightness ?? 1.0
              const bgOpacity = settings.opacity ?? 0.5
              return (
                <Link
                  key={avatar.name}
                  to={`/avatar/${encodeURIComponent(avatar.name)}`}
                  className="relative bg-bg-surface border border-border rounded-soft overflow-hidden hover:border-primary/50 transition-colors group"
                  style={{ minHeight: '140px' }}
                >
                  {imgSrc && (
                    <div
                      className="absolute inset-0 bg-cover bg-center transition-opacity"
                      style={{
                        backgroundImage: `url('${imgSrc}')`,
                        backgroundPosition: bgPos,
                        filter: `brightness(${bgBrightness})`,
                        opacity: bgOpacity,
                      }}
                    />
                  )}
                  <div className="relative p-3 flex flex-col h-full justify-between">
                    <div>
                      <div className="text-xs text-text-muted mb-1">#{i + 1}</div>
                      <h3 className="text-sm font-semibold leading-tight">{avatar.name}</h3>
                      <span className="text-xs text-text-muted">{avatar.total} games</span>
                    </div>
                    <div className="mt-2">
                      <div className="text-lg font-bold" style={{ color: getWinRateColor(avatar.win_rate) }}>
                        {avatar.win_rate}%
                      </div>
                      <div className="text-xs">
                        <span className="text-accent-green">{avatar.wins}W</span>{' - '}
                        <span className="text-accent-red">{avatar.losses}L</span>
                      </div>
                    </div>
                    {isAdmin && imgSrc && (
                      <div onClick={(e) => { e.preventDefault(); e.stopPropagation() }}>
                        <AvatarImageAdmin
                          avatarName={avatar.name}
                          imgSrc={imgSrc}
                          currentSettings={settings}
                          onSaved={handleImageSettingsSaved}
                        />
                      </div>
                    )}
                  </div>
                </Link>
              )
            })}
          </div>

          <section className="mb-8">
            <h2 className="text-center text-text-muted text-sm mb-4">Total Decklists Reported: {totalGames}</h2>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="border-b border-border">
                  <tr>
                    <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase">Avatar Name</th>
                    <th className="px-3 py-2 text-center text-xs font-semibold text-text-muted uppercase">Reported Games</th>
                    <th className="px-3 py-2 text-center text-xs font-semibold text-text-muted uppercase">% of All Games</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {[...avatars].sort((a, b) => b.total - a.total).map((avatar) => (
                    <tr key={avatar.name} className="hover:bg-bg-elevated transition-colors">
                      <td className="px-3 py-2 text-sm">
                        <Link to={`/avatar/${encodeURIComponent(avatar.name)}`} className="text-primary hover:underline">{avatar.name}</Link>
                      </td>
                      <td className="px-3 py-2 text-sm text-center">{avatar.total}</td>
                      <td className="px-3 py-2 text-sm text-center">{totalGames > 0 ? ((avatar.total / totalGames) * 100).toFixed(1) : 0}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
