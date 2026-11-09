import { useState } from 'react'
import { ElementPair } from '@/components/meta/MetaMap'

/**
 * "What does my deck lose to?" Pick a deck type (the Deck Archetypes element
 * groups: a deck's top two elements by Spellbook copies), optionally an Avatar,
 * and see what it beats and loses to. Used by the Meta Report (numbers built on
 * the server) and Elemental Win Rates (numbers summed here from daily totals,
 * filters in the page's top bar). Totals only, never a deck list.
 */

const UP = '#3fb950'
const DOWN = '#f47067'
const ELEMENTS = ['Air', 'Earth', 'Fire', 'Water']
export const MIN_DECK_GAMES = 20     // like an Avatar needs for the Meta Report tiers...
export const MIN_DECK_SHARE = 0.01   // ...and 1% of the deck-games
export const MIN_MATCHUP_GAMES = 10  // like a matchup grid cell

const VS_VIEWS = [
  { key: 'avatar', label: 'Avatars' },
  { key: 'deckType', label: 'Deck types' },
  { key: 'both', label: 'Avatar + deck type' },
]
const KIND_GROUPS = [
  { kind: 'mono', label: 'Mono element' },
  { kind: 'pair', label: 'Two elements' },
  { kind: 'any', label: 'Any deck with' },
]
const panel = 'bg-bg-surface border border-border rounded-lg p-4'
const selectCls = 'bg-bg-raised border border-border rounded px-3 py-2 text-sm text-text-primary w-full'

export function cellStyle(v) {
  if (v == null) return { background: '#21262d', color: '#8b949e' }
  const t = Math.max(-1, Math.min(1, (v - 50) / 12))
  const rgb = t >= 0 ? '63,185,80' : '244,112,103'
  return { background: `rgba(${rgb},${(Math.abs(t) * 0.55 + 0.08).toFixed(2)})`, color: '#f0f6fc' }
}

function label(key) {
  if (key.startsWith('any:')) return `Any ${key.slice(4)} deck`
  return key.includes(' / ') ? key : `Mono ${key}`
}

function typeKeys(elements) {
  return [elements, ...elements.split(' / ').filter((e) => ELEMENTS.includes(e)).map((e) => `any:${e}`)]
}

/**
 * Same numbers as services/meta_report.deck_type_matchups, from
 * games = [{ winner: [avatar, elements], loser: [avatar, elements], n }].
 * minDeckGames null = max(20, 1% of deck-games), as the Meta Report does.
 */
export function deckTypeMatchups(games, minDeckGames = null) {
  const stats = new Map()
  let deckGames = 0
  for (const { winner: w, loser: l, n = 1 } of games) {
    if (!w?.[1] || !l?.[1]) continue
    deckGames += 2 * n
    const picksOf = (me) => new Set(typeKeys(me[1]).flatMap((k) => [`${k}|`, `${k}|${me[0]}`]))
    const pw = picksOf(w)
    const pl = picksOf(l)
    for (const [me, opp, won, mine, theirs] of [[w, l, true, pw, pl], [l, w, false, pl, pw]]) {
      for (const pick of mine) {
        if (theirs.has(pick)) continue // mirror
        let rec = stats.get(pick)
        if (!rec) stats.set(pick, (rec = { games: 0, wins: 0, avatar: {}, deckType: {}, both: {} }))
        rec.games += n
        rec.wins += won ? n : 0
        for (const [view, name] of [['avatar', opp[0]], ['deckType', opp[1]], ['both', `${opp[0]}|${opp[1]}`]]) {
          const cell = (rec[view][name] ||= [0, 0])
          cell[0] += n
          cell[1] += won ? n : 0
        }
      }
    }
  }
  const minimum = minDeckGames ?? Math.max(MIN_DECK_GAMES, Math.ceil(deckGames * MIN_DECK_SHARE))
  const picks = {}
  const options = new Map()
  for (const [pick, rec] of stats) {
    if (rec.games < minimum) continue
    const cut = pick.lastIndexOf('|')
    const key = pick.slice(0, cut)
    const avatar = pick.slice(cut + 1)
    const out = { games: rec.games, winRate: Math.round((rec.wins / rec.games) * 1000) / 10 }
    for (const view of ['avatar', 'deckType', 'both']) {
      out[view] = Object.entries(rec[view])
        .filter(([, [m]]) => m >= MIN_MATCHUP_GAMES)
        .map(([name, [m, won]]) => {
          const row = { games: m, winRate: Math.round((won / m) * 1000) / 10 }
          if (view === 'both') [row.avatar, row.elements] = name.split('|')
          else if (view === 'avatar') row.avatar = name
          else row.elements = name
          return row
        })
        .sort((a, b) => a.winRate - b.winRate || b.games - a.games)
    }
    picks[pick] = out
    if (!options.has(key)) {
      options.set(key, {
        key, label: label(key), games: 0, avatars: [],
        kind: key.startsWith('any:') ? 'any' : key.includes(' / ') ? 'pair' : 'mono',
      })
    }
    const opt = options.get(key)
    if (avatar) opt.avatars.push({ avatar, games: rec.games })
    else opt.games = rec.games
  }
  const order = { mono: 0, pair: 1, any: 2 }
  const list = [...options.values()].filter((o) => o.games)
    .sort((a, b) => order[a.kind] - order[b.kind] || b.games - a.games)
  list.forEach((o) => o.avatars.sort((a, b) => b.games - a.games))
  return { options: list, picks, minDeckGames: minimum, minGames: MIN_MATCHUP_GAMES }
}

/** The option, Avatar and pick a selection lands on, falling back when it has too few games. */
export function resolveSelection(data, value) {
  const options = data?.options || []
  const option = options.find((o) => o.key === value?.type) || options[0] || null
  const avatar = option?.avatars.some((a) => a.avatar === value?.avatar) ? value.avatar : ''
  const pick = option ? data.picks?.[`${option.key}|${avatar}`] || null : null
  return { option, avatar, pick, view: value?.view || 'avatar' }
}

export function DeckTypeFilters({ data, value, onChange, compact = false }) {
  const { option, avatar, view } = resolveSelection(data, value)
  const options = data?.options || []
  const set = (patch) => onChange({ ...value, type: option?.key, avatar, view, ...patch })
  const labelCls = compact ? 'flex items-center gap-2 text-sm text-text-muted' : 'grid gap-1 text-xs text-text-muted'
  const sel = compact ? 'bg-bg-raised border border-border rounded px-2 py-1 text-sm text-text-primary' : selectCls
  return (
    <>
      <label className={labelCls}>
        {compact ? 'Your deck:' : 'Your deck'}
        <select aria-label="Your deck type" value={option?.key || ''} disabled={!option}
                onChange={(e) => set({ type: e.target.value, avatar: '' })} className={sel}>
          {!option && <option value="">Not enough games</option>}
          {KIND_GROUPS.map((g) => {
            const opts = options.filter((o) => o.kind === g.kind)
            return opts.length ? (
              <optgroup key={g.kind} label={g.label}>
                {opts.map((o) => <option key={o.key} value={o.key}>{o.label} ({o.games} games)</option>)}
              </optgroup>
            ) : null
          })}
        </select>
      </label>
      <label className={labelCls}>
        {compact ? 'Avatar:' : 'Avatar'}
        <select aria-label="Your Avatar" value={avatar} disabled={!option} onChange={(e) => set({ avatar: e.target.value })} className={sel}>
          <option value="">Any Avatar</option>
          {(option?.avatars || []).map((a) => <option key={a.avatar} value={a.avatar}>{a.avatar} ({a.games} games)</option>)}
        </select>
      </label>
      <div className={labelCls}>
        {compact ? 'Against:' : 'Against'}
        <div className="flex rounded border border-border overflow-hidden" role="group" aria-label="Group opponents by">
          {VS_VIEWS.map((v) => (
            <button key={v.key} type="button" onClick={() => set({ view: v.key })} aria-pressed={view === v.key}
                    className={`flex-1 ${compact ? 'px-2 py-1' : 'px-2 py-2'} text-xs ${view === v.key ? 'bg-secondary/20 text-secondary' : 'bg-bg-raised text-text-muted hover:text-text-primary'}`}>
              {v.label}
            </button>
          ))}
        </div>
      </div>
    </>
  )
}

function deckTypeName(elements) {
  if (!elements) return null
  return elements.includes(' / ') ? <ElementPair pair={elements} /> : <span className="text-xs">Mono <ElementPair pair={elements} /></span>
}

function OpponentList({ title, rows, color, empty }) {
  return (
    <div className="min-w-0">
      <p className="text-xs uppercase tracking-wider mb-2" style={{ color }}>{title}</p>
      {rows.length ? (
        <ul className="grid gap-1.5">
          {rows.map((r) => (
            <li key={`${r.avatar || ''}|${r.elements || ''}`} className="grid grid-cols-[1fr_auto] gap-3 items-center text-sm">
              <span className="min-w-0 truncate">
                {r.avatar && <span className="mr-1.5">{r.avatar}</span>}
                {deckTypeName(r.elements)}
              </span>
              <span className="text-right whitespace-nowrap">
                <span className="font-mono rounded px-1.5 py-0.5" style={cellStyle(r.winRate)}>{r.winRate}%</span>
                <span className="text-xs text-text-muted ml-2 inline-block w-16 text-left">{r.games} games</span>
              </span>
            </li>
          ))}
        </ul>
      ) : <p className="text-sm text-text-muted">{empty}</p>}
    </div>
  )
}

export function DeckTypeResults({ data, value, gamesLabel = 'games', emptyText = 'Not enough games to break matchups down by deck type.' }) {
  const { option, avatar, pick, view } = resolveSelection(data, value)
  if (!option || !pick) return <p className="text-sm text-text-muted">{emptyText}</p>
  const rows = pick[view] || []
  const losesTo = rows.filter((r) => r.winRate < 50)
  const beats = rows.filter((r) => r.winRate > 50).reverse()
  const even = rows.filter((r) => r.winRate === 50)
  const who = avatar ? `${avatar} ` : ''
  const deckLabel = option.kind === 'any' ? `${who}Decks with ${option.key.slice(4)}` : `${who}${option.label} decks`
  return (
    <div className="grid gap-4">
      <p className="text-sm">
        <b>{deckLabel}</b> won <span className="font-mono" style={{ color: pick.winRate >= 50 ? UP : DOWN }}>{pick.winRate}%</span> of {pick.games} {gamesLabel}.
      </p>
      <div className="grid gap-5 grid-cols-[repeat(auto-fit,minmax(min(100%,260px),1fr))]">
        <OpponentList title="Loses to" rows={losesTo} color={DOWN} empty="Nothing with enough games beats it more often than not." />
        <OpponentList title="Beats" rows={beats} color={UP} empty="Nothing with enough games that it beats more often than not." />
      </div>
      {even.length > 0 && (
        <p className="text-xs text-text-muted">Dead even (50%): {even.map((r) => [r.avatar, r.elements].filter(Boolean).join(' ')).join(', ')}.</p>
      )}
      <p className="text-xs text-text-muted">
        Win rates are for your deck. Your pick needs {data.minDeckGames} games to be listed and each opponent needs {data.minGames}; anything smaller is left out. Games where both decks fit your pick (mirrors) don&apos;t count. Totals only, never a deck list.
      </p>
    </div>
  )
}

/** Meta Report version: filters inside the box. */
export default function DeckTypeMatchups({ data }) {
  const [value, onChange] = useState({ type: '', avatar: '', view: 'avatar' })
  if (!(data?.options || []).length) {
    return (
      <div className={`${panel} text-sm text-text-muted mt-4`}>
        Not enough ranked games to break matchups down by deck type this period.
      </div>
    )
  }
  return (
    <div className={`${panel} mt-4 grid gap-4`}>
      <div>
        <p className="text-xs uppercase tracking-wider text-text-muted">Your deck&apos;s matchups</p>
        <p className="text-sm text-text-muted mt-1">
          Pick your deck type, and an Avatar if you like, to see what it beats and what it loses to. Deck types use the same element groups as Deck Archetypes: a deck&apos;s top two elements by Spellbook copies.
        </p>
      </div>
      <div className="grid gap-3 grid-cols-1 sm:grid-cols-3">
        <DeckTypeFilters data={data} value={value} onChange={onChange} />
      </div>
      <DeckTypeResults data={data} value={value} gamesLabel="ranked games this period" />
    </div>
  )
}
