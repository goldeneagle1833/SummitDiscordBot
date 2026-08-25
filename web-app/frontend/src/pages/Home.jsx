import { useState, useEffect, useRef, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { get } from '@/api/client'
import { getEventLeaderboard, getPaperEventLeaderboard, getLimitedLeaderboard } from '@/api/leaderboard'
import { StatBox, TrophyRuns, LimitedLeaderboardTable } from '@/components/leaderboard/LimitedLeaderboardContent'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

// ── Player Search ─────────────────────────────────────────────

function PlayerSearch() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const [activeIdx, setActiveIdx] = useState(-1)
  const timerRef = useRef(null)
  const requestSeqRef = useRef(0)
  const containerRef = useRef(null)
  const navigate = useNavigate()

  const MIN_CHARS = 2

  const search = useCallback(async (q) => {
    if (q.length < MIN_CHARS) { setOpen(false); return }
    const seq = ++requestSeqRef.current
    try {
      const data = await get(`/api/players/search?q=${encodeURIComponent(q)}&limit=8`)
      // Ignore stale responses that resolve after a newer request
      if (seq !== requestSeqRef.current) return
      setResults(data.players || [])
      setActiveIdx(-1)
      setOpen(true)
    } catch {
      if (seq === requestSeqRef.current) setOpen(false)
    }
  }, [])

  const handleInput = (e) => {
    const val = e.target.value
    setQuery(val)
    clearTimeout(timerRef.current)
    if (val.trim().length < MIN_CHARS) {
      requestSeqRef.current++ // invalidate in-flight requests
      setOpen(false)
      setResults([])
      setActiveIdx(-1)
      return
    }
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
      else if (results.length > 0) goToPlayer(results[0])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  useEffect(() => {
    const handler = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => {
      document.removeEventListener('mousedown', handler)
      clearTimeout(timerRef.current)
      requestSeqRef.current++ // drop any in-flight response after unmount
    }
  }, [])

  return (
    <div ref={containerRef} className="relative w-full max-w-md mx-auto mt-6">
      <input
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls="player-search-listbox"
        aria-activedescendant={activeIdx >= 0 && results[activeIdx] ? `player-option-${results[activeIdx].user_id}` : undefined}
        aria-autocomplete="list"
        aria-label="Search players"
        value={query}
        onChange={handleInput}
        onKeyDown={handleKeyDown}
        placeholder="Search players..."
        autoComplete="off"
        spellCheck={false}
        className="w-full bg-bg-surface border border-border rounded-soft px-4 py-2 text-sm focus:outline-none focus:border-primary/60 placeholder:text-text-muted"
      />
      {open && (
        <div
          id="player-search-listbox"
          role="listbox"
          className="absolute z-50 w-full mt-1 bg-bg-surface border border-border rounded-soft shadow-lg overflow-hidden"
        >
          {results.length === 0 ? (
            <div className="px-4 py-2 text-sm text-text-muted">No players found</div>
          ) : (
            results.map((player, i) => {
              const avatarUrl = getAvatarUrl(player)
              return (
                <button
                  key={player.user_id}
                  id={`player-option-${player.user_id}`}
                  role="option"
                  aria-selected={i === activeIdx}
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

// ── Promo Carousel ────────────────────────────────────────────

const BADGE_STYLES = {
  blue:   'bg-white/10 text-white/90 border border-white/20',
  gold:   'bg-white/10 text-white/90 border border-white/20',
  green:  'bg-white/10 text-white/90 border border-white/20',
  purple: 'bg-white/10 text-white/90 border border-white/20',
  red:    'bg-white/10 text-white/90 border border-white/20',
}

const isYouTubeLink = (url) => url && /youtu\.?be/i.test(url)

function PromoCarousel() {
  const [items, setItems] = useState([])
  const [active, setActive] = useState(0)
  const timerRef = useRef(null)

  useEffect(() => {
    const promises = [
      get('/api/analytics/banners/active').then(d => d.success ? d.banners || [] : []).catch(() => []),
      get('/api/spotlight').then(d => d.success && d.spotlight ? d.spotlight : null).catch(() => null),
      get('/api/event-spotlight').then(d => d.success && d.event_spotlight ? d.event_spotlight : null).catch(() => null),
      get('/api/recent-event').then(d => d.event || null).catch(() => null),
      get('/api/deck-rec/staff-pick').then(d => d.success && d.staff_pick ? d.staff_pick : null).catch(() => null),
    ]
    Promise.all(promises).then(([banners, spotlight, eventSpotlight, newEvent, staffPick]) => {
      const slides = []

      if (newEvent) {
        slides.push({
          key: 'new-event', badge: 'NEW', color: 'blue',
          title: newEvent.name, subtitle: 'New Top 8 decklists added',
          link: `/top-8/${newEvent.folder}`, thumbnail: null, analyticsType: 'new_event',
        })
      }

      for (const b of banners) {
        const badge = isYouTubeLink(b.link) ? 'VIDEO' : b.badge_text
        slides.push({
          key: `promo-${b.id}`, badge, color: b.color,
          title: b.title, subtitle: b.subtitle, link: b.link,
          thumbnail: b.images?.[0] || null, analyticsType: `promo_${b.id}`,
        })
      }

      if (spotlight) {
        slides.push({
          key: 'spotlight', badge: spotlight.badge_text, color: spotlight.color,
          title: spotlight.title, subtitle: spotlight.subtitle, link: spotlight.link,
          thumbnail: spotlight.image_url || spotlight.stats?.avatar_bg_image || null,
          analyticsType: `spotlight_${spotlight.type}`,
        })
      }

      if (eventSpotlight) {
        slides.push({
          key: 'event-spotlight', badge: eventSpotlight.badge_text, color: eventSpotlight.color,
          title: eventSpotlight.title, subtitle: eventSpotlight.subtitle, link: eventSpotlight.link,
          thumbnail: eventSpotlight.image_url || null, analyticsType: 'event_spotlight',
        })
      }

      if (staffPick) {
        const subtitle = staffPick.primer || `${staffPick.avatar_name} deck`
        const badge = staffPick.is_new ? 'NEW STAFF PICK' : 'STAFF PICK'
        slides.push({
          key: 'staff-pick', badge, color: 'gold',
          title: staffPick.deck_name, subtitle,
          link: `/deck-rec/${staffPick.deck_id}`,
          thumbnail: staffPick.avatar_image || null, analyticsType: 'staff_pick',
        })
      }

      setItems(slides)
    })
  }, [])

  // Auto-advance every 12 seconds
  useEffect(() => {
    if (items.length <= 1) return
    timerRef.current = setInterval(() => setActive(i => (i + 1) % items.length), 12000)
    return () => clearInterval(timerRef.current)
  }, [items.length])

  const goTo = (idx) => {
    setActive(idx)
    clearInterval(timerRef.current)
    if (items.length > 1) {
      timerRef.current = setInterval(() => setActive(i => (i + 1) % items.length), 12000)
    }
  }

  const navigate = (dir) => {
    goTo((active + dir + items.length) % items.length)
  }

  if (!items.length) return null

  const item = items[active]
  const badgeStyle = BADGE_STYLES[item.color] || BADGE_STYLES.blue
  const isExternal = item.link && !item.link.startsWith('/')

  const handleClick = () => {
    navigator.sendBeacon?.('/api/analytics/banner-click',
      new Blob([JSON.stringify({ banner_type: item.analyticsType || 'promo' })], { type: 'application/json' }))
  }

  const Wrapper = isExternal ? 'a' : Link
  const wrapperProps = isExternal
    ? { href: item.link, target: '_blank', rel: 'noopener noreferrer' }
    : { to: item.link }

  return (
    <div className="relative mt-4">
      <Wrapper
        {...wrapperProps}
        onClick={handleClick}
        className="block relative overflow-hidden group"
      >
        {/* Background — image or gradient */}
        <div className="absolute inset-0 bg-bg-elevated">
          {item.thumbnail && (
            <img
              key={item.thumbnail}
              src={item.thumbnail}
              alt=""
              className="absolute inset-0 w-full h-full object-cover opacity-30 group-hover:opacity-40 transition-opacity duration-500"
              onError={(e) => { e.target.style.display = 'none' }}
            />
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-bg-dark/95 via-bg-dark/70 to-bg-dark/50" />
        </div>

        {/* Content overlay */}
        <div className="relative px-6 py-12 sm:py-16 sm:px-8 text-center flex flex-col items-center">
          <h3 className="text-3xl sm:text-4xl font-display text-text-primary leading-tight mb-2">
            {item.title}
          </h3>
          {item.subtitle && (
            <p className="text-base text-text-muted leading-relaxed max-w-lg mx-auto">
              {item.subtitle}
            </p>
          )}
          <div className="flex items-center gap-3 mt-4">
            <span className={`inline-block text-[10px] font-semibold px-2.5 py-0.5 ${badgeStyle} rounded-full uppercase tracking-wider`}>
              {item.badge}
            </span>
            <span className="inline-flex items-center gap-1 text-xs font-medium text-primary group-hover:text-primary-light transition-colors">
              Learn more <span className="group-hover:translate-x-1 transition-transform">&rarr;</span>
            </span>
          </div>
        </div>
      </Wrapper>

      {/* Navigation arrows — full-height hit area */}
      {items.length > 1 && (
        <>
          <button
            onClick={() => navigate(-1)}
            className="absolute left-0 top-0 bottom-0 z-10 w-12 flex items-center justify-center text-white/0 hover:text-white/70 hover:bg-gradient-to-r hover:from-black/30 hover:to-transparent transition-all text-lg"
            aria-label="Previous"
          >
            &lsaquo;
          </button>
          <button
            onClick={() => navigate(1)}
            className="absolute right-0 top-0 bottom-0 z-10 w-12 flex items-center justify-center text-white/0 hover:text-white/70 hover:bg-gradient-to-l hover:from-black/30 hover:to-transparent transition-all text-lg"
            aria-label="Next"
          >
            &rsaquo;
          </button>
        </>
      )}

      {/* Dot indicators */}
      {items.length > 1 && (
        <div className="flex justify-center gap-1.5 mt-2">
          {items.map((s, i) => (
            <button
              key={s.key}
              onClick={() => goTo(i)}
              className={`w-1.5 h-1.5 rounded-full transition-all duration-300 ${
                i === active ? 'bg-primary w-4' : 'bg-text-muted/30 hover:bg-text-muted/50'
              }`}
              aria-label={`Go to slide ${i + 1}`}
            />
          ))}
        </div>
      )}
    </div>
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
  const titleClickCount = useRef(0)
  const titleTimer = useRef(null)
  const navigate = useNavigate()

  // Fetch event leaderboard
  const fetchLeaderboard = useCallback(async (src) => {
    setLoading(true)
    try {
      if (src === 'limited') {
        const data = await getLimitedLeaderboard()
        const lb = data.leaderboard || data
        const stats = data.stats || {}
        const trophyRuns = data.trophy_runs || []
        setEventData({ limited: true, leaderboard: Array.isArray(lb) ? lb : [], stats, trophyRuns })
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
          className="text-4xl sm:text-5xl font-display text-secondary mb-2 cursor-default select-none"
        >
          Welcome to the Sorcery Community Leaderboard
        </h1>

        <PromoCarousel />
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
          {isLimited ? (
            <>
              {eventData.stats?.unique_players > 0 && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
                  <StatBox label="Players" value={eventData.stats.unique_players} />
                  <StatBox label="Runs Completed" value={eventData.stats.total_runs} />
                  <StatBox label="Matches Played" value={eventData.stats.total_matches} />
                  <StatBox label="Trophy Runs (4-0)" value={eventData.stats.trophy_runs} />
                </div>
              )}
              <LimitedLeaderboardTable data={leaderboard} />
              <TrophyRuns runs={eventData.trophyRuns} />
            </>
          ) : (
            <>
              <StatBar leaderboard={leaderboard} />
              <EventLeaderboardTable leaderboard={leaderboard} />
            </>
          )}
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
