import { useState, useEffect, useRef } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { getStreamerBanner } from '@/api/streamers'

const PERMANENT_LINKS = ['Home', 'Discord', 'Facebook', 'Reddit', 'About', 'Patreon']

const ALL_NAV_OPTIONS = [
  { to: '/', label: 'Home' },
  { to: '/community', label: 'Community' },
  { href: 'https://discord.gg/ZDqHSK9VGx', label: 'Discord' },
  { href: 'https://www.facebook.com/groups/858917126995929', label: 'Facebook' },
  { href: 'https://www.reddit.com/r/SorcerersSummit/', label: 'Reddit' },
  { href: 'https://patreon.com/TheSorcerersSummit?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_fan&utm_content=copyLink', label: 'Patreon' },
  { to: '/about', label: 'About' },
  { to: '/avatars', label: 'Avatar Winrates' },
  { to: '/avatars/top-players', label: 'Avatar Top 16' },
  { to: '/deck-rec', label: 'Sorcery Deck Rec' },
  { to: '/deck-builder', label: 'Deck Visualizer' },
  { to: '/elements', label: 'Element Winrates' },
  { to: '/explorer', label: 'Community Series' },
  { to: '/top-8', label: 'Top 8 Decks' },
  { to: '/fun-stats', label: 'Fun Stats' },
  { to: '/rumble', label: 'Rumble' },
  { to: '/elo', label: 'ELO Leaderboards' },
  { to: '/match-history', label: 'Match History' },
  { to: '/life-counter', label: 'Life Counter' },
  { to: '/help', label: 'Help' },
  { to: '/card-points', label: 'Omens' },
]

const DEFAULT_NAV_LABELS = ['Home', 'Community', 'Discord', 'Facebook', 'Reddit', 'Patreon', 'About']
const STORAGE_KEY = 'summit-nav-prefs'

function getNavPrefs() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) return JSON.parse(stored)
  } catch {}
  return null
}

function saveNavPrefs(labels) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(labels))
}

function ConfirmMatchModal({ confirmation, onClose, onConfirmed }) {
  const [deckUrl, setDeckUrl] = useState('')
  const [avatar, setAvatar] = useState('')
  const [avatars, setAvatars] = useState([])
  const [matchComment, setMatchComment] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const youWon = confirmation.winner_discord_id === confirmation.opponent_discord_id
  const confirmingPlayerAvatar = youWon
    ? confirmation.winner_avatar
    : confirmation.loser_avatar
  const avatarRequired = Boolean(
    (confirmation.winner_avatar || confirmation.loser_avatar)
    && !confirmingPlayerAvatar
    && confirmation.match_type !== 'casual'
  )

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  useEffect(() => {
    fetch('/api/list-all-avatars')
      .then((response) => response.ok ? response.json() : [])
      .then(setAvatars)
      .catch(() => {})
  }, [])

  const handleSubmit = async () => {
    if (avatarRequired && !deckUrl.trim() && !avatar) {
      setError('Provide your Curiosa deck URL or select the avatar you played.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const res = await fetch(`/api/match-report/confirm/${confirmation.id}`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          deck_url: deckUrl.trim() || undefined,
          avatar: avatar || undefined,
          match_comment: matchComment.trim() || undefined,
        }),
      })
      const data = await res.json()
      if (data.success) {
        onConfirmed()
      } else {
        setError(data.error?.message || 'Failed to confirm')
      }
    } catch {
      setError('Network error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[1100] flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-bg-surface border border-border rounded-lg w-full max-w-md mx-4" onClick={(e) => e.stopPropagation()}>
        <div className="p-6">
          <h3 className="text-lg font-semibold text-text-primary mb-4">Confirm Match</h3>

          {/* Game stats */}
          <div className="bg-bg-elevated rounded-lg p-4 mb-4 space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-text-muted">Reported by</span>
              <span className="text-white font-medium">{confirmation.submitter_display_name || 'Unknown'}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-text-muted">Result</span>
              <span className={`font-medium ${youWon ? 'text-green-400' : 'text-red-400'}`}>
                {youWon ? 'You won' : 'You lost'}
              </span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-text-muted">Final life</span>
              <span className="text-white">{confirmation.final_life_winner} - {confirmation.final_life_loser}</span>
            </div>
            {confirmation.match_type && (
              <div className="flex justify-between text-sm">
                <span className="text-text-muted">Type</span>
                <span className="text-white capitalize">{confirmation.match_type}</span>
              </div>
            )}
            {(confirmation.winner_avatar || confirmation.loser_avatar) && (
              <>
              <div className="flex justify-between text-sm">
                <span className="text-text-muted">Winner avatar</span>
                <span className="text-white">{confirmation.winner_avatar || 'Not provided'}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-text-muted">Loser avatar</span>
                <span className="text-white">{confirmation.loser_avatar || 'Not provided'}</span>
              </div>
              <p className="text-xs text-amber-300 pt-1">
                Confirm only if both the result and avatars are correct. Otherwise, deny this report.
              </p>
              </>
            )}
            {confirmation.went_first && (
              <div className="flex justify-between text-sm">
                <span className="text-text-muted">First player</span>
                <span className="text-white capitalize">{confirmation.went_first}</span>
              </div>
            )}
          </div>

          {/* Deck URL input */}
          <div className="mb-4">
            <label className="text-xs text-text-muted block mb-1">Your Deck URL (optional)</label>
            <input
              type="url"
              value={deckUrl}
              onChange={(e) => setDeckUrl(e.target.value)}
              placeholder="https://curiosa.io/decks/..."
              className="w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm"
            />
          </div>

          {confirmingPlayerAvatar ? (
            <div className="mb-4 rounded border border-border bg-bg-elevated px-3 py-2">
              <p className="text-xs text-text-muted">Your reported avatar</p>
              <p className="text-sm text-white font-medium">{confirmingPlayerAvatar}</p>
              <p className="text-xs text-amber-300 mt-1">Deny the report if this is incorrect.</p>
            </div>
          ) : (
            <div className="mb-4">
              <label className="text-xs text-text-muted block mb-1">
                Your Avatar {avatarRequired ? '(required if no deck URL)' : '(optional)'}
              </label>
              <select
                value={avatar}
                onChange={(e) => setAvatar(e.target.value)}
                className="w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm"
              >
                <option value="">Detect from Curiosa deck</option>
                {avatars.map((name) => <option key={name} value={name}>{name}</option>)}
              </select>
            </div>
          )}

          {/* Match Comments */}
          <div className="mb-4">
            <label className="text-xs text-text-muted block mb-1">Match Comments (optional)</label>
            <textarea
              value={matchComment}
              onChange={(e) => setMatchComment(e.target.value)}
              placeholder="Any notes about the match?"
              rows={2}
              className="w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm resize-none"
            />
          </div>

          {error && <p className="text-xs text-red-400 mb-3">{error}</p>}

          <div className="flex justify-end gap-2">
            <button
              onClick={onClose}
              className="px-3 py-1.5 text-sm bg-bg-elevated border border-border rounded hover:border-secondary transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={saving}
              className="px-3 py-1.5 text-sm bg-green-600 text-white rounded hover:bg-green-500 transition-colors disabled:opacity-40"
            >
              {saving ? 'Confirming...' : 'Confirm Match'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function NotificationBell({ user }) {
  const [count, setCount] = useState(0)
  const [open, setOpen] = useState(false)
  const [confirmations, setConfirmations] = useState([])
  const [storeNotifs, setStoreNotifs] = useState([])
  const [acting, setActing] = useState({})
  const [feedback, setFeedback] = useState({})
  const [confirmModal, setConfirmModal] = useState(null)
  const ref = useRef(null)

  const fetchPending = () => {
    fetch('/api/match-report/pending', { credentials: 'include' })
      .then((r) => r.ok ? r.json() : { pending_confirmations: [] })
      .then((d) => {
        const pending = d.pending_confirmations || []
        setConfirmations(pending)
      })
      .catch(() => {})

    fetch('/api/store/notifications', { credentials: 'include' })
      .then((r) => r.ok ? r.json() : { notifications: [] })
      .then((d) => setStoreNotifs(d.notifications || []))
      .catch(() => {})
  }

  useEffect(() => {
    setCount(confirmations.length + storeNotifs.length)
  }, [confirmations, storeNotifs])

  useEffect(() => {
    if (!user) return
    fetchPending()
    const interval = setInterval(fetchPending, 60000)
    return () => clearInterval(interval)
  }, [user])

  useEffect(() => {
    if (!open) return
    const handleClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('click', handleClick)
    return () => document.removeEventListener('click', handleClick)
  }, [open])

  const handleDeny = async (id) => {
    setActing((prev) => ({ ...prev, [id]: true }))
    try {
      const res = await fetch(`/api/match-report/deny/${id}`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      const data = await res.json()
      if (data.success) {
        setFeedback((prev) => ({ ...prev, [id]: 'denied' }))
        setTimeout(() => fetchPending(), 1200)
      } else {
        setFeedback((prev) => ({ ...prev, [id]: data.error?.message || 'Failed' }))
      }
    } catch {
      setFeedback((prev) => ({ ...prev, [id]: 'Error denying' }))
    } finally {
      setActing((prev) => ({ ...prev, [id]: false }))
    }
  }

  if (!user || count === 0) return null

  const formatTime = (expiresAt) => {
    const remaining = expiresAt - Math.floor(Date.now() / 1000)
    if (remaining <= 0) return 'expired'
    const h = Math.floor(remaining / 3600)
    if (h > 24) return `${Math.floor(h / 24)}d`
    if (h > 0) return `${h}h`
    return `${Math.floor((remaining % 3600) / 60)}m`
  }

  return (
    <>
      <div className="relative" ref={ref}>
        <button
          className="relative flex items-center justify-center w-10 h-10 rounded hover:bg-white/10 transition-colors"
          onClick={(e) => { e.stopPropagation(); setOpen(!open) }}
          aria-label="Notifications"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" className="w-6 h-6">
            <path fill={count > 0 ? '#ef4444' : 'white'} d="M12 2C11.4477 2 11 2.44772 11 3V3.17071C8.83481 3.58254 7.17254 5.24481 6.76071 7.41L6 11.5L4.5 13V15H19.5V13L18 11.5L17.2393 7.41C16.8275 5.24481 15.1652 3.58254 13 3.17071V3C13 2.44772 12.5523 2 12 2Z" />
            <path fill={count > 0 ? '#ef4444' : 'white'} d="M10 17C10 18.1046 10.8954 19 12 19C13.1046 19 14 18.1046 14 17H10Z" />
          </svg>
          <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-600 text-white text-xs font-bold rounded-full flex items-center justify-center">
            {count > 9 ? '9+' : count}
          </span>
        </button>
        {open && (
          <div className="absolute right-0 top-full mt-2 w-80 max-h-96 bg-bg-elevated shadow-xl rounded-lg overflow-hidden z-[1001] border border-secondary/30">
            {/* Store order notifications */}
            {storeNotifs.length > 0 && (
              <>
                <div className="bg-primary/20 px-4 py-3 border-b border-white/10">
                  <h3 className="text-sm font-bold text-white uppercase tracking-wide">Orders</h3>
                </div>
                <div>
                  {storeNotifs.map((n) => (
                    <div key={`store-${n.id}`} className="px-4 py-3 border-b border-white/5 flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-white">{n.title}</p>
                        <p className="text-xs text-text-muted mt-0.5">{n.body}</p>
                      </div>
                      <button
                        onClick={async () => {
                          await fetch(`/api/store/notifications/${n.id}/dismiss`, {
                            method: 'POST', credentials: 'include',
                          })
                          setStoreNotifs((prev) => prev.filter((x) => x.id !== n.id))
                        }}
                        className="text-xs text-text-muted hover:text-white shrink-0"
                        aria-label="Dismiss"
                      >
                        &times;
                      </button>
                    </div>
                  ))}
                </div>
              </>
            )}
            <div className="bg-secondary/20 px-4 py-3 border-b border-white/10">
              <h3 className="text-sm font-bold text-white uppercase tracking-wide">Match Confirmations</h3>
            </div>
            <div className="overflow-y-auto max-h-80">
              {confirmations.length === 0 ? (
                <div className="p-6 text-center text-text-muted text-sm">No pending confirmations</div>
              ) : (
                confirmations.map((conf) => {
                  const youWon = conf.winner_discord_id === conf.opponent_discord_id
                  const fb = feedback[conf.id]
                  return (
                    <div
                      key={conf.id}
                      className="px-4 py-3 border-b border-white/5"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-semibold text-white truncate">{conf.submitter_display_name || 'Unknown'}</p>
                          <p className={`text-xs font-medium mt-0.5 ${youWon ? 'text-green-400' : 'text-red-400'}`}>
                            {youWon ? 'You won' : 'You lost'}
                          </p>
                          <p className="text-xs text-text-muted mt-1">Final: {conf.final_life_winner} - {conf.final_life_loser}</p>
                        </div>
                        <span className="text-xs px-2 py-0.5 bg-yellow-500/20 text-yellow-400 rounded-full whitespace-nowrap">
                          {formatTime(conf.expires_at)}
                        </span>
                      </div>
                      {/* Confirm / Deny actions */}
                      {fb === 'confirmed' ? (
                        <p className="text-xs text-green-400 mt-2 font-medium">Confirmed!</p>
                      ) : fb === 'denied' ? (
                        <p className="text-xs text-red-400 mt-2 font-medium">Denied</p>
                      ) : fb ? (
                        <p className="text-xs text-red-400 mt-2">{fb}</p>
                      ) : (
                        <div className="flex gap-2 mt-2">
                          <button
                            onClick={() => { setConfirmModal(conf); setOpen(false) }}
                            className="flex-1 px-3 py-1.5 text-xs font-medium bg-green-600/80 text-white rounded hover:bg-green-600 transition-colors"
                          >
                            Confirm
                          </button>
                          <button
                            onClick={() => handleDeny(conf.id)}
                            disabled={acting[conf.id]}
                            className="flex-1 px-3 py-1.5 text-xs font-medium bg-red-600/80 text-white rounded hover:bg-red-600 transition-colors disabled:opacity-40"
                          >
                            {acting[conf.id] ? '...' : 'Deny'}
                          </button>
                        </div>
                      )}
                    </div>
                  )
                })
              )}
            </div>
          </div>
        )}
      </div>

      {/* Confirm match modal */}
      {confirmModal && (
        <ConfirmMatchModal
          confirmation={confirmModal}
          onClose={() => setConfirmModal(null)}
          onConfirmed={() => {
            setFeedback((prev) => ({ ...prev, [confirmModal.id]: 'confirmed' }))
            setConfirmModal(null)
            setTimeout(() => fetchPending(), 1200)
          }}
        />
      )}
    </>
  )
}

function NavCustomizeModal({ activeLabels, onSave, onClose }) {
  const [selected, setSelected] = useState(new Set(activeLabels))

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const toggle = (label) => {
    if (PERMANENT_LINKS.includes(label)) return
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(label)) next.delete(label)
      else next.add(label)
      return next
    })
  }

  const handleSave = () => {
    const labels = ALL_NAV_OPTIONS
      .map((opt) => opt.label)
      .filter((l) => selected.has(l))
    onSave(labels)
    onClose()
  }

  const handleReset = () => {
    setSelected(new Set(DEFAULT_NAV_LABELS))
  }

  return (
    <div className="fixed inset-0 z-[1100] flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-bg-surface border border-border rounded-lg w-full max-w-sm mx-4" onClick={(e) => e.stopPropagation()}>
        <div className="p-6">
          <h3 className="text-lg font-semibold text-text-primary mb-1">Customize Nav Bar</h3>
          <p className="text-xs text-text-muted mb-4">Choose which links appear in your navigation bar.</p>

          <div className="space-y-1 max-h-72 overflow-y-auto">
            {ALL_NAV_OPTIONS.map(({ label }) => {
              const isPermanent = PERMANENT_LINKS.includes(label)
              const isActive = selected.has(label)
              return (
                <label
                  key={label}
                  className={`flex items-center gap-3 px-3 py-2 rounded cursor-pointer transition-colors ${
                    isPermanent ? 'opacity-50 cursor-not-allowed' : 'hover:bg-white/5'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={isActive}
                    disabled={isPermanent}
                    onChange={() => toggle(label)}
                    className="accent-secondary w-4 h-4"
                  />
                  <span className="text-sm text-text">{label}</span>
                  {isPermanent && <span className="text-xs text-text-muted ml-auto">Required</span>}
                </label>
              )
            })}
          </div>

          <div className="flex justify-between mt-4">
            <button
              onClick={handleReset}
              className="px-3 py-1.5 text-xs text-text-muted hover:text-text transition-colors"
            >
              Reset to Default
            </button>
            <div className="flex gap-2">
              <button
                onClick={onClose}
                className="px-3 py-1.5 text-sm bg-bg-elevated border border-border rounded hover:border-secondary transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                className="px-3 py-1.5 text-sm bg-secondary text-white rounded hover:bg-secondary/80 transition-colors"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function LiveIndicator() {
  const [streamer, setStreamer] = useState(null)

  useEffect(() => {
    const fetch_ = () => {
      getStreamerBanner()
        .then((data) => setStreamer(data.is_live ? data.streamer : null))
        .catch(() => setStreamer(null))
    }
    fetch_()
    const interval = setInterval(fetch_, 120000)
    return () => clearInterval(interval)
  }, [])

  if (!streamer) return null

  return (
    <a
      href={streamer.stream_url}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-center gap-1.5 text-sm text-text hover:text-secondary transition-colors"
      title={streamer.stream_title || `${streamer.display_name} is live`}
    >
      <span className="relative flex h-2.5 w-2.5">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-500 opacity-75" />
        <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-500" />
      </span>
      <span className="hidden sm:inline font-medium">{streamer.display_name}</span>
    </a>
  )
}

export default function Nav() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [customizeOpen, setCustomizeOpen] = useState(false)
  const [navLabels, setNavLabels] = useState(() => getNavPrefs() || DEFAULT_NAV_LABELS)
  const { user, loading } = useAuth()
  const location = useLocation()

  // Sync nav prefs from server when user logs in
  useEffect(() => {
    if (!user) return
    fetch('/api/nav-prefs', { credentials: 'include' })
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (data?.labels) {
          setNavLabels(data.labels)
          saveNavPrefs(data.labels)
        }
      })
      .catch(() => {})
  }, [user])

  const activeNavLinks = ALL_NAV_OPTIONS.filter((opt) => navLabels.includes(opt.label))

  const handleSavePrefs = (labels) => {
    setNavLabels(labels)
    saveNavPrefs(labels)
    // Save to server if logged in
    if (user) {
      fetch('/api/nav-prefs', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ labels }),
      }).catch(() => {})
    }
  }

  const close = () => setSidebarOpen(false)

  return (
    <>
      {/* Backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-[900]"
          onClick={close}
        />
      )}

      <nav className="bg-bg-surface border-b border-border sticky top-0 z-[1000]">
        <div className="max-w-content mx-auto px-4 flex items-center h-16">
          {/* Left: Hamburger (mobile only) + Brand */}
          <div className="flex items-center gap-4 flex-1">
            <button
              className="flex items-center justify-center w-10 h-10 rounded hover:bg-white/10 transition-colors"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              aria-label="Toggle menu"
            >
              <span className="text-2xl font-bold leading-none text-white">☰</span>
            </button>
            <Link to="/" className="font-display text-lg md:text-xl text-secondary hover:text-text transition-colors">
              Sorcerers Summit
            </Link>
          </div>

          {/* Right */}
          <div className="flex items-center gap-3 flex-1 justify-end">
            <LiveIndicator />

            {/* Nav links - visible on desktop */}
            {activeNavLinks.map(({ to, href, label }) =>
              href ? (
                <a
                  key={label}
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hidden md:inline-block text-text hover:text-secondary font-medium transition-colors"
                >
                  {label}
                </a>
              ) : (
                <Link
                  key={label}
                  to={to}
                  className={`hidden md:inline-block font-medium transition-colors ${
                    location.pathname === to ? 'text-secondary' : 'text-text hover:text-secondary'
                  }`}
                >
                  {label}
                </Link>
              )
            )}

            {/* Customize nav pencil icon - only when logged in */}
            {user && (
              <button
                onClick={() => setCustomizeOpen(true)}
                className="hidden md:flex items-center justify-center w-8 h-8 rounded hover:bg-white/10 transition-colors"
                aria-label="Customize navigation"
                title="Customize nav bar"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-text-muted hover:text-secondary">
                  <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
                </svg>
              </button>
            )}

            {/* Notification bell - single instance, always visible */}
            <NotificationBell user={user} />

            {/* Mobile life counter */}
            <Link
              to="/life-counter"
              className="flex md:hidden items-center justify-center w-10 h-10 rounded hover:bg-white/10 transition-colors"
              aria-label="Life Counter"
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" className="w-6 h-6">
                <circle cx="7" cy="6" r="2.5" fill="white" />
                <path d="M7 10C4.5 10 2.5 11.5 2.5 13.5V17H11.5V13.5C11.5 11.5 9.5 10 7 10Z" fill="white" />
                <circle cx="17" cy="6" r="2.5" fill="white" />
                <path d="M17 10C14.5 10 12.5 11.5 12.5 13.5V17H21.5V13.5C21.5 11.5 19.5 10 17 10Z" fill="white" />
              </svg>
            </Link>

            {/* Desktop auth */}
            {!loading && (
              <div className="hidden md:flex items-center gap-3">
                {user ? (
                  <>
                    <Link
                      to={`/player/${user.user_id}`}
                      className="text-primary font-semibold hover:text-primary-light transition-colors"
                    >
                      {user.username}
                    </Link>
                    <a
                      href="/api/logout"
                      className="text-sm text-text-muted hover:text-accent-red transition-colors"
                      onClick={(e) => {
                        e.preventDefault()
                        fetch('/api/logout', { credentials: 'include' })
                          .then(() => window.location.reload())
                      }}
                    >
                      Logout
                    </a>
                  </>
                ) : (
                  <Link
                    to={`/login?next=${encodeURIComponent(window.location.href)}`}
                    className="text-sm bg-primary/20 text-primary hover:bg-primary/30 px-3 py-1.5 rounded-soft transition-colors"
                  >
                    Login
                  </Link>
                )}
              </div>
            )}
          </div>
        </div>
      </nav>

      {/* Sidebar */}
      <aside
        className={`fixed top-0 left-0 h-full w-72 bg-bg-surface border-r border-border z-[950] transform transition-transform duration-300 overflow-y-auto ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="p-4 border-b border-border flex items-center justify-between">
          <Link to="/" className="font-display text-lg text-secondary" onClick={close}>
            Sorcerers Summit
          </Link>
          <button className="p-1 text-text-muted hover:text-text" onClick={close}>
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Navigation & External links - hidden on desktop since they're in the nav bar */}
        <div className="border-b border-border md:hidden">
          <SidebarLink to="/" label="Home" location={location} onClick={close} />
          <SidebarLink to="/community" label="Community" location={location} onClick={close} />
          {user?.is_store_admin && <SidebarLink to="/store" label="Store" location={location} onClick={close} />}
          <SidebarExternal href="https://discord.gg/ZDqHSK9VGx" label="Discord" />
          <SidebarExternal href="https://www.facebook.com/groups/858917126995929" label="Facebook" />
          <SidebarExternal href="https://www.reddit.com/r/SorcerersSummit/" label="Reddit" />
          <SidebarExternal href="https://patreon.com/TheSorcerersSummit?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_fan&utm_content=copyLink" label="Patreon" />
          <SidebarLink to="/about" label="About" location={location} onClick={close} />
        </div>

        {/* Auth section */}
        <div className="border-b border-border">
          {!loading && (
            user ? (
              <>
                <Link
                  to={`/player/${user.user_id}`}
                  className="block px-4 py-3 text-primary hover:bg-secondary/10 transition-colors font-semibold"
                  onClick={close}
                >
                  {user.username}
                </Link>
                <a
                  href="/api/logout"
                  className="block px-4 py-3 text-text-muted hover:bg-accent-red/10 hover:text-accent-red transition-colors text-sm"
                  onClick={(e) => {
                    e.preventDefault()
                    fetch('/api/logout', { credentials: 'include' })
                      .then(() => { close(); window.location.reload() })
                  }}
                >
                  Logout
                </a>
              </>
            ) : (
              <Link
                to={`/login?next=${encodeURIComponent(window.location.href)}`}
                className="block mx-4 my-3 text-center bg-primary/20 text-primary hover:bg-primary/30 px-3 py-2 rounded-soft transition-colors font-medium"
                onClick={close}
              >
                Login
              </Link>
            )
          )}
        </div>

        {/* Full navigation */}
        <div>
          {/* Creator link */}
          {user?.is_store_admin && (
            <div className="border-b border-border">
              <SidebarLink to="/admin/store" label="Store Admin" location={location} onClick={close} />
            </div>
          )}

          {(user?.is_creator || user?.is_admin) && (
            <div className="border-b border-border">
              <SidebarLink to="/creator" label="Creator Stats" location={location} onClick={close} />
            </div>
          )}

          {/* Admin link */}
          {user?.is_admin && (
            <div className="border-b border-border">
              <Link
                to="/admin/audit-log"
                className="block px-4 py-3 text-accent-red hover:bg-accent-red/10 transition-colors font-medium"
                onClick={close}
              >
                Admin Log
              </Link>
            </div>
          )}

          {/* Stats */}
          <SidebarHeading label="Stats" />
          <SidebarLink to="/avatars" label="Avatar Winrates" location={location} onClick={close} />
          <SidebarLink to="/avatars/top-players" label="Avatar Top 16" location={location} onClick={close} />
          <SidebarLink to="/elements" label="Element Winrates" location={location} onClick={close} />

          {/* Event Info */}
          <SidebarHeading label="Event Info" />
          <SidebarLink to="/top-8" label="Top 8 Decks" location={location} onClick={close} />
          <SidebarLink to="/deck-rec" label="Sorcery Deck Rec" location={location} onClick={close} />
          <SidebarLink to="/explorer" label="Community Series" location={location} onClick={close} />
          <SidebarLink to="/card-points" label="Omens" location={location} onClick={close} />

          {/* Summit Stats */}
          <SidebarHeading label="Summit Stats" />
          <SidebarLink to="/elo" label="ELO Leaderboards" location={location} onClick={close} />
          <SidebarLink to="/match-history" label="Match History" location={location} onClick={close} />
          <SidebarLink to="/rumble" label="Rumble" location={location} onClick={close} />
          <SidebarLink to="/fun-stats" label="Fun Stats" location={location} onClick={close} />

          {/* Tools & Info */}
          <SidebarHeading label="Tools & Info" />
          <SidebarLink to="/deck-builder" label="Deck Visualizer" location={location} onClick={close} />
          <SidebarLink to="/life-counter" label="Life Counter" location={location} onClick={close} />
          <SidebarLink to="/help" label="Help" location={location} onClick={close} />
          <SidebarLink to="/community" label="Community" location={location} onClick={close} />
          {user?.is_store_admin && <SidebarLink to="/store" label="Store" location={location} onClick={close} />}
        </div>
      </aside>

      {/* Nav customize modal */}
      {customizeOpen && (
        <NavCustomizeModal
          activeLabels={navLabels}
          onSave={handleSavePrefs}
          onClose={() => setCustomizeOpen(false)}
        />
      )}
    </>
  )
}

function SidebarHeading({ label }) {
  return (
    <div className="px-4 pt-4 pb-1">
      <span className="text-xs font-bold text-text-muted uppercase tracking-wider">{label}</span>
    </div>
  )
}

function SidebarLink({ to, label, location, onClick }) {
  const active = location.pathname === to
  return (
    <Link
      to={to}
      className={`block px-4 py-3 transition-colors font-medium ${
        active
          ? 'text-secondary bg-secondary/10'
          : 'text-text hover:bg-secondary/10 hover:text-secondary'
      }`}
      onClick={onClick}
    >
      {label}
    </Link>
  )
}

function SidebarExternal({ href, label }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="block px-4 py-3 text-text hover:bg-secondary/10 hover:text-secondary transition-colors font-medium"
    >
      {label}
    </a>
  )
}
