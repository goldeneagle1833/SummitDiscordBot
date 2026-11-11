import { lazy, Suspense } from 'react'
import { Link } from 'react-router-dom'
import usePageTitle from '@/hooks/usePageTitle'
import Spinner from '@/components/ui/Spinner'
import { ES_PATHS, ES_LOGO } from '@/utils/explorerSite'
import useExplorerSeason, { formatEventDate } from './useExplorerSeason'
import useSiteContent from './useSiteContent'
import SiteText from '@/components/explorer/SiteText'
import { useAuth } from '@/context/AuthContext'

const EventsMap = lazy(() => import('@/components/explorer/EventsMap'))

function SectionHead({ title, to, linkLabel }) {
  return (
    <div className="flex items-baseline justify-between gap-3 mb-3">
      <h2 className="es-heading text-xl font-bold">{title}</h2>
      {to && <Link to={to} className="es-link text-sm whitespace-nowrap">{linkLabel} →</Link>}
    </div>
  )
}

function DateChip({ value }) {
  const d = formatEventDate(value)
  return (
    <div className="w-12 shrink-0 text-center rounded-md border border-[color:var(--es-rule)] bg-[color:var(--es-card-2)] py-1 leading-tight">
      <span className="block text-[10px] tracking-wider es-muted">{d?.month || '—'}</span>
      <span className="block text-lg font-semibold">{d?.day || ''}</span>
    </div>
  )
}

function Stat({ value, label }) {
  return (
    <div className="rounded-lg border border-[color:var(--es-rule-soft)] bg-[color:var(--es-card-2)] px-3 py-2.5">
      <span className="block text-2xl font-semibold">{value ?? '—'}</span>
      <span className="block text-xs es-muted leading-snug">{label}</span>
    </div>
  )
}

function PointsGuide({ config }) {
  if (!config) return null
  const bonus = config.bonus_pathfinder || {}
  const persecutor = Object.entries(config.persecutor || {})
    .map(([place, pts]) => [Number(place), pts])
    .sort((a, b) => a[0] - b[0])
  // Collapse equal neighbours: 3rd-4th 4 pts, 5th-6th 3 pts ...
  const placeRows = []
  for (const [place, pts] of persecutor) {
    const last = placeRows[placeRows.length - 1]
    if (last && last.pts === pts && last.to === place - 1) last.to = place
    else placeRows.push({ from: place, to: place, pts })
  }
  const ordinal = (n) => `${n}${['th', 'st', 'nd', 'rd'][(n % 100 > 10 && n % 100 < 14) ? 0 : (n % 10 < 4 ? n % 10 : 0)]}`

  return (
    <div className="grid sm:grid-cols-2 gap-4">
      <div className="rounded-lg border border-[color:var(--es-rule-soft)] bg-[color:var(--es-card-2)] p-4">
        <h3 className="es-heading text-lg font-bold">Pathfinder track</h3>
        <p className="text-xs es-muted mb-2">Rewards showing up and travelling to play.</p>
        <table className="w-full text-sm">
          <tbody>
            <tr className="border-t es-rule"><td className="py-1.5">Complete any Series event</td><td className="py-1.5 text-right font-semibold">{config.participation} pts</td></tr>
            {['2', '1', '0'].filter((k) => bonus[k] != null).map((k) => (
              <tr key={k} className="border-t es-rule">
                <td className="py-1.5">Bonus: win exactly {k} match{k === '1' ? '' : 'es'}</td>
                <td className="py-1.5 text-right font-semibold">{bonus[k]} pts</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="rounded-lg border border-[color:var(--es-rule-soft)] bg-[color:var(--es-card-2)] p-4">
        <h3 className="es-heading text-lg font-bold">Persecutor track</h3>
        <p className="text-xs es-muted mb-2">Rewards finishing near the top of an event.</p>
        <table className="w-full text-sm">
          <tbody>
            {placeRows.map((r) => (
              <tr key={r.from} className="border-t es-rule">
                <td className="py-1.5">{r.from === r.to ? ordinal(r.from) : `${ordinal(r.from)} – ${ordinal(r.to)}`} in any event</td>
                <td className="py-1.5 text-right font-semibold">{r.pts} pts</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="sm:col-span-2 text-sm es-muted">
        Your <span className="font-semibold text-[color:var(--es-ink)]">Grand Explorer</span> score is Pathfinder plus Persecutor.
        {config.trials_threshold != null && <> Reach {config.trials_threshold} Persecutor points to qualify for the Trials of the Persecutor.</>}
      </p>
    </div>
  )
}

export default function ExplorerHome() {
  usePageTitle('Explorer Series')
  const { season, leaderboard, events, mapEvents, loading, error } = useExplorerSeason()
  const { content } = useSiteContent()
  const { user } = useAuth()
  const isAdmin = !!(user && (user.is_explorer_admin || user.is_admin))
  const sections = (content.sections || []).filter((s) => !s.hidden)

  const top = (leaderboard?.players || []).slice(0, 8)
  const recent = [...events].sort((a, b) => String(b.event_date || '').localeCompare(String(a.event_date || ''))).slice(0, 4)
  const venues = new Set(events.map((e) => (e.venue_name || '').trim()).filter(Boolean)).size

  return (
    <div className="space-y-6">
      {isAdmin && (
        <div className="flex justify-end -mb-2">
          <Link to={ES_PATHS.content} className="es-btn-ghost !py-1.5 !px-3 text-sm">✎ Edit this page</Link>
        </div>
      )}
      {content.announcement && (
        <div className="es-card px-4 py-3 border-l-4 !border-l-[color:var(--es-rust)]" role="status">
          <SiteText text={content.announcement} className="text-sm" />
        </div>
      )}
      {/* Hero */}
      <section className="grid md:grid-cols-[1.15fr_1fr] gap-6 items-center pt-2">
        <div>
          <p className="es-kicker">{content.kicker || season?.name || 'The Sorcery Explorer Series'}</p>
          <h1 className="es-heading text-4xl sm:text-5xl font-bold mt-2 mb-3">{content.title || 'The Explorer Series'}</h1>
          <SiteText text={content.intro} className="text-base sm:text-lg es-muted max-w-xl" />
          <div className="flex flex-wrap gap-3 mt-5">
            <Link to={ES_PATHS.standings} className="es-btn">See the standings</Link>
            <Link to={ES_PATHS.host} className="es-btn-ghost">Host an event at your store</Link>
            {content.discord_url && (
              <a href={content.discord_url} target="_blank" rel="noopener noreferrer" className="es-btn-ghost">Join our Discord ↗</a>
            )}
            {content.member_url && (
              <a href={content.member_url} target="_blank" rel="noopener noreferrer" className="es-btn-ghost">Become a member ↗</a>
            )}
          </div>
        </div>
        <img
          src={ES_LOGO}
          alt="Explorer Series compass rose logo"
          width="1000"
          height="733"
          className="w-full max-w-md mx-auto md:ml-auto drop-shadow-[0_6px_14px_rgba(59,38,20,0.25)]"
        />
      </section>

      {error && <p className="text-sm text-red-400">{error}</p>}
      {loading ? <Spinner className="py-12" /> : (
        <>
          <div className="grid lg:grid-cols-[1.35fr_1fr] gap-5">
            <section className="es-card p-4 sm:p-5">
              <SectionHead title="Season standings" to={ES_PATHS.standings} linkLabel="Full standings" />
              {top.length === 0 ? (
                <p className="text-sm es-muted">No results yet this season.</p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-left">
                      <th className="py-1.5 w-8 font-medium">#</th>
                      <th className="py-1.5 font-medium">Explorer</th>
                      <th className="py-1.5 font-medium text-right hidden sm:table-cell">Events</th>
                      <th className="py-1.5 font-medium text-right">Grand Explorer</th>
                    </tr>
                  </thead>
                  <tbody>
                    {top.map((p, i) => (
                      <tr key={p.cardeio_user_id || i} className="border-t es-rule">
                        <td className="py-2 es-muted">{p.rank ?? i + 1}</td>
                        <td className="py-2 font-medium">{p.display_name}</td>
                        <td className="py-2 text-right es-muted hidden sm:table-cell">{p.events_played}</td>
                        <td className="py-2 text-right font-semibold text-[color:var(--es-rust)]">{p.grand_explorer}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>

            <div className="space-y-5">
              <section className="es-card p-4 sm:p-5">
                <SectionHead title="This season" />
                <div className="grid grid-cols-3 gap-2.5">
                  <Stat value={events.length} label="events played" />
                  <Stat value={leaderboard?.unique_players_1_event} label="Explorers" />
                  <Stat value={venues || '—'} label="stores" />
                </div>
                {leaderboard?.unique_players_3_events != null && (
                  <p className="text-xs es-muted mt-3">
                    {leaderboard.unique_players_3_events} Explorers have played 3 or more events.
                  </p>
                )}
              </section>

              <section className="es-card p-4 sm:p-5">
                <SectionHead title="Recent events" to={ES_PATHS.events} linkLabel="All events" />
                {recent.length === 0 ? (
                  <p className="text-sm es-muted">No events yet.</p>
                ) : (
                  <ul>
                    {recent.map((e) => (
                      <li key={e.id} className="flex gap-3 py-2 border-t es-rule first:border-t-0">
                        <DateChip value={e.event_date} />
                        <div className="min-w-0">
                          <p className="text-sm font-medium truncate">{e.venue_name || e.event_name}</p>
                          <p className="text-xs es-muted truncate">
                            {e.venue_name ? e.event_name : ''}{e.total_players ? `${e.venue_name ? ' · ' : ''}${e.total_players} players` : ''}
                          </p>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>
          </div>

          {mapEvents.length > 0 && (
            <section className="es-card p-4 sm:p-5">
              <SectionHead title="Where the Series has played" to={ES_PATHS.events} linkLabel="Events" />
              <Suspense fallback={<div className="h-96 rounded-lg border border-[color:var(--es-rule)]" />}>
                <EventsMap events={mapEvents} />
              </Suspense>
            </section>
          )}

          {sections.map((sec, i) => (
            <section key={i} className="es-card p-4 sm:p-6">
              {sec.title && <h2 className="es-heading text-2xl font-bold mb-3">{sec.title}</h2>}
              <SiteText text={sec.body} />
            </section>
          ))}

          {content.show_points_guide !== false && leaderboard?.points_config && (
            <section className="es-card p-4 sm:p-5">
              <SectionHead title="How Series points work" />
              <PointsGuide config={leaderboard.points_config} />
            </section>
          )}

          <section className="es-card p-5 sm:p-6 text-center">
            <h2 className="es-heading text-2xl font-bold">{content.host_title || 'Bring the Series to your store'}</h2>
            <SiteText text={content.host_text} className="es-muted mt-1 mb-4 max-w-xl mx-auto" />
            <Link to={ES_PATHS.host} className="es-btn">Apply to host an event</Link>
          </section>
        </>
      )}
    </div>
  )
}
