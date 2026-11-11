import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import usePageTitle from '@/hooks/usePageTitle'
import { useAuth } from '@/context/AuthContext'
import { fetchSeasons } from '@/api/explorer'
import { ES_PATHS } from '@/utils/explorerSite'
import AddSeasonModal from '@/components/explorer/AddSeasonModal'
import AddEventModal from '@/components/explorer/AddEventModal'
import EventsMapToggle from '@/components/explorer/EventsMapToggle'
import PlayerMergePanel from '@/components/explorer/PlayerMergePanel'
import VenueAttendancePanel from '@/components/explorer/VenueAttendancePanel'
import ExplorerAdminPanel from '@/components/explorer/ExplorerAdminPanel'

function Tile({ to, title, text }) {
  return (
    <Link to={to} className="es-card p-4 block hover:!border-[color:var(--es-rust)] transition-colors">
      <span className="es-heading text-lg font-bold block">{title} →</span>
      <span className="text-sm es-muted">{text}</span>
    </Link>
  )
}

function Panel({ title, text, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <section className="es-card">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full text-left px-4 sm:px-5 py-3.5 flex items-center justify-between gap-3"
      >
        <span>
          <span className="es-heading text-lg font-bold block">{title}</span>
          {text && <span className="text-sm es-muted">{text}</span>}
        </span>
        <span aria-hidden="true" className="es-muted">{open ? '▴' : '▾'}</span>
      </button>
      {open && <div className="px-4 sm:px-5 pb-5 border-t es-rule pt-4">{children}</div>}
    </section>
  )
}

/** One place for every Explorer admin tool. */
export default function ExplorerAdminHome() {
  usePageTitle('Explorer Series admin')
  const { user } = useAuth()
  const [seasons, setSeasons] = useState([])
  const [modal, setModal] = useState(null) // 'season' | 'event'
  const [notice, setNotice] = useState(null)

  const loadSeasons = () => fetchSeasons().then((d) => setSeasons(d || [])).catch(() => {})
  useEffect(() => { loadSeasons() }, [])

  return (
    <div className="space-y-5">
      <div>
        <p className="es-kicker">Explorer admins</p>
        <h1 className="es-heading text-3xl sm:text-4xl font-bold mt-1">Admin</h1>
        <p className="es-muted text-sm mt-1">Everything you need to run the Series site.</p>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <Tile to={ES_PATHS.content} title="Edit site content" text="Home page text, announcement, Discord and member links, extra sections." />
        <Tile to={ES_PATHS.applications} title="Review Explorer Series Applications" text="Review, vote on and publish applications to host." />
        <Tile to={ES_PATHS.calendar} title="Events calendar" text="Proposed dates and clashes between applications." />
        <Tile to={ES_PATHS.standings} title="Standings" text="The public leaderboard, with export and per-player results." />
      </div>

      <section className="es-card p-4 sm:p-5">
        <h2 className="es-heading text-lg font-bold">Series and events</h2>
        <p className="text-sm es-muted mb-3">Start a new series, or import an event's results from its sorcerytcg.com page.</p>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="es-btn-ghost" onClick={() => setModal('season')}>+ Add series</button>
          <button type="button" className="es-btn" disabled={!seasons.length} onClick={() => setModal('event')}>+ Import event</button>
        </div>
        {notice && <p className="text-sm text-accent-green mt-3" role="status">{notice}</p>}
      </section>

      <section className="es-card p-4 sm:p-5">
        <EventsMapToggle />
      </section>

      <Panel title="Merge duplicate players" text="Combine one player's results that came in under two names.">
        <PlayerMergePanel />
      </Panel>

      <Panel title="Venue attendance lookup" text="Paste a sorcerytcg.com store link to see its event attendance.">
        <VenueAttendancePanel />
      </Panel>

      {user?.is_admin && (
        <Panel title="Explorer admins" text="Who can use these tools. Site admins only.">
          <ExplorerAdminPanel />
        </Panel>
      )}

      {modal === 'season' && (
        <AddSeasonModal
          onClose={() => setModal(null)}
          onCreated={(season) => { setModal(null); loadSeasons(); setNotice(`Series "${season?.name || ''}" created.`) }}
        />
      )}
      {modal === 'event' && (
        <AddEventModal
          seasons={seasons}
          onClose={() => setModal(null)}
          onSaved={() => { setModal(null); loadSeasons(); setNotice('Event imported. The standings now include it.') }}
        />
      )}
    </div>
  )
}
