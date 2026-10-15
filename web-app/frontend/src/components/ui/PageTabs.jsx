import { Link, useLocation } from 'react-router-dom'

// Pill toggle that switches between sibling pages (each tab is its own route,
// so old links keep working and open the matching tab).
export default function PageTabs({ tabs, label, className = '' }) {
  const { pathname } = useLocation()
  return (
    <nav aria-label={label} className={`flex justify-center ${className}`}>
      <div className="inline-flex gap-1 bg-bg-surface border border-border rounded-full p-1">
        {tabs.map(({ to, label: tabLabel }) => {
          const active = pathname === to
          return (
            <Link
              key={to}
              to={to}
              aria-current={active ? 'page' : undefined}
              className={`px-4 py-1.5 rounded-full text-sm font-semibold transition-colors ${
                active ? 'bg-bg-elevated text-secondary' : 'text-text-muted hover:text-text'
              }`}
            >
              {tabLabel}
            </Link>
          )
        })}
      </div>
    </nav>
  )
}
