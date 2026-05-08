import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { get } from '@/api/client'
import { getEventLeaderboard, getPaperEventLeaderboard, getLimitedLeaderboard } from '@/api/leaderboard'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

// ── Player Search ─────────────────────────────────────────────

function PlayerSearch() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const [activeIdx, setActiveIdx] = useState(-1)
  const timerRef = useRef(null)
  const containerRef = useRef(null)
  const navigate = useNavigate()

  const search = useCallback(async (q) => {
    if (q.length < 3) { setOpen(false); return }
    try {
      const data = await get(`/api/players/search?q=${encodeURIComponent(q)}&limit=8`)
      setResults(data.players || [])
      setActiveIdx(-1)
      setOpen(true)
    } catch {
      setOpen(false)
    }
  }, [])

  const handleInput = (e) => {
    const val = e.target.value
    setQuery(val)
    clearTimeout(timerRef.current)
    if (val.trim().length < 3) { setOpen(false); return }
    timerRef.current = setTimeout(() => search(val.trim()), 200)
  }

  const getAvatarUrl = (player) => {
    if (player.provider === 'discord' && player.avatar)
      return `https://cdn.discordapp.com/avatars/${player.user_id}/${player.avatar}.png?size=32`
    if (player.provider === 'google' && player.avatar) return player.avatar
    return null
  }

  const goToPlayer = (player) => {
    setOpen(false)
    setQuery('')
    navigate(`/player/${encodeURIComponent(player.user_id)}`)
  }

  const handleKeyDown = (e) => {
    if (!open) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIdx((i) => Math.min(i + 1, results.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIdx((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      if (activeIdx >= 0 && results[activeIdx]) goToPlayer(results[activeIdx])
      else if (results.length === 1) goToPlayer(results[0])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  useEffect(() => {
    const handler = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div ref={containerRef} className="relative w-full max-w-md mx-auto mt-6">
      <input
        type="text"
        value={query}
        onChange={handleInput}
        onKeyDown={handleKeyDown}
        placeholder="Search players..."
        autoComplete="off"
        spellCheck={false}
        className="w-full bg-bg-surface border border-border rounded-soft px-4 py-2 text-sm focus:outline-none focus:border-primary/60 placeholder:text-text-muted"
      />
      {open && (
        <div className="absolute z-50 w-full mt-1 bg-bg-surface border border-border rounded-soft shadow-lg overflow-hidden">
          {results.length === 0 ? (
            <div className="px-4 py-2 text-sm text-text-muted">No players found</div>
          ) : (
            results.map((player, i) => {
              const avatarUrl = getAvatarUrl(player)
              return (
                <button
                  key={player.user_id}
                  onClick={() => goToPlayer(player)}
                  className={`w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-bg-elevated transition-colors ${i === activeIdx ? 'bg-bg-elevated' : ''}`}
                >
                  {avatarUrl ? (
                    <img src={avatarUrl} alt="" className="w-6 h-6 rounded-full object-cover" onError={(e) => { e.target.style.visibility = 'hidden' }} />
                  ) : (
                    <span className="w-6 h-6 rounded-full bg-border/40 inline-block" />
                  )}
                  <span>{player.display_name}</span>
                </button>
              )
            })
          )}
        </div>
      )}
    </div>
  )
}

// ── Promo Banners ─────────────────────────────────────────────

const BANNER_COLORS = {
  blue:   { border: 'border-blue-500/40',   badge: 'bg-blue-500',   glow: 'hover:border-blue-400/60' },
  gold:   { border: 'border-yellow-500/40', badge: 'bg-yellow-500', glow: 'hover:border-yellow-400/60' },
  green:  { border: 'border-green-500/40',  badge: 'bg-green-500',  glow: 'hover:border-green-400/60' },
  purple: { border: 'border-purple-500/40', badge: 'bg-purple-500', glow: 'hover:border-purple-400/60' },
  red:    { border: 'border-red-500/40',    badge: 'bg-red-500',    glow: 'hover:border-red-400/60' },
}

function extractDominantColor(imgEl) {
  const canvas = document.createElement('canvas')
  canvas.width = 50
  canvas.height = 50
  const ctx = canvas.getContext('2d')
  ctx.drawImage(imgEl, 0, 0, 50, 50)
  const { data } = ctx.getImageData(0, 0, 50, 50)
  let r = 0, g = 0, b = 0, count = 0
  for (let i = 0; i < data.length; i += 4) {
    if (data[i + 3] < 128) continue // skip transparent
    r += data[i]; g += data[i + 1]; b += data[i + 2]; count++
  }
  if (!count) return null
  return [Math.round(r / count), Math.round(g / count), Math.round(b / count)]
}

function PromoBanner({ b }) {
  const images = useMemo(() => b.images || [], [b.images])
  const [imgIdx, setImgIdx] = useState(0)
  const [dominantColor, setDominantColor] = useState(null)
  const colors = BANNER_COLORS[b.color] || BANNER_COLORS.blue

  useEffect(() => {
    if (images.length <= 1) return
    const id = setInterval(() => setImgIdx(i => (i + 1) % images.length), 10000)
    return () => clearInterval(id)
  }, [images.length])

  // Reset color when image changes
  useEffect(() => { setDominantColor(null) }, [imgIdx])

  const handleImageLoad = (e) => {
    try {
      setDominantColor(extractDominantColor(e.target))
    } catch { /* CORS blocked on external URLs */ }
  }

  const dc = dominantColor
  const imgBg = dc
    ? `linear-gradient(135deg, rgba(${dc},0.55) 0%, rgba(${dc[0]},${dc[1]},${dc[2]},0.25) 60%, rgba(0,0,0,0.6) 100%)`
    : undefined
  const cardShadow = dc
    ? { boxShadow: `0 4px 28px rgba(${dc[0]},${dc[1]},${dc[2]},0.45)` }
    : undefined

  return (
    <a
      href={b.link}
      onClick={() => {
        navigator.sendBeacon?.('/api/analytics/banner-click',
          new Blob([JSON.stringify({ banner_type: `promo_${b.id}` })], { type: 'application/json' }))
      }}
      className={`block overflow-hidden rounded-soft border bg-bg-surface transition-all duration-300 group ${colors.border} ${colors.glow}`}
      style={cardShadow}
    >
      {/* Image panel */}
      {images.length > 0 ? (
        <div
          className="w-full h-44 flex items-center justify-center overflow-hidden transition-all duration-700"
          style={{ background: imgBg || 'rgba(0,0,0,0.6)' }}
        >
          <img
            key={images[imgIdx]}
            src={images[imgIdx]}
            alt=""
            crossOrigin="anonymous"
            className="w-full h-full object-contain block transition-transform duration-500 group-hover:scale-[1.02]"
            onLoad={handleImageLoad}
            onError={(e) => { e.target.parentElement.style.display = 'none' }}
          />
        </div>
      ) : (
        <div className="h-10" />
      )}

      {/* Text strip */}
      <div className="flex items-center gap-3 px-4 py-3 bg-bg-raised border-t border-border/50">
        <span className={`text-xs font-bold px-2 py-0.5 ${colors.badge} text-white rounded flex-shrink-0`}>
          {b.badge_text}
        </span>
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-sm text-text-primary leading-tight">{b.title}</div>
          {b.subtitle && (
            <div className="text-text-muted text-xs mt-0.5 leading-tight">{b.subtitle}</div>
          )}
        </div>
        <span className="text-text-muted text-base group-hover:translate-x-1 transition-transform flex-shrink-0">&rarr;</span>
      </div>
    </a>
  )
}

function PromoBanners() {
  const [banners, setBanners] = useState([])

  useEffect(() => {
    get('/api/analytics/banners/active')
      .then((data) => { if (data.success) setBanners(data.banners || []) })
      .catch(() => {})
  }, [])

  if (!banners.length) return null

  return (
    <div className="space-y-2">
      {banners.map((b) => <PromoBanner key={b.id} b={b} />)}
    </div>
  )
}

// ── Community Spotlight ───────────────────────────────────────

function CommunitySpotlight() {
  const [spotlight, setSpotlight] = useState(null)

  useEffect(() => {
    get('/api/spotlight')
      .then((data) => { if (data.success && data.spotlight) setSpotlight(data.spotlight) })
      .catch(() => {})
  }, [])

  if (!spotlight) return null

  const colors = BANNER_COLORS[spotlight.color] || BANNER_COLORS.blue
  const isExternal = spotlight.link && !spotlight.link.startsWith('/')

  const handleClick = () => {
    navigator.sendBeacon?.('/api/analytics/banner-click',
      new Blob([JSON.stringify({ banner_type: `spotlight_${spotlight.type}` })], { type: 'application/json' }))
  }

  const stats = spotlight.stats
  const avatarBgImage = stats?.avatar_bg_image
  const elements = stats?.elements || []
  const isPlayerCard = spotlight.type === 'player_of_the_day' && avatarBgImage

  const ELEMENT_COLORS = {
    Earth: 'text-green-400',
    Fire: 'text-red-400',
    Water: 'text-blue-400',
    Air: 'text-yellow-300',
  }

  const inner = isPlayerCard ? (
    // Player card matching promo banner layout: image panel + text strip
    <>
      {/* Image panel (same h-44 as promo banners) */}
      <div className="relative w-full h-44 overflow-hidden" style={{ background: 'rgba(0,0,0,0.6)' }}>
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: `url('${avatarBgImage}')`, backgroundPosition: '50% 25%', opacity: 0.5 }}
        />
        <div className="absolute inset-0 bg-black/20" />
      </div>

      {/* Text strip (matches promo banner layout) */}
      <div className="flex items-center gap-3 px-4 py-3 bg-bg-raised border-t border-border/50">
        <span className={`text-xs font-bold px-2 py-0.5 ${colors.badge} text-white rounded flex-shrink-0`}>
          {spotlight.badge_text}
        </span>
        {spotlight.image_url && (
          <img
            src={spotlight.image_url}
            alt=""
            className="w-8 h-8 rounded-full object-cover border border-border flex-shrink-0"
            onError={(e) => { e.target.style.display = 'none' }}
          />
        )}
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-sm text-text-primary leading-tight">{spotlight.title}</div>
          <div className="text-text-muted text-xs mt-0.5 leading-tight">{spotlight.subtitle}</div>
        </div>
        <span className="text-text-muted text-base group-hover:translate-x-1 transition-transform flex-shrink-0">&rarr;</span>
      </div>
    </>
  ) : (
    // Standard card for community channel / website (no avatar image)
    <>
      <div className="flex items-center gap-3 px-4 py-3 bg-bg-raised border-b border-border/50">
        <span className={`text-xs font-bold px-2 py-0.5 ${colors.badge} text-white rounded flex-shrink-0`}>
          {spotlight.badge_text}
        </span>
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-sm text-text-primary leading-tight">{spotlight.title}</div>
          <div className="text-text-muted text-xs mt-0.5 leading-tight">{spotlight.subtitle}</div>
        </div>
        <span className="text-text-muted text-base group-hover:translate-x-1 transition-transform flex-shrink-0">&rarr;</span>
      </div>
    </>
  )

  if (isExternal) {
    return (
      <a
        href={spotlight.link}
        target="_blank"
        rel="noopener noreferrer"
        onClick={handleClick}
        className={`block overflow-hidden rounded-soft border bg-bg-surface transition-all duration-300 group ${colors.border} ${colors.glow}`}
      >
        {inner}
      </a>
    )
  }

  return (
    <Link
      to={spotlight.link}
      onClick={handleClick}
      className={`block overflow-hidden rounded-soft border bg-bg-surface transition-all duration-300 group ${colors.border} ${colors.glow}`}
    >
      {inner}
    </Link>
  )
}

// ── Stat Bar ──────────────────────────────────────────────────

function StatBar({ leaderboard, eloKey = 'event_elo' }) {
  if (!leaderboard.length) return null
  const total = leaderboard.length
  const top = leaderboard[0][eloKey]
  const avg = Math.round(leaderboard.reduce((s, p) => s + (p[eloKey] || 0), 0) / total)
  return (
    <div className="flex gap-6 mb-4 text-center">
      {[['Players', total], ['Top ELO', top], ['Avg ELO', avg]].map(([label, val]) => (
        <div key={label}>
          <div className="text-lg font-bold text-secondary">{val}</div>
          <div className="text-xs text-text-muted">{label}</div>
        </div>
      ))}
    </div>
  )
}

// ── YouTube Videos ────────────────────────────────────────────

function YouTubeVideos() {
  const [videos, setVideos] = useState([])

  useEffect(() => {
    get('/api/youtube-videos')
      .then((data) => setVideos(Object.values(data).filter(Boolean)))
      .catch(() => {})
  }, [])

  if (!videos.length) return null

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-4">
      {videos.map((v, i) => (
        <div key={i} className="bg-bg-surface border border-border rounded-soft overflow-hidden">
          <a href={v.url} target="_blank" rel="noopener noreferrer">
            <img src={v.thumbnail} alt={v.title} className="w-full aspect-video object-cover" loading="lazy" />
          </a>
          <div className="p-3">
            <p className="text-xs text-text-muted mb-1">
              <a href={v.channel_url} target="_blank" rel="noopener noreferrer" className="hover:text-primary transition-colors">
                {v.channel_display_name}
              </a>
            </p>
            <a href={v.url} target="_blank" rel="noopener noreferrer" className="text-sm font-medium hover:text-primary transition-colors line-clamp-2">
              {v.title}
            </a>
          </div>
        </div>
      ))}
    </div>
  )
}

// ── ELO Source Toggle ─────────────────────────────────────────

const STORAGE_KEY = 'home_elo_source_preference'

const SOURCE_LABELS = { online: 'Online', paper: 'Paper', limited: 'Limited' }

function EloToggle({ source, onChange }) {
  return (
    <div className="inline-flex bg-bg-surface border border-border rounded-soft overflow-hidden">
      {['online', 'paper', 'limited'].map((s) => (
        <button
          key={s}
          onClick={() => onChange(s)}
          className={`px-4 py-1.5 text-sm font-medium transition-colors capitalize ${
            source === s
              ? 'bg-primary text-black'
              : 'text-text-muted hover:bg-bg-elevated hover:text-primary'
          }`}
        >
          {SOURCE_LABELS[s]}
        </button>
      ))}
    </div>
  )
}

// ── Leaderboard Table ─────────────────────────────────────────

const RANK_LABELS = { 1: 'I', 2: 'II', 3: 'III' }

function EventLeaderboardTable({ leaderboard, eloKey = 'event_elo' }) {
  if (!leaderboard.length) {
    return <p className="text-center text-text-muted py-8">No matches played yet</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left">
            <th className="py-2 px-3 w-14 text-text-muted font-semibold">Rank</th>
            <th className="py-2 px-3 text-text-muted font-semibold">Player</th>
            <th className="py-2 px-3 text-right text-text-muted font-semibold">ELO</th>
          </tr>
        </thead>
        <tbody>
          {leaderboard.map((player, index) => {
            const rank = index + 1
            return (
              <tr key={player.id} className={`border-b border-border/50 hover:bg-bg-surface/50 transition-colors ${rank <= 3 ? `font-semibold` : ''}`}>
                <td className="py-2 px-3">
                  {rank <= 3 ? (
                    <span className={`inline-flex items-center justify-center w-7 h-7 rounded text-xs font-bold ${
                      rank === 1 ? 'bg-yellow-500/20 text-yellow-400' :
                      rank === 2 ? 'bg-gray-400/20 text-gray-300' :
                      'bg-amber-700/20 text-amber-600'
                    }`}>
                      {RANK_LABELS[rank]}
                    </span>
                  ) : (
                    <span className="text-text-muted">{rank}</span>
                  )}
                </td>
                <td className="py-2 px-3">
                  <Link to={`/player/${player.id}`} className="hover:text-primary transition-colors">
                    {player.name}
                  </Link>
                </td>
                <td className="py-2 px-3 text-right">{player[eloKey]}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── Home Page ─────────────────────────────────────────────────

export default function Home() {
  usePageTitle('Sorcerers Summit')
  const [source, setSource] = useState(() =>
    ['paper', 'limited'].includes(localStorage.getItem(STORAGE_KEY)) ? localStorage.getItem(STORAGE_KEY) : 'online'
  )
  const [eventData, setEventData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [newEvent, setNewEvent] = useState(null)
  const titleClickCount = useRef(0)
  const titleTimer = useRef(null)
  const navigate = useNavigate()

  // Fetch new event banner
  useEffect(() => {
    get('/api/recent-event')
      .then((data) => setNewEvent(data.event || null))
      .catch(() => {})
  }, [])

  // Fetch event leaderboard
  const fetchLeaderboard = useCallback(async (src) => {
    setLoading(true)
    try {
      if (src === 'limited') {
        const data = await getLimitedLeaderboard()
        setEventData({ limited: true, leaderboard: data })
      } else {
        const data = src === 'paper' ? await getPaperEventLeaderboard() : await getEventLeaderboard()
        setEventData(data)
      }
    } catch {
      setEventData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchLeaderboard(source)
    const interval = setInterval(() => fetchLeaderboard(source), 30000)
    return () => clearInterval(interval)
  }, [source, fetchLeaderboard])

  const handleSourceChange = (src) => {
    setSource(src)
    localStorage.setItem(STORAGE_KEY, src)
  }

  const handleTitleClick = () => {
    titleClickCount.current += 1
    if (titleClickCount.current === 3) {
      titleClickCount.current = 0
      clearTimeout(titleTimer.current)
      navigate('/secret-fart-leaderboard')
      return
    }
    clearTimeout(titleTimer.current)
    titleTimer.current = setTimeout(() => { titleClickCount.current = 0 }, 600)
  }

  const isLimited = eventData?.limited === true
  const hasEvent = isLimited || eventData?.event != null
  const leaderboard = eventData?.leaderboard || []

  return (
    <div className="space-y-8">
      {/* Hero */}
      <section className="text-center pt-6">
        <h1
          onClick={handleTitleClick}
          className="text-3xl font-display text-secondary mb-2 cursor-default select-none"
        >
          Welcome to the Sorcery Community Leaderboard
        </h1>

        {/* New Event Banner */}
        {newEvent && (
          <a
            href={`/top-8/${newEvent.folder}`}
            onClick={() => {
              navigator.sendBeacon?.('/api/analytics/banner-click',
                new Blob([JSON.stringify({ banner_type: 'new_event' })], { type: 'application/json' }))
            }}
            className="inline-flex items-center gap-3 mt-4 px-4 py-2 bg-bg-surface border border-primary/40 rounded-soft hover:border-primary transition-colors"
          >
            <span className="text-xs font-bold px-2 py-0.5 bg-primary text-black rounded">NEW</span>
            <span className="text-sm font-medium">New Top 8 decklists added: {newEvent.name}</span>
            <span className="text-text-muted">&rarr;</span>
          </a>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
          <PromoBanners />
          <CommunitySpotlight />
        </div>
        <PlayerSearch />
      </section>

      {/* Event Leaderboard or No-Event */}
      {loading ? (
        <Spinner className="py-16" />
      ) : hasEvent ? (
        <section>
          <div className="flex flex-wrap justify-between items-start gap-4 mb-4">
            <div>
              {isLimited ? (
                <>
                  <h2 className="text-xl font-display text-secondary">Limited Format Leaderboard</h2>
                  <p className="text-sm text-text-muted mt-0.5">Rankings for limited format matches</p>
                </>
              ) : (
                <>
                  <h2 className="text-xl font-display text-secondary">{eventData.event.event_name}</h2>
                  <p className="text-sm text-text-muted mt-0.5">
                    Started: {new Date(eventData.event.start_date).toLocaleDateString()}
                  </p>
                </>
              )}
            </div>
            <EloToggle source={source} onChange={handleSourceChange} />
          </div>
          {!isLimited && <StatBar leaderboard={leaderboard} />}
          <EventLeaderboardTable leaderboard={leaderboard} eloKey={isLimited ? 'elo' : 'event_elo'} />
        </section>
      ) : (
        <section className="text-center py-8">
          <div className="flex justify-center mb-4">
            <EloToggle source={source} onChange={handleSourceChange} />
          </div>
          <h2 className="text-xl font-display text-secondary mb-2">No Active Event</h2>
          <p className="text-text-muted mb-2">Check back soon for the next event leaderboard!</p>
          <p className="text-text-muted text-sm mb-6">
            In the meantime, check out the{' '}
            <Link to="/avatars" className="text-primary hover:text-primary/80">Avatar Win Rates</Link>
            {' '}or catch up on some Sorcery content:
          </p>
          <YouTubeVideos />
        </section>
      )}
    </div>
  )
}
