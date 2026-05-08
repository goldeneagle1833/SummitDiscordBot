import { useState, useEffect, useRef } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'

const NAV_LINKS = [
  { to: '/', label: 'Home' },
  { to: '/community', label: 'Community' },
  { href: 'https://discord.gg/ZDqHSK9VGx', label: 'Discord' },
  { href: 'https://patreon.com/TheSorcerersSummit?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_fan&utm_content=copyLink', label: 'Patreon' },
  { to: '/about', label: 'About' },
]

function ConfirmMatchModal({ confirmation, onClose, onConfirmed }) {
  const [deckUrl, setDeckUrl] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const youWon = confirmation.winner_discord_id === confirmation.opponent_discord_id

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const handleSubmit = async () => {
    setSaving(true)
    setError(null)
    try {
      const res = await fetch(`/api/match-report/confirm/${confirmation.id}`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ deck_url: deckUrl.trim() || undefined }),
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
        setCount(pending.length)
      })
      .catch(() => {})
  }

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

export default function Nav() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const { user, loading } = useAuth()
  const location = useLocation()

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
            {/* Nav links - visible on desktop */}
            {NAV_LINKS.map(({ to, href, label }) =>
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
          <SidebarExternal href="https://discord.gg/ZDqHSK9VGx" label="Discord" />
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

          {/* Main navigation */}
          <SidebarLink to="/avatars" label="Avatar Winrates" location={location} onClick={close} />
          <SidebarLink to="/deck-rec" label="Sorcery Deck Rec" location={location} onClick={close} />
          <SidebarLink to="/elements" label="Element Winrates" location={location} onClick={close} />
          <SidebarLink to="/explorer" label="Community Series" location={location} onClick={close} />
          <SidebarLink to="/top-8" label="Top 8 Decks" location={location} onClick={close} />
          <SidebarLink to="/fun-stats" label="Fun Stats" location={location} onClick={close} />
          {user?.is_admin && (
            <SidebarLink to="/cards" label="Card Winrates" location={location} onClick={close} />
          )}
          <SidebarLink to="/elo" label="ELO Leaderboards" location={location} onClick={close} />
          <SidebarLink to="/elo/limited" label="Limited Leaderboard" location={location} onClick={close} />
          <SidebarLink to="/match-history" label="Match History" location={location} onClick={close} />
          <SidebarLink to="/life-counter" label="Life Counter" location={location} onClick={close} />
          <SidebarLink to="/help" label="Help" location={location} onClick={close} />
          <SidebarLink to="/community" label="Community" location={location} onClick={close} />
          <SidebarLink to="/curio-tracking" label="Curio Tracking" location={location} onClick={close} />
        </div>
      </aside>
    </>
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
