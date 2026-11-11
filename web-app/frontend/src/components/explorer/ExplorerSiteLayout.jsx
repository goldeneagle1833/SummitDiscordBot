import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { getStorefronts } from '@/api/store'
import useNewContent from '@/hooks/useNewContent'
import { ES_PATHS, ES_COMPASS, ES_STOREFRONT_SLUG } from '@/utils/explorerSite'
import '@/styles/explorerSite.css'

/**
 * The Explorer Series mini-site's own header, menu and footer. It is still the
 * Summit web app underneath (same login, same API), but it looks and reads as
 * its own website.
 */

function useExplorerShopOpen() {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    let alive = true
    getStorefronts()
      .then((data) => {
        if (alive) setOpen((data?.storefronts || []).some((s) => s.slug === ES_STOREFRONT_SLUG))
      })
      .catch(() => {})
    return () => { alive = false }
  }, [])
  return open
}

function useClickAway(ref, onAway) {
  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) onAway() }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [ref, onAway])
}

function navClass({ isActive }) {
  return `pb-1 border-b-2 transition-colors ${
    isActive ? 'border-[color:var(--es-rust)] text-[color:var(--es-ink)]' : 'border-transparent es-muted hover:text-[color:var(--es-ink)]'
  }`
}

const ADMIN_LINKS = [
  { to: ES_PATHS.admin, label: 'Admin home' },
  { to: ES_PATHS.content, label: 'Edit site content' },
  { to: ES_PATHS.applications, label: 'Host applications' },
  { to: ES_PATHS.calendar, label: 'Events calendar' },
]

function AdminMenu({ onNavigate }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useClickAway(ref, () => setOpen(false))
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="es-btn-ghost !py-1.5 !px-3 text-sm"
      >
        Admin <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-56 es-card py-1 z-50 text-sm">
          {ADMIN_LINKS.map((l) => (
            <Link key={l.to} to={l.to} onClick={() => { setOpen(false); onNavigate?.() }} className="block px-4 py-2 hover:bg-white/5">{l.label}</Link>
          ))}
        </div>
      )}
    </div>
  )
}

function AccountLink({ user, loading }) {
  if (loading) return null
  if (!user) {
    return (
      <Link
        to={`/login?next=${encodeURIComponent(window.location.href)}`}
        className="text-sm es-link font-medium"
      >
        Log in
      </Link>
    )
  }
  return (
    <Link to={`/player/${user.user_id}`} className="text-sm es-muted hover:text-[color:var(--es-ink)] truncate max-w-[10rem]" title="Your Sorcerers Summit profile">
      {user.username}
    </Link>
  )
}

export default function ExplorerSiteLayout({ children }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  const shopOpen = useExplorerShopOpen()
  const [menuOpen, setMenuOpen] = useState(false)
  const isAdmin = !!(user && (user.is_explorer_admin || user.is_admin))
  // Opening the site clears the Summit menu's new-content dot for it
  useNewContent(user, location.pathname)

  useEffect(() => { setMenuOpen(false) }, [location.pathname])

  const links = [
    { to: ES_PATHS.home, label: 'Home', end: true },
    { to: ES_PATHS.standings, label: 'Standings' },
    { to: ES_PATHS.events, label: 'Events' },
    { to: ES_PATHS.host, label: 'Host an event' },
    ...(shopOpen ? [{ to: ES_PATHS.shop, label: 'Shop' }] : []),
  ]

  return (
    <div className="es-theme min-h-screen flex flex-col">
      {/* Thin strip back to the main site */}
      <div className="text-xs es-muted border-b es-rule bg-[color:var(--es-paper-deep)]/70">
        <div className="max-w-content mx-auto px-4 py-1.5 flex items-center justify-between gap-3">
          <span>Part of <span className="font-semibold text-[color:var(--es-ink)]">Sorcerers Summit</span></span>
          <Link to="/" className="hover:text-[color:var(--es-ink)]">← Back to Sorcerers Summit</Link>
        </div>
      </div>

      <header className="border-b-2 border-[color:var(--es-rule)] bg-[color:var(--es-card)]/80 backdrop-blur-sm sticky top-0 z-40">
        <div className="max-w-content mx-auto px-4 py-2.5 flex items-center gap-6">
          <Link to={ES_PATHS.home} className="flex items-center gap-2.5 shrink-0" aria-label="Explorer Series home">
            <img src={ES_COMPASS} alt="" width="40" height="39" className="w-10 h-auto" />
            <span className="es-heading text-2xl font-bold leading-none">Explorer Series</span>
          </Link>

          <nav className="hidden md:flex items-center gap-5 text-[15px]" aria-label="Explorer Series">
            {links.map((l) => (
              <NavLink key={l.to} to={l.to} end={l.end} className={navClass}>{l.label}</NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            <div className="hidden md:flex items-center gap-3">
              {isAdmin && <AdminMenu />}
              <AccountLink user={user} loading={loading} />
            </div>
            <button
              type="button"
              className="md:hidden text-2xl leading-none px-1"
              aria-label={menuOpen ? 'Close menu' : 'Open menu'}
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((o) => !o)}
            >
              {menuOpen ? '✕' : '☰'}
            </button>
          </div>
        </div>

        {menuOpen && (
          <nav className="md:hidden border-t es-rule bg-[color:var(--es-card)]" aria-label="Explorer Series menu">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                end={l.end}
                className={({ isActive }) => `block px-4 py-3 border-b es-rule ${isActive ? 'font-semibold text-[color:var(--es-rust)]' : ''}`}
              >
                {l.label}
              </NavLink>
            ))}
            {isAdmin && (
              <>
                <p className="px-4 pt-3 pb-1 es-kicker">Admin</p>
                {ADMIN_LINKS.map((l) => (
                  <Link key={l.to} to={l.to} className="block px-4 py-2.5">{l.label}</Link>
                ))}
                <div className="border-b es-rule" />
              </>
            )}
            <div className="px-4 py-3">
              <AccountLink user={user} loading={loading} />
            </div>
          </nav>
        )}
      </header>

      <main className="flex-1 max-w-content mx-auto w-full px-4 py-6">
        {children}
      </main>

      <footer className="border-t-2 border-[color:var(--es-rule)] bg-[color:var(--es-paper-deep)]/60 mt-auto">
        <div className="max-w-content mx-auto px-4 py-6 flex flex-col sm:flex-row gap-3 sm:items-center sm:justify-between text-sm es-muted">
          <div className="flex items-center gap-2">
            <img src={ES_COMPASS} alt="" width="24" height="23" className="w-6 h-auto opacity-80" />
            <span>The Sorcery Explorer Series, a player-run annual circuit.</span>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            <Link to={ES_PATHS.standings} className="hover:text-[color:var(--es-ink)]">Standings</Link>
            <Link to={ES_PATHS.host} className="hover:text-[color:var(--es-ink)]">Host an event</Link>
            <Link to="/" className="hover:text-[color:var(--es-ink)]">Hosted on Sorcerers Summit</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}
