import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'

const mainLinks = [
  { to: '/elo', label: 'Leaderboard' },
  { to: '/match-history', label: 'Matches' },
  { to: '/top-8', label: 'Events' },
  { to: '/community', label: 'Community' },
]

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
        <div className="max-w-content mx-auto px-4 flex items-center justify-between h-14">
          {/* Hamburger */}
          <button
            className="p-2 text-text-muted hover:text-text"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            aria-label="Toggle menu"
          >
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>

          {/* Logo */}
          <Link to="/" className="font-display text-xl text-secondary hover:text-secondary-light transition-colors">
            Sorcerers Summit
          </Link>

          {/* Desktop Nav Links */}
          <div className="hidden md:flex items-center gap-6">
            {mainLinks.map(({ to, label }) => (
              <Link
                key={to}
                to={to}
                className={`text-sm font-medium transition-colors ${
                  location.pathname.startsWith(to)
                    ? 'text-primary'
                    : 'text-text-muted hover:text-text'
                }`}
              >
                {label}
              </Link>
            ))}
          </div>

          {/* Auth / Life Counter */}
          <div className="flex items-center gap-3">
            <Link
              to="/life-counter"
              className="text-sm text-text-muted hover:text-text transition-colors hidden sm:inline"
            >
              Life Counter
            </Link>
            {!loading && (
              user ? (
                <div className="flex items-center gap-2">
                  <Link
                    to={`/player/${user.user_id}`}
                    className="text-sm text-primary hover:text-primary-light transition-colors"
                  >
                    {user.username}
                  </Link>
                  <a
                    href="/api/logout"
                    className="text-sm text-text-muted hover:text-text transition-colors"
                    onClick={(e) => {
                      e.preventDefault()
                      fetch('/api/logout', { credentials: 'include' })
                        .then(() => window.location.href = '/')
                    }}
                  >
                    Logout
                  </a>
                </div>
              ) : (
                <Link
                  to="/login"
                  className="text-sm bg-primary/20 text-primary hover:bg-primary/30 px-3 py-1.5 rounded-soft transition-colors"
                >
                  Login
                </Link>
              )
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

        {/* Navigation & External links */}
        <div className="border-b border-border">
          <SidebarLink to="/" label="Home" location={location} onClick={close} />
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
                      .then(() => { close(); window.location.href = '/' })
                  }}
                >
                  Logout
                </a>
              </>
            ) : (
              <Link
                to="/login"
                className="block mx-4 my-3 text-center bg-primary/20 text-primary hover:bg-primary/30 px-3 py-2 rounded-soft transition-colors font-medium"
                onClick={close}
              >
                Login
              </Link>
            )
          )}
        </div>

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
        <SidebarLink to="/fun-stats" label="Fun Stats" location={location} onClick={close} />
        {user?.is_admin && (
          <>
            <SidebarLink to="/cards" label="Card Winrates" location={location} onClick={close} />
            <SidebarLink to="/live-popular-cards" label="Live Popular Cards" location={location} onClick={close} />
          </>
        )}
        <SidebarLink to="/elo" label="ELO Leaderboards" location={location} onClick={close} />
        <SidebarLink to="/elo/limited" label="Limited Leaderboard" location={location} onClick={close} />
        <SidebarLink to="/match-history" label="Match History" location={location} onClick={close} />
        <SidebarLink to="/top-8" label="Top 8 Decks" location={location} onClick={close} />
        <SidebarLink to="/life-counter" label="Life Counter" location={location} onClick={close} />
        <SidebarLink to="/help" label="Help" location={location} onClick={close} />
        <SidebarLink to="/community" label="Community" location={location} onClick={close} />
        <SidebarLink to="/curio-tracking" label="Curio Tracking" location={location} onClick={close} />
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
