import { lazy, Suspense } from 'react'
import usePageTitle from '@/hooks/usePageTitle'
import Spinner from '@/components/ui/Spinner'
import useExplorerSeason, { formatEventDate } from './useExplorerSeason'

const EventsMap = lazy(() => import('@/components/explorer/EventsMap'))

function monthKey(value) {
  const d = formatEventDate(value)
  if (!d || !d.month) return 'Date to be confirmed'
  return new Date(`${String(value).slice(0, 10)}T12:00:00`).toLocaleString('en-US', { month: 'long', year: 'numeric' })
}

/** Every event in a series, month by month, with the map when it's switched on. */
export default function ExplorerEvents() {
  usePageTitle('Explorer Series events')
  const { seasons, activeId, setActiveId, events, mapEvents, loading, error } = useExplorerSeason()

  const groups = []
  for (const e of [...events].sort((a, b) => String(a.event_date || '9').localeCompare(String(b.event_date || '9')))) {
    const key = monthKey(e.event_date)
    const last = groups[groups.length - 1]
    if (last && last.key === key) last.events.push(e)
    else groups.push({ key, events: [e] })
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="es-kicker">Series events</p>
          <h1 className="es-heading text-3xl sm:text-4xl font-bold mt-1">Events</h1>
        </div>
        {seasons.length > 1 && (
          <label className="text-sm es-muted flex items-center gap-2">
            Series
            <select
              value={activeId ?? ''}
              onChange={(e) => setActiveId(Number(e.target.value))}
              className="border rounded px-3 py-1.5 text-sm"
            >
              {seasons.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </label>
        )}
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}
      {loading ? <Spinner className="py-12" /> : (
        <>
          {mapEvents.length > 0 && (
            <section className="es-card p-3 sm:p-4">
              <Suspense fallback={<div className="h-96 rounded-lg border border-[color:var(--es-rule)]" />}>
                <EventsMap events={mapEvents} />
              </Suspense>
            </section>
          )}

          {groups.length === 0 ? (
            <div className="es-card p-8 text-center es-muted">No events in this series yet.</div>
          ) : (
            <div className="space-y-4">
              {groups.map((g) => (
                <section key={g.key} className="es-card overflow-hidden">
                  <h2 className="es-heading text-xl font-bold px-4 sm:px-5 py-3 border-b es-rule bg-[color:var(--es-card-2)]">
                    {g.key}
                    <span className="ml-2 text-sm font-sans font-normal es-muted">{g.events.length} event{g.events.length === 1 ? '' : 's'}</span>
                  </h2>
                  <ul>
                    {g.events.map((e) => {
                      const d = formatEventDate(e.event_date)
                      return (
                        <li key={e.id} className="px-4 sm:px-5 py-3 border-t es-rule first:border-t-0 flex flex-wrap items-center gap-x-4 gap-y-1">
                          <span className="w-28 shrink-0 text-sm es-muted">{d?.full || 'Date TBC'}</span>
                          <div className="flex-1 min-w-[12rem]">
                            <p className="font-medium">{e.venue_name || e.event_name}</p>
                            {e.venue_name && <p className="text-xs es-muted">{e.event_name}</p>}
                          </div>
                          {e.total_players ? <span className="text-sm es-muted">{e.total_players} players</span> : null}
                          {e.source_url && (
                            <a href={e.source_url} target="_blank" rel="noopener noreferrer" className="text-sm es-link">
                              Results ↗
                            </a>
                          )}
                        </li>
                      )
                    })}
                  </ul>
                </section>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
