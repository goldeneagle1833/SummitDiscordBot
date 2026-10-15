import { Link } from 'react-router-dom'
import usePageTitle from '@/hooks/usePageTitle'

// One menu link for the admin tools that used to be listed one by one in the
// hamburger menu. Every tool keeps its own page and address.
const SECTIONS = [
  {
    heading: 'Site',
    tools: [
      { to: '/admin/audit-log', label: 'Admin Log', blurb: 'Who changed what, and when.' },
      { to: '/admin/monitoring', label: 'Monitoring', blurb: 'Site health and traffic.' },
      { to: '/admin/users', label: 'Users', blurb: 'Look up players and set roles.' },
    ],
  },
  {
    heading: 'Events and content',
    tools: [
      { to: '/admin/brackets', label: 'Manage Top Cut', blurb: 'Create and run the season top cut bracket.' },
      { to: '/admin/meta-reports', label: 'Meta Reports', blurb: 'Build and publish reports.' },
    ],
  },
]

export default function AdminHub() {
  usePageTitle('Admin')

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-display text-secondary">Admin</h1>
        <p className="text-sm text-text-muted mt-1">Every admin tool in one place.</p>
      </div>
      {SECTIONS.map(({ heading, tools }) => (
        <section key={heading}>
          <h2 className="text-xs font-bold text-text-muted uppercase tracking-wider mb-2">{heading}</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {tools.map(({ to, label, blurb }) => (
              <Link
                key={to}
                to={to}
                className="block bg-bg-surface border border-border rounded-soft p-4 hover:border-accent-red/60 transition-colors"
              >
                <span className="block font-semibold text-text-primary">{label}</span>
                <span className="block text-sm text-text-muted mt-0.5">{blurb}</span>
              </Link>
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
