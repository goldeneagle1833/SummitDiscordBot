import { useMemo, useState } from 'react'
import AvatarArtCard, { useAvatarArt } from './AvatarArtCard'
import { getWinRateColor } from '@/utils/winRateColor'

const SORTS = {
  games: { label: 'Most played', fn: (a, b) => b.wins + b.losses - (a.wins + a.losses) },
  win_rate: { label: 'Win rate', fn: (a, b) => b.win_rate - a.win_rate || b.wins - a.wins },
  recent: { label: 'Recently played', fn: (a, b) => String(b.last_played || '').localeCompare(String(a.last_played || '')) },
}

function shortDate(value) {
  if (!value) return null
  const d = new Date(String(value).replace(' ', 'T'))
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function Form({ results = [] }) {
  if (!results.length) return null
  return (
    <div className="flex items-center gap-1" aria-label={`Last ${results.length} games, newest first: ${results.join(' ')}`}>
      {results.map((r, i) => (
        <span
          key={i}
          aria-hidden="true"
          className={`w-5 h-5 rounded text-[10px] font-bold flex items-center justify-center ${
            r === 'W' ? 'bg-secondary text-black' : 'bg-white/15 text-text-muted'
          }`}
        >
          {r}
        </span>
      ))}
    </div>
  )
}

function Highlight({ label, avatar, detail }) {
  return (
    <div className="bg-bg-surface border border-border rounded-xl px-4 py-3.5 min-w-0">
      <div className="text-xs text-text-muted">{label}</div>
      <div className="text-lg font-bold text-text-primary truncate mt-0.5">{avatar ?? '-'}</div>
      {detail && <div className="text-xs text-text-muted mt-0.5">{detail}</div>}
    </div>
  )
}

/**
 * The Avatars tab: one art card per avatar the player has been on, showing how
 * it is doing for them next to how it does for everyone.
 */
export default function AvatarPerformance({ avatars, playerId }) {
  const { imageFiles, community } = useAvatarArt()
  const [sort, setSort] = useState('games')
  const sorted = useMemo(() => [...(avatars || [])].sort(SORTS[sort].fn), [avatars, sort])

  if (!avatars?.length) return null

  const games = (a) => a.wins + a.losses
  const mostPlayed = [...avatars].sort(SORTS.games.fn)[0]
  const qualified = avatars.filter((a) => games(a) >= 5)
  const best = [...qualified].sort(SORTS.win_rate.fn)[0]
  const recent = [...avatars].sort(SORTS.recent.fn)[0]

  return (
    <div className="space-y-6">
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
        <Highlight label="Avatars played" avatar={avatars.length} />
        <Highlight label="Most played" avatar={mostPlayed?.name} detail={mostPlayed && `${games(mostPlayed)} games`} />
        <Highlight label="Best win rate (5+ games)" avatar={best?.name} detail={best && `${best.win_rate}% · ${best.wins}-${best.losses}`} />
        <Highlight label="Last played" avatar={recent?.last_played ? recent.name : null} detail={shortDate(recent?.last_played)} />
      </div>

      <div className="flex items-center justify-end gap-2">
        <label htmlFor="avatar-sort" className="text-sm text-text-muted">Sort by</label>
        <select
          id="avatar-sort"
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          className="h-11 rounded-lg border border-border bg-bg-raised px-3 text-sm"
        >
          {Object.entries(SORTS).map(([key, s]) => <option key={key} value={key}>{s.label}</option>)}
        </select>
      </div>

      <ul className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
        {sorted.map((av) => {
          const total = games(av)
          const everyone = community[av.name]
          const diff = everyone?.win_rate != null && total > 0 ? Math.round((av.win_rate - everyone.win_rate) * 10) / 10 : null
          return (
            <li key={av.name}>
              <AvatarArtCard
                name={av.name}
                imageFiles={imageFiles}
                to={`/player/${playerId}/avatar/${encodeURIComponent(av.name)}`}
                className="min-h-[240px]"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className="text-xl font-bold text-white leading-tight">{av.name}</h3>
                    <div className="text-sm text-gray-300 mt-1">
                      {total} {total === 1 ? 'game' : 'games'}
                      {shortDate(av.last_played) && ` · last ${shortDate(av.last_played)}`}
                    </div>
                  </div>
                  {av.event_elo != null && (
                    <div className="text-right shrink-0">
                      <div className="text-lg font-bold text-secondary tabular-nums">{av.event_elo}</div>
                      <div className="text-xs text-gray-300">{av.event_rank ? `#${av.event_rank}` : 'Event ELO'}</div>
                    </div>
                  )}
                </div>

                <div className="mt-auto pt-6 space-y-3">
                  <div className="flex items-end justify-between gap-3">
                    <div>
                      <div className="text-4xl font-extrabold tabular-nums leading-none" style={{ color: getWinRateColor(av.win_rate) }}>
                        {av.win_rate}%
                      </div>
                      <div className="text-sm text-gray-200 mt-1 tabular-nums">{av.wins}W · {av.losses}L</div>
                    </div>
                    <div className="text-right text-sm">
                      {diff != null && (
                        <div className="text-gray-300">
                          Everyone {everyone.win_rate}%{' '}
                          <span className={diff > 0 ? 'text-secondary font-semibold' : ''}>
                            ({diff > 0 ? '+' : ''}{diff})
                          </span>
                        </div>
                      )}
                      {av.elo_change ? (
                        <div className="text-gray-300 tabular-nums">
                          {av.elo_change > 0 ? '+' : ''}{av.elo_change} ELO
                        </div>
                      ) : null}
                    </div>
                  </div>
                  <Form results={av.form} />
                </div>
              </AvatarArtCard>
            </li>
          )
        })}
      </ul>
      <p className="text-xs text-text-muted">
        &ldquo;Everyone&rdquo; is the win rate of every reported game on that avatar, and the number in brackets is how far you are above or below it. The squares are your last 10 games, newest first.
      </p>
    </div>
  )
}
