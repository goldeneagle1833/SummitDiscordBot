import { useState, useEffect, useRef, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { get } from '@/api/client'
import { getEventLeaderboard, getLimitedLeaderboard } from '@/api/leaderboard'
import { StatBox, TrophyRuns, LimitedLeaderboardTable } from '@/components/leaderboard/LimitedLeaderboardContent'
import PostseasonName, { PostseasonLegend } from '@/components/player/BracketMarks'
import AvatarBadges, { AvatarCell } from '@/components/leaderboard/AvatarBadges'
import { getAvatarImageFiles, getSeasonAvatarBadges } from '@/api/cards'
import { badgesByPlayer, getAvatarImagePath } from '@/utils/avatarBadges'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

const DISCORD_URL = 'https://discord.gg/ZDqHSK9VGx'
const HERO_LOGO = '/static/images/summit-logo-hero.png'
// Flip to true when the store opens to everyone
const STORE_LIVE = false

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
    <div ref={containerRef} className="relative w-full max-w-md">
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

export function PromoCarousel() {
  const [items, setItems] = useState([])
  const [active, setActive] = useState(0)
  const [direction, setDirection] = useState(1) // 1 = next/right, -1 = prev/left
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

  // Auto-advance every 25 seconds
  useEffect(() => {
    if (items.length <= 1) return
    timerRef.current = setInterval(() => {
      setDirection(1)
      setActive(i => (i + 1) % items.length)
    }, 25000)
    return () => clearInterval(timerRef.current)
  }, [items.length])

  const goTo = (idx, dir) => {
    setDirection(dir ?? (idx > active ? 1 : -1))
    setActive(idx)
    clearInterval(timerRef.current)
    if (items.length > 1) {
      timerRef.current = setInterval(() => {
        setDirection(1)
        setActive(i => (i + 1) % items.length)
      }, 25000)
    }
  }

  const navigate = (dir) => {
    goTo((active + dir + items.length) % items.length, dir)
  }

  // Touch swipe: once a gesture locks to the horizontal axis it drags the
  // slide, and the click that follows is swallowed so a swipe never opens
  // the article underneath.
  const touchRef = useRef(null)
  const swipedRef = useRef(false)
  const [dragX, setDragX] = useState(0)

  const handleTouchStart = (e) => {
    if (items.length <= 1) return
    const t = e.touches[0]
    touchRef.current = { x: t.clientX, y: t.clientY, axis: null, dx: 0 }
    swipedRef.current = false
  }

  const handleTouchMove = (e) => {
    const start = touchRef.current
    if (!start) return
    const t = e.touches[0]
    const dx = t.clientX - start.x
    const dy = t.clientY - start.y
    if (!start.axis && (Math.abs(dx) > 8 || Math.abs(dy) > 8)) {
      start.axis = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y'
    }
    if (start.axis === 'x') {
      start.dx = dx
      setDragX(dx)
    }
  }

  const handleTouchEnd = () => {
    const start = touchRef.current
    touchRef.current = null
    setDragX(0)
    if (start?.axis !== 'x') return
    swipedRef.current = true
    if (Math.abs(start.dx) > 40) navigate(start.dx < 0 ? 1 : -1)
  }

  const handleClickCapture = (e) => {
    if (!swipedRef.current) return
    swipedRef.current = false
    e.preventDefault()
    e.stopPropagation()
  }

  if (!items.length) return null

  return (
    <div
      className="relative h-56 sm:h-64 overflow-hidden rounded-[10px] border border-border"
      style={{ touchAction: 'pan-y' }}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      onTouchCancel={handleTouchEnd}
      onClickCapture={handleClickCapture}
    >
      {/* All slides rendered, positioned absolutely, with slide transition */}
      {items.map((item, i) => {
        const badgeStyle = BADGE_STYLES[item.color] || BADGE_STYLES.blue
        const isExternal = item.link && !item.link.startsWith('/')
        const Wrapper = isExternal ? 'a' : Link
        const wrapperProps = isExternal
          ? { href: item.link, target: '_blank', rel: 'noopener noreferrer' }
          : { to: item.link }
        const isActive = i === active

        const handleClick = () => {
          navigator.sendBeacon?.('/api/analytics/banner-click',
            new Blob([JSON.stringify({ banner_type: item.analyticsType || 'promo' })], { type: 'application/json' }))
        }

        return (
          <Wrapper
            key={item.key}
            {...wrapperProps}
            onClick={handleClick}
            className="absolute inset-0 overflow-hidden group transition-all duration-700 ease-in-out"
            style={{
              opacity: isActive ? 1 : 0,
              transform: isActive ? `translateX(${dragX}px)` : `translateX(${direction * 60}px)`,
              transition: dragX ? 'none' : undefined,
              pointerEvents: isActive ? 'auto' : 'none',
            }}
          >
            {/* Background — image or gradient */}
            <div className="absolute inset-0 bg-bg-elevated">
              {item.thumbnail && (
                <img
                  src={item.thumbnail}
                  alt=""
                  className="absolute inset-0 w-full h-full object-cover opacity-30 group-hover:opacity-40 transition-opacity duration-500"
                  onError={(e) => { e.target.style.display = 'none' }}
                />
              )}
              <div className="absolute inset-0 bg-gradient-to-t from-bg-dark/95 via-bg-dark/70 to-bg-dark/50" />
            </div>

            {/* Content overlay */}
            <div className="relative h-full px-12 sm:px-14 pb-6 text-center flex flex-col items-center justify-center">
              <h3 className="text-2xl sm:text-4xl font-display text-text-primary leading-tight mb-1 sm:mb-2 line-clamp-2">
                {item.title}
              </h3>
              {item.subtitle && item.subtitle.trim() !== item.title?.trim() && (
                <p className="text-sm sm:text-base text-text-muted leading-snug sm:leading-relaxed max-w-lg mx-auto line-clamp-2">
                  {item.subtitle}
                </p>
              )}
              <div className="flex items-center gap-3 mt-3 sm:mt-4 shrink-0">
                <span className={`inline-block text-[10px] font-semibold px-2.5 py-0.5 ${badgeStyle} rounded-full uppercase tracking-wider`}>
                  {item.badge}
                </span>
                <span className="inline-flex items-center gap-1 text-xs font-medium text-secondary group-hover:text-secondary-light transition-colors">
                  Learn more <span className="group-hover:translate-x-1 transition-transform">&rarr;</span>
                </span>
              </div>
            </div>
          </Wrapper>
        )
      })}

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
        <div className="absolute bottom-3 left-0 right-0 z-10 flex justify-center gap-1.5">
          {items.map((s, i) => (
            <button
              key={s.key}
              onClick={() => goTo(i)}
              className={`w-1.5 h-1.5 rounded-full transition-all duration-300 ${
                i === active ? 'bg-secondary w-4' : 'bg-text-muted/30 hover:bg-text-muted/50'
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
  // Avatar-mode seasons list one row per player and avatar; count people once
  const players = new Set(leaderboard.map((p) => String(p.id))).size
  const top = leaderboard[0][eloKey]
  const avg = Math.round(leaderboard.reduce((s, p) => s + (p[eloKey] || 0), 0) / total)
  const stats = [['Players', players]]
  if (total !== players) stats.push(['Avatar Entries', total])
  stats.push(['Top ELO', top], ['Avg ELO', avg])
  return (
    <div className="flex flex-wrap gap-x-9 gap-y-3">
      {stats.map(([label, val]) => (
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
    <>
      <p className="text-text-muted text-sm mb-4">Or catch up on some Sorcery content:</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
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
    </>
  )
}

// ── ELO Source Toggle ─────────────────────────────────────────

const STORAGE_KEY = 'home_elo_source_preference'

// Paper is hidden: nobody plays on the paper ladder
const SOURCE_LABELS = { online: 'Online', limited: 'Limited' }

function EloToggle({ source, onChange }) {
  return (
    <div className="inline-flex bg-bg-surface border border-border rounded-soft overflow-hidden">
      {['online', 'limited'].map((s) => (
        <button
          key={s}
          onClick={() => onChange(s)}
          className={`px-4 py-1.5 text-sm font-medium transition-colors capitalize ${
            source === s
              ? 'bg-brand-blue text-white'
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

/** Each row's position among the rows on the same avatar ({ place, of }), in ladder order. */
function rankWithinAvatar(leaderboard) {
  const totals = {}
  for (const row of leaderboard) totals[row.avatar] = (totals[row.avatar] || 0) + 1
  const seen = {}
  return leaderboard.map((row) => {
    seen[row.avatar] = (seen[row.avatar] || 0) + 1
    return { place: seen[row.avatar], of: totals[row.avatar] }
  })
}

function avatarImageSrc(avatar, files) {
  const file = avatar ? getAvatarImagePath(avatar, files) : null
  return file ? `/avatar-images/${file}` : null
}

const RANK_LABELS = { 1: 'I', 2: 'II', 3: 'III' }

function RankCell({ rank, pinned }) {
  if (pinned) return <span className="font-display text-lg text-secondary">{rank}</span>
  if (rank <= 3) {
    return (
      <span className={`inline-flex items-center justify-center w-7 h-7 rounded text-xs font-bold ${
        rank === 1 ? 'bg-yellow-500/20 text-yellow-400' :
        rank === 2 ? 'bg-gray-400/20 text-gray-300' :
        'bg-amber-700/20 text-amber-600'
      }`}>
        {RANK_LABELS[rank]}
      </span>
    )
  }
  return <span className="text-text-muted">{rank}</span>
}

function EventLeaderboardTable({ leaderboard, eloKey = 'event_elo', avatarBadges = {}, avatarMode = false, avatarImageFiles = [], userId = null }) {
  if (!leaderboard.length) {
    return <p className="text-center text-text-muted py-8">No matches played yet</p>
  }
  // Player mode: the season "top player with this avatar" badges get their own
  // column. Avatar mode: every row instead shows where that entry ranks among
  // everyone playing the same avatar this season.
  const showBadges = !avatarMode && Object.keys(avatarBadges || {}).length > 0
  const avatarRanks = avatarMode ? rankWithinAvatar(leaderboard) : null
  const badgesForRow = (player) => (avatarBadges || {})[String(player.id)] || []
  const isMine = (player) => userId != null && String(player.id) === String(userId)
  // The viewer's own entries (one per avatar in avatar mode) repeat above #1
  // so they never have to scroll to find themselves.
  const pinned = leaderboard
    .map((player, index) => ({ player, index }))
    .filter(({ player }) => isMine(player))

  const renderRow = (player, index, isPinned) => {
    const rank = index + 1
    const mine = isMine(player)
    const rowClass = isPinned
      ? 'bg-brand-panel border-b border-brand-line'
      : `border-b border-border/50 transition-colors ${mine ? 'bg-brand-panel/50' : 'hover:bg-bg-elevated/40'}`
    return (
      <tr
        key={`${isPinned ? 'pinned' : 'row'}-${player.entry_id || player.id}`}
        className={`${rowClass} ${rank <= 3 || isPinned ? 'font-semibold' : ''}`}
      >
        <td className="py-2.5 px-4">
          <RankCell rank={isPinned ? `#${rank}` : rank} pinned={isPinned} />
        </td>
        <td className="py-2.5 px-4">
          <span className="inline-flex items-center gap-2">
            <PostseasonName playerId={player.id}>
              <Link to={`/player/${player.id}`} className="hover:text-secondary transition-colors">
                {player.name}
              </Link>
            </PostseasonName>
            {isPinned && (
              <span className="text-[10px] font-bold tracking-wider px-2 py-0.5 rounded-full bg-secondary text-bg-dark">YOU</span>
            )}
          </span>
        </td>
        {showBadges && (
          <td className="py-2.5 px-4">
            <AvatarBadges badges={badgesForRow(player)} withLabel />
          </td>
        )}
        {avatarMode && (
          <td className="py-2.5 px-4">
            <AvatarCell
              avatar={player.avatar}
              rank={avatarRanks[index]}
              imgSrc={avatarImageSrc(player.avatar, avatarImageFiles)}
            />
          </td>
        )}
        <td className="py-2.5 px-4 text-right">{player[eloKey]}</td>
      </tr>
    )
  }

  return (
    <div>
      <PostseasonLegend className="mb-2 px-1" />
      <div className="overflow-x-auto bg-bg-surface border border-border rounded-[10px]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wider">
              <th className="py-3 px-4 w-16 text-text-muted font-semibold">Rank</th>
              <th className="py-3 px-4 text-text-muted font-semibold">Player</th>
              {showBadges && <th className="py-3 px-4 text-text-muted font-semibold">Badge</th>}
              {avatarMode && <th className="py-3 px-4 text-text-muted font-semibold">Avatar</th>}
              <th className="py-3 px-4 text-right text-text-muted font-semibold">ELO</th>
            </tr>
          </thead>
          <tbody>
            {pinned.map(({ player, index }) => renderRow(player, index, true))}
            {leaderboard.map((player, index) => renderRow(player, index, false))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Store Card ────────────────────────────────────────────────

function StoreCard() {
  return (
    <div className="flex flex-col justify-between gap-5 p-6 bg-brand-panel border border-brand-line rounded-[10px] lg:flex-1">
      <div className="flex flex-col gap-2.5 items-start">
        {!STORE_LIVE && (
          <span className="text-xs font-bold tracking-[0.12em] uppercase px-2.5 py-1 rounded-full border border-secondary text-secondary">
            Coming soon
          </span>
        )}
        <h2 className="font-display text-3xl text-secondary">Summit Store</h2>
        <p className="text-text/80 leading-relaxed">
          Support the Summit and other Sorcery groups by picking up tokens or merch.
        </p>
      </div>
      {STORE_LIVE ? (
        <Link
          to="/store"
          className="inline-flex items-center justify-center h-12 px-6 rounded-soft bg-brand-blue hover:bg-brand-blue-light text-white font-semibold transition-colors"
        >
          Shop Summit Store
        </Link>
      ) : (
        <button
          type="button"
          disabled
          className="inline-flex items-center justify-center h-12 px-6 rounded-soft border border-border bg-bg-elevated text-text-muted font-semibold cursor-not-allowed"
        >
          Shop Summit Store
        </button>
      )}
    </div>
  )
}

/** "Event ends Oct 31." from the bot's scheduled end (unix seconds), or null when unscheduled. */
function eventEndsText(scheduledEndAt) {
  if (!scheduledEndAt) return null
  const date = new Date(scheduledEndAt * 1000)
  if (Number.isNaN(date.getTime())) return null
  return `Event ends ${date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}.`
}

// ── Home Page ─────────────────────────────────────────────────

export default function Home() {
  usePageTitle('Sorcerers Summit')
  const { user } = useAuth()
  const [source, setSource] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === 'limited' ? 'limited' : 'online'
    } catch {
      return 'online'
    }
  })
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
        const data = await getEventLeaderboard()
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

  // Current-season "top player with this avatar" badges (online leaderboard)
  const [avatarBadges, setAvatarBadges] = useState({})
  const [avatarImageFiles, setAvatarImageFiles] = useState([])
  useEffect(() => {
    let cancelled = false
    Promise.all([getSeasonAvatarBadges(), getAvatarImageFiles()])
      .then(([data, files]) => {
        if (cancelled) return
        setAvatarBadges(badgesByPlayer(data?.badges, files))
        setAvatarImageFiles(files || [])
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

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
  const avatarMode = eventData?.event?.elo_mode === 'avatar'
  const endsText = eventEndsText(eventData?.event?.scheduled_end_at)

  return (
    <div className="space-y-10">
      {/* Hero */}
      <section className="grid lg:grid-cols-2 gap-8 items-center pt-2">
        <div className="flex flex-col gap-6 order-2 lg:order-1">
          <p className="text-[13px] font-semibold tracking-[0.16em] uppercase text-brand-sky">Sorcery: Community</p>
          <h1
            onClick={handleTitleClick}
            className="text-5xl sm:text-7xl font-display font-bold text-white leading-none cursor-default select-none"
          >
            Climb the Summit.
          </h1>
          <p className="max-w-lg text-lg leading-relaxed text-text/80">
            Ranked ladders, event standings, decklists and stats for every Sorcery player in the community.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link
              to="/elo"
              className="inline-flex items-center h-12 px-6 rounded-soft border border-white text-white font-semibold hover:bg-white/10 transition-colors"
            >
              View past leaderboards
            </Link>
            <a
              href={DISCORD_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center h-12 px-6 rounded-soft bg-secondary hover:bg-secondary-light text-bg-dark font-bold transition-colors"
            >
              Join the Discord
            </a>
          </div>
          <PlayerSearch />
        </div>
        <img
          src={HERO_LOGO}
          alt="Sorcerers Summit mountain logo"
          width={1063}
          height={776}
          className="order-1 lg:order-2 w-full max-w-[280px] sm:max-w-[420px] lg:max-w-[580px] h-auto mx-auto lg:mr-0"
        />
      </section>

      {/* Promos + store */}
      <section className="flex flex-col lg:flex-row gap-5">
        <div className="lg:flex-[2] min-w-0 empty:hidden">
          <PromoCarousel />
        </div>
        <StoreCard />
      </section>

      {/* Event Leaderboard or No-Event */}
      {loading ? (
        <Spinner className="py-16" />
      ) : hasEvent ? (
        <section>
          <div className="flex flex-wrap justify-between items-end gap-4 mb-5">
            {isLimited ? (
              <div>
                <h2 className="text-3xl font-display text-white">Limited Format Leaderboard</h2>
                <p className="text-sm text-text-muted mt-1">Rankings for limited format matches</p>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-3">
                <h2 className="text-3xl font-display text-white">{eventData.event.event_name}</h2>
                {avatarMode && (
                  <span className="text-[11px] font-bold tracking-[0.12em] uppercase px-2.5 py-1 rounded-full bg-brand-panel border border-brand-line text-brand-sky">
                    Avatar mode
                  </span>
                )}
              </div>
            )}
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
              <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-4">
                <StatBar leaderboard={leaderboard} />
                {(avatarMode || endsText) && (
                  <p className="max-w-lg text-[13px] leading-relaxed text-text-muted md:text-right">
                    {avatarMode && 'Each avatar is rated separately, so a player can appear once per avatar. Top cut still gives each player one invite. '}
                    {endsText && <span className="text-text font-semibold">{endsText}</span>}
                  </p>
                )}
              </div>
              <EventLeaderboardTable
                leaderboard={leaderboard}
                avatarBadges={source === 'online' ? avatarBadges : undefined}
                avatarImageFiles={avatarImageFiles}
                avatarMode={avatarMode}
                userId={user ? user.user_id : null}
              />
            </>
          )}
        </section>
      ) : (
        <section className="text-center py-4">
          <div className="flex justify-center mb-6">
            <EloToggle source={source} onChange={handleSourceChange} />
          </div>
          <div className="max-w-2xl mx-auto px-6 py-10 mb-8 bg-bg-surface border border-border rounded-[10px]">
            <h2 className="text-3xl font-display text-white mb-2">No Active Event</h2>
            <p className="text-text-muted mb-6">Check back soon for the next event leaderboard!</p>
            <div className="flex flex-wrap justify-center gap-3">
              <Link
                to="/elo"
                className="inline-flex items-center h-11 px-5 rounded-soft border border-white text-white font-semibold hover:bg-white/10 transition-colors"
              >
                View past leaderboards
              </Link>
              <Link
                to="/avatars"
                className="inline-flex items-center h-11 px-5 rounded-soft bg-brand-blue hover:bg-brand-blue-light text-white font-semibold transition-colors"
              >
                Avatar Win Rates
              </Link>
            </div>
          </div>
          <YouTubeVideos />
        </section>
      )}
    </div>
  )
}
