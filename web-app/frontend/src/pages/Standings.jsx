import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getStandingsHub } from '@/api/standings'
import { useAuth } from '@/context/AuthContext'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

/**
 * `/standings`: one page for every automatically run ladder, bracket and
 * series (season ladder + top cut, Underdog, Limited, precon ladder, site
 * brackets, Community Series), and, logged in, where you stand in each.
 */

const GROUPS = ['Ladders', 'Brackets & Series']

const STATUS = {
  live: { label: 'Live', cls: 'bg-accent-green/15 text-accent-green border-accent-green/40' },
  coming_soon: { label: 'Coming soon', cls: 'bg-secondary/10 text-secondary border-secondary/40' },
  between_seasons: { label: 'Between seasons', cls: 'bg-bg-elevated text-text-muted border-border' },
  finished: { label: 'Finished', cls: 'bg-bg-elevated text-text-muted border-border' },
  none: { label: 'Nothing running', cls: 'bg-bg-elevated text-text-muted border-border' },
}

const YOU_TONE = {
  in: 'border-l-accent-green',
  ranked: 'border-l-secondary',
  out: 'border-l-amber-500',
  no_ticket: 'border-l-amber-500',
  none: 'border-l-border',
  unknown: 'border-l-border',
}

const FORMAT_LABEL = { constructed: 'Constructed', limited: 'Limited', underdog: 'Underdog' }

function daysLeft(value) {
  if (!value) return null
  const end = new Date(value)
  if (Number.isNaN(end.getTime())) return null
  const days = Math.ceil((end.getTime() - Date.now()) / 86400000)
  if (days < 0) return null
  if (days === 0) return 'Ends today'
  return `${days} day${days === 1 ? '' : 's'} left`
}

function StatusPill({ status }) {
  const s = STATUS[status] || STATUS.none
  return <span className={`text-[11px] uppercase tracking-wide border rounded-full px-2 py-0.5 ${s.cls}`}>{s.label}</span>
}

function YouBox({ you }) {
  if (!you) return null
  return (
    <div className={`border-l-4 ${YOU_TONE[you.state] || 'border-l-border'} bg-bg-elevated rounded-r px-3 py-2 text-sm`}>
      <div className="text-[11px] uppercase tracking-wide text-text-muted">You</div>
      <div className="font-semibold text-text-primary">{you.headline}</div>
      {you.detail && <div className="text-text-muted">{you.detail}</div>}
      {(you.notes || []).map((n) => (
        <div key={n} className="text-text-muted text-xs mt-0.5">{n}</div>
      ))}
      {you.brackets?.length > 0 && (
        <ul className="mt-1 space-y-0.5">
          {you.brackets.map((b) => (
            <li key={b.slug}>
              <Link to={`/brackets/${b.slug}`} className="text-secondary hover:underline">{b.name}</Link>
              <span className="text-text-muted"> · seed {b.seed} · {b.label}</span>
            </li>
          ))}
        </ul>
      )}
      {you.action && (
        <Link to={you.action.to} className="inline-block mt-1 text-secondary hover:underline text-xs">
          {you.action.label} →
        </Link>
      )}
    </div>
  )
}

function BracketRows({ rows, finished }) {
  if (!rows?.length) return null
  return (
    <ul className="divide-y divide-border border border-border rounded">
      {rows.map((b) => (
        <li key={b.slug} className="px-3 py-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
          <Link to={`/brackets/${b.slug}`} className="text-secondary hover:underline font-medium">{b.name}</Link>
          <span className="text-[11px] border border-border rounded px-1.5 text-text-muted">
            {b.community ? 'Community' : FORMAT_LABEL[b.format] || b.format}
          </span>
          <span className="text-text-muted text-xs ml-auto">
            {finished
              ? b.champion ? `Champion: ${b.champion}` : 'Finished'
              : `${b.entrants} players · ${b.open_matches} match${b.open_matches === 1 ? '' : 'es'} to play`}
          </span>
        </li>
      ))}
    </ul>
  )
}

function SystemCard({ system, loggedIn }) {
  const left = system.status === 'live' ? daysLeft(system.ends_at) : null
  const title = system.link ? (
    <Link to={system.link} className="hover:underline">{system.title}</Link>
  ) : system.title
  return (
    <section className="w-full bg-bg-surface border border-border rounded-lg p-4 flex flex-col gap-3 min-w-0">
      <header className="flex flex-wrap items-center gap-2">
        <h3 className="text-lg font-display text-text-primary mr-auto">{title}</h3>
        {left && <span className="text-xs text-text-muted">{left}</span>}
        <StatusPill status={system.status} />
      </header>
      <p className="text-sm text-text-muted">{system.blurb}</p>

      {system.facts?.length > 0 && (
        <dl className="grid grid-cols-3 gap-2">
          {system.facts.map((f) => (
            <div key={f.label} className="bg-bg-elevated rounded px-2 py-1.5 min-w-0">
              <dt className="text-[11px] text-text-muted truncate">{f.label}</dt>
              <dd className="text-text-primary font-semibold">{f.value}</dd>
            </div>
          ))}
        </dl>
      )}

      {system.top?.length > 0 && (
        <ol className="text-sm space-y-0.5">
          {system.top.map((t) => (
            <li key={`${t.rank}-${t.name}`} className="flex gap-2">
              <span className="w-6 text-text-muted text-right">{t.rank}.</span>
              <span className="truncate text-text-primary">{t.name}</span>
              <span className="ml-auto text-text-muted whitespace-nowrap">
                {t.value}{t.unit ? ` ${t.unit}` : ''}
              </span>
            </li>
          ))}
        </ol>
      )}

      {system.key === 'brackets' && (
        <>
          {system.live?.length > 0 ? (
            <BracketRows rows={system.live} />
          ) : (
            <p className="text-sm text-text-muted">No bracket is being played right now.</p>
          )}
          {system.recent?.length > 0 && (
            <div>
              <div className="text-[11px] uppercase tracking-wide text-text-muted mb-1">Recently finished</div>
              <BracketRows rows={system.recent} finished />
            </div>
          )}
        </>
      )}

      {loggedIn && system.status !== 'coming_soon' && <YouBox you={system.you} />}

      {(system.link || system.links?.length > 0) && (
        <footer className="flex flex-wrap gap-x-4 gap-y-1 text-sm mt-auto pt-1">
          {system.link && (
            <Link to={system.link} className="text-secondary hover:underline">Full standings →</Link>
          )}
          {(system.links || []).map((l) => (
            <Link key={l.to} to={l.to} className="text-secondary hover:underline">{l.label} →</Link>
          ))}
        </footer>
      )}
    </section>
  )
}

function Snapshot({ systems }) {
  const rows = systems.filter((s) => s.you && s.status !== 'coming_soon')
  const todo = systems.flatMap((s) => s.you?.todo || [])
  if (!rows.length && !todo.length) return null
  return (
    <div className="space-y-3">
      {todo.length > 0 && (
        <div className="bg-secondary/10 border-l-2 border-secondary px-4 py-3 rounded-r">
          <h2 className="text-sm font-semibold mb-1">Waiting on you</h2>
          <ul className="space-y-1 text-sm">
            {todo.map((m) => (
              <li key={`${m.slug}-${m.round_title}-${m.opponent}`}>
                <Link to={`/brackets/${m.slug}`} className="text-secondary hover:underline">
                  {m.bracket_name}{m.round_title ? ` · ${m.round_title}` : ''}
                </Link>
                <span className="text-text-muted">
                  {m.opponent ? ` vs ${m.opponent}` : ''} ({m.needs === 'report' ? 'play and report' : 'confirm the result'})
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="grid gap-2 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
        {rows.map((s) => (
          <a
            key={s.key}
            href={`#${s.key}`}
            className={`block border-l-4 ${YOU_TONE[s.you.state] || 'border-l-border'} bg-bg-surface border border-border rounded px-3 py-2 hover:bg-bg-elevated`}
          >
            <div className="text-[11px] uppercase tracking-wide text-text-muted truncate">{s.title}</div>
            <div className="text-sm font-semibold text-text-primary">{s.you.headline}</div>
          </a>
        ))}
      </div>
    </div>
  )
}

const MORE = [
  { to: '/elo', label: 'ELO Leaderboards' },
  { to: '/brackets', label: 'Season Top Cut' },
  { to: '/top-8', label: 'Top 8 Decks' },
  { to: '/explorer', label: 'Community Series' },
  { to: '/summit-format', label: 'Summit Format' },
]

export default function Standings() {
  usePageTitle('Event Standings')
  const { user } = useAuth()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    getStandingsHub()
      .then((res) => setData(res))
      .catch(() => setError('Could not load standings.'))
  }, [user])

  if (error) return <p className="text-center text-accent-red py-12">{error}</p>
  if (!data) return <Spinner />

  const systems = data.systems || []
  const loggedIn = Boolean(data.logged_in)

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
      <div>
        <h1 className="text-2xl font-display text-text-primary">Event Standings</h1>
        <p className="text-text-muted text-sm mt-1">
          Every ladder, bracket and series the Summit runs, in one place
          {loggedIn ? ', and where you stand in each.' : '.'}
        </p>
      </div>

      {loggedIn ? (
        <Snapshot systems={systems} />
      ) : (
        <div className="bg-bg-surface border border-border rounded px-4 py-3 text-sm text-text-muted">
          <Link to="/login" className="text-secondary hover:underline">Log in with Discord</Link>{' '}
          to see where you stand in each one.
        </div>
      )}

      {GROUPS.map((group) => {
        const inGroup = systems.filter((s) => s.group === group)
        if (!inGroup.length) return null
        return (
          <div key={group} className="space-y-3">
            <h2 className="text-sm uppercase tracking-wider text-secondary">{group}</h2>
            <div className="grid gap-4 grid-cols-1 lg:grid-cols-2">
              {inGroup.map((s) => (
                <div key={s.key} id={s.key} className="scroll-mt-20 flex">
                  <SystemCard system={s} loggedIn={loggedIn} />
                </div>
              ))}
            </div>
          </div>
        )
      })}

      <div className="border-t border-border pt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm">
        <span className="text-text-muted">More:</span>
        {MORE.map((m) => (
          <Link key={m.to} to={m.to} className="text-secondary hover:underline">{m.label}</Link>
        ))}
      </div>
    </div>
  )
}
