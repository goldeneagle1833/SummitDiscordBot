import { useEffect, useMemo, useState } from 'react'
import { getPlayerCardStats } from '@/api/players'
import Spinner from '@/components/ui/Spinner'

const MIN_GAMES_OPTIONS = [1, 3, 5, 10]

function Tile({ value, label }) {
  return (
    <div className="bg-bg-surface border border-border rounded-xl px-4 py-3.5 min-w-0">
      <div className="text-2xl font-extrabold text-text-primary truncate tabular-nums">{value}</div>
      <div className="text-xs text-text-muted mt-1">{label}</div>
    </div>
  )
}

function points(effect) {
  if (effect == null) return '-'
  return `${effect > 0 ? '+' : ''}${effect} pts`
}

function EffectBar({ effect }) {
  const width = effect == null ? 0 : Math.min(50, Math.abs(effect) * 2)
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex-1 flex h-2.5 rounded bg-bg-raised overflow-hidden" aria-hidden="true">
        <div className="flex-1 flex justify-end">
          {effect < 0 && <div className="h-full bg-text-muted/60" style={{ width: `${width * 2}%` }} />}
        </div>
        <div className="w-0.5 bg-border" />
        <div className="flex-1 flex">
          {effect > 0 && <div className="h-full bg-secondary" style={{ width: `${width * 2}%` }} />}
        </div>
      </div>
      <span className={`w-16 text-right font-bold tabular-nums ${effect > 0 ? 'text-secondary' : 'text-text-muted'}`}>
        {points(effect)}
      </span>
    </div>
  )
}

function CardList({ title, cards }) {
  return (
    <section className="bg-bg-surface border border-border rounded-xl p-5">
      <h2 className="text-xs font-bold uppercase tracking-wider text-text-muted mb-4">{title}</h2>
      {cards.length === 0 ? (
        <p className="text-sm text-text-muted">Not enough games yet.</p>
      ) : (
        <ul className="space-y-3">
          {cards.map((card) => (
            <li key={card.name} className="flex items-center gap-3">
              {card.image_url ? (
                <img src={card.image_url} alt="" className="w-10 h-14 rounded object-cover shrink-0" loading="lazy" />
              ) : (
                <div className="w-10 h-14 rounded bg-bg-raised border border-border shrink-0" aria-hidden="true" />
              )}
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-text-primary truncate">{card.name}</div>
                <div className="text-xs text-text-muted tabular-nums">
                  Played in {card.games} games · {card.win_rate}% win rate
                </div>
              </div>
              <strong className={`tabular-nums ${card.effect > 0 ? 'text-secondary' : 'text-text-muted'}`}>
                {points(card.effect)}
              </strong>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

/**
 * The Card Stats tab: this player's own cards from Sorcery Online's
 * played-card data, and how they do when each card hits the table.
 */
export default function CardStats({ playerId, eventFilter, isOwner, isPublic }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [query, setQuery] = useState('')
  const [minGames, setMinGames] = useState(3)
  const [sort, setSort] = useState('games')

  useEffect(() => {
    let active = true
    setData(null)
    setError(null)
    getPlayerCardStats(playerId, { event: eventFilter })
      .then((d) => active && setData(d))
      .catch((err) => active && setError(err.message || 'Could not load card stats'))
    return () => {
      active = false
    }
  }, [playerId, eventFilter])

  const rows = useMemo(() => {
    if (!data) return []
    const q = query.trim().toLowerCase()
    const list = data.cards.filter((c) => c.games >= minGames && (!q || c.name.toLowerCase().includes(q)))
    const key = { games: (c) => c.games, win_rate: (c) => c.win_rate, effect: (c) => c.effect ?? -999 }[sort]
    return [...list].sort((a, b) => key(b) - key(a) || a.name.localeCompare(b.name))
  }, [data, query, minGames, sort])

  if (error) return <p className="text-sm text-text-muted py-6">{error}</p>
  if (!data) return <Spinner className="py-12" />

  if (!data.games) {
    return (
      <p className="text-sm text-text-muted py-6">
        No Sorcery Online games with card data for this period yet. Cards show up here after games played through the PSO queue.
      </p>
    )
  }

  const rated = data.cards.filter((c) => c.games >= 5 && c.effect != null)
  const best = [...rated].filter((c) => c.effect > 0).sort((a, b) => b.effect - a.effect).slice(0, 5)
  const worst = [...rated].filter((c) => c.effect < 0).sort((a, b) => a.effect - b.effect).slice(0, 5)
  const mostPlayed = data.cards[0]

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-text-muted">
          From Sorcery Online games: <strong className="text-text-primary tabular-nums">{data.games}</strong> games with card data
          ({data.wins}-{data.losses}, {data.win_rate}%).
        </p>
        {isOwner && (
          <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-bg-raised border border-border text-xs text-text-muted">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" />
            </svg>
            {isPublic ? 'Public: anyone can see this tab' : 'Only you and admins can see this tab'}
          </span>
        )}
      </div>

      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
        <Tile value={data.unique_cards} label="Different cards played" />
        <Tile value={data.avg_cards_per_game} label="Cards played per game" />
        <Tile value={mostPlayed?.name ?? '-'} label={mostPlayed ? `Most played · ${mostPlayed.games} games` : 'Most played'} />
        <Tile value={best[0]?.name ?? '-'} label={best[0] ? `Biggest boost · ${points(best[0].effect)}` : 'Biggest boost'} />
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        <CardList title="Cards that win you games" cards={best} />
        <CardList title="Cards that let you down" cards={worst} />
      </div>

      <div className="flex flex-wrap gap-2.5 items-center">
        <label className="sr-only" htmlFor="card-stats-search">Search cards</label>
        <input
          id="card-stats-search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search cards"
          className="h-11 w-56 rounded-lg border border-border bg-bg-raised px-3 text-sm"
        />
        <label className="sr-only" htmlFor="card-stats-min">Minimum games</label>
        <select
          id="card-stats-min"
          value={minGames}
          onChange={(e) => setMinGames(Number(e.target.value))}
          className="h-11 rounded-lg border border-border bg-bg-raised px-3 text-sm"
        >
          {MIN_GAMES_OPTIONS.map((n) => <option key={n} value={n}>{n}+ games</option>)}
        </select>
        <label className="sr-only" htmlFor="card-stats-sort">Sort by</label>
        <select
          id="card-stats-sort"
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          className="h-11 rounded-lg border border-border bg-bg-raised px-3 text-sm"
        >
          <option value="games">Most played</option>
          <option value="win_rate">Win % when played</option>
          <option value="effect">Effect of playing it</option>
        </select>
        <span className="ml-auto text-xs text-text-muted">{rows.length} cards</span>
      </div>

      <section className="bg-bg-surface border border-border rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wider text-text-muted">
                <th className="py-3 px-5 font-bold">Card</th>
                <th className="py-3 px-2.5 font-bold">Games played</th>
                <th className="py-3 px-2.5 font-bold">Record</th>
                <th className="py-3 px-2.5 font-bold">Win % played</th>
                <th className="py-3 px-2.5 font-bold">Win % not played</th>
                <th className="py-3 px-5 font-bold w-[26%]">Effect of playing it</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((card) => (
                <tr key={card.name} className="border-t border-border/60">
                  <td className="py-3 px-5">
                    <div className="font-semibold text-text-primary">{card.name}</div>
                    {card.element && <div className="text-xs text-text-muted">{card.element}</div>}
                  </td>
                  <td className="py-3 px-2.5 tabular-nums text-text-muted">{card.games}</td>
                  <td className="py-3 px-2.5 tabular-nums">{card.wins}-{card.losses}</td>
                  <td className="py-3 px-2.5 tabular-nums font-bold">{card.win_rate}%</td>
                  <td className="py-3 px-2.5 tabular-nums text-text-muted">
                    {card.win_rate_not_played != null ? `${card.win_rate_not_played}%` : '-'}
                  </td>
                  <td className="py-3 px-5"><EffectBar effect={card.effect} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
