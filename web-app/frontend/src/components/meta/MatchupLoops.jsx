import { useMemo, useRef, useState } from 'react'
import { ElementPair, ELEMENT_COLORS } from '@/components/meta/MetaMap'
import { cellStyle } from '@/components/meta/DeckTypeMatchups'

/**
 * Rock-paper-scissors loops between decks (Avatar + element pair, the Deck
 * Archetypes grouping): A beats B, B beats C, C beats A. The Cycle Finder lists
 * the loops it finds; the Chain Walker lets you follow "beats" arrows by hand.
 * Built from the same saved winner > loser totals as "Your deck's matchups".
 * Totals only, never a deck list.
 */

const UP = '#3fb950'
const DOWN = '#f47067'
export const MIN_LOOP_DECK_GAMES = 20 // a deck needs this many games to be in a loop
export const MIN_LOOP_EDGE_GAMES = 10 // and each arrow this many games head to head
export const LOOP_THRESHOLDS = [52, 55, 60]
const SHOWN = 8

const panel = 'bg-bg-surface border border-border rounded-lg p-4'
const sel = 'bg-bg-raised border border-border rounded px-2 py-1 text-sm text-text-primary min-w-0 w-full sm:w-auto max-w-full'

/**
 * games = [{ winner: [avatar, elements], loser: [avatar, elements], n }]
 * Returns { decks: [{ key, avatar, elements, games, winRate }], edges: Map("a>b" -> { games, wins }) }
 * where wins counts a's wins over b. Only decks with enough games, no mirrors.
 */
export function deckGraph(games, minDeckGames = MIN_LOOP_DECK_GAMES) {
  const totals = new Map()
  const pairs = new Map()
  for (const { winner: w, loser: l, n = 1 } of games) {
    if (!w?.[0] || !w?.[1] || !l?.[0] || !l?.[1]) continue
    const a = `${w[0]}|${w[1]}`
    const b = `${l[0]}|${l[1]}`
    if (a === b) continue
    for (const [k, won] of [[a, n], [b, 0]]) {
      const t = totals.get(k) || { games: 0, wins: 0 }
      t.games += n
      t.wins += won
      totals.set(k, t)
    }
    for (const [x, y, won] of [[a, b, n], [b, a, 0]]) {
      const e = pairs.get(`${x}>${y}`) || { games: 0, wins: 0 }
      e.games += n
      e.wins += won
      pairs.set(`${x}>${y}`, e)
    }
  }
  const decks = [...totals]
    .filter(([, t]) => t.games >= minDeckGames)
    .map(([key, t]) => {
      const [avatar, elements] = key.split('|')
      return { key, avatar, elements, games: t.games, winRate: Math.round((t.wins / t.games) * 1000) / 10 }
    })
    .sort((x, y) => y.games - x.games)
  const keep = new Set(decks.map((d) => d.key))
  const edges = new Map()
  for (const [k, e] of pairs) {
    const [a, b] = k.split('>')
    if (keep.has(a) && keep.has(b)) edges.set(k, { games: e.games, winRate: Math.round((e.wins / e.games) * 1000) / 10 })
  }
  return { decks, edges }
}

/** a beats b at least `min`% over enough games */
function beats(edges, a, b, min, minGames) {
  const e = edges.get(`${a}>${b}`)
  return !!e && e.games >= minGames && e.winRate >= min && e.winRate > 50
}

/**
 * Every three-deck loop where each arrow wins at least `min`%. Strength is the
 * weakest arrow; strongest loops first, then the most games.
 */
export function findLoops(graph, min = 55, minGames = MIN_LOOP_EDGE_GAMES) {
  const { decks, edges } = graph
  const keys = decks.map((d) => d.key)
  const out = []
  // a is the smallest index in the loop, so each loop is found once
  for (let i = 0; i < keys.length; i++) {
    const a = keys[i]
    for (let j = i + 1; j < keys.length; j++) {
      const b = keys[j]
      for (const [x, y] of [[a, b], [b, a]]) {
        if (!beats(edges, x, y, min, minGames)) continue
        for (let k = i + 1; k < keys.length; k++) {
          if (k === j) continue
          const c = keys[k]
          // x > y > c > x, rotated so a comes first
          if (beats(edges, y, c, min, minGames) && beats(edges, c, x, min, minGames)) {
            const loop = x === a ? [a, b, c] : [a, c, b]
            const arrows = loop.map((d, n) => edges.get(`${d}>${loop[(n + 1) % 3]}`))
            out.push({
              decks: loop,
              arrows,
              strength: Math.min(...arrows.map((r) => r.winRate)),
              games: arrows.reduce((s, r) => s + r.games, 0),
            })
          }
        }
      }
    }
  }
  const seen = new Set()
  return out
    .filter((l) => {
      const id = l.decks.join('>')
      if (seen.has(id)) return false
      seen.add(id)
      return true
    })
    .sort((p, q) => q.strength - p.strength || q.games - p.games)
}

/** What a deck beats and loses to, each with enough games. */
export function deckMatchups(graph, key, minGames = MIN_LOOP_EDGE_GAMES) {
  const rows = graph.decks
    .filter((d) => d.key !== key)
    .map((d) => ({ ...d, vs: graph.edges.get(`${key}>${d.key}`) }))
    .filter((d) => d.vs && d.vs.games >= minGames)
  return {
    beats: rows.filter((r) => r.vs.winRate > 50).sort((x, y) => y.vs.winRate - x.vs.winRate || y.vs.games - x.vs.games),
    losesTo: rows.filter((r) => r.vs.winRate < 50).sort((x, y) => x.vs.winRate - y.vs.winRate || y.vs.games - x.vs.games),
  }
}

const deckLabel = (key) => {
  const [avatar, elements = ''] = key.split('|')
  return `${avatar} ${elements.includes(' / ') ? elements.replace(' / ', '/') : `Mono ${elements}`}`
}

function DeckName({ k }) {
  const [avatar, elements] = k.split('|')
  return (
    <span>
      <span className="mr-1.5">{avatar}</span>
      {elements.includes(' / ') ? <ElementPair pair={elements} /> : <span className="text-xs">Mono <ElementPair pair={elements} /></span>}
    </span>
  )
}

/* ---- Cycle Finder triangle ---- */
const POS = [[160, 30], [260, 196], [60, 196]]
const BOX_W = 112
const BOX_H = 44
/** How far from a box's center its edge is, going in direction (dx, dy). */
function boxEdge(dx, dy) {
  const len = Math.hypot(dx, dy)
  const ux = Math.abs(dx / len)
  const uy = Math.abs(dy / len)
  return Math.min(ux ? BOX_W / 2 / ux : Infinity, uy ? BOX_H / 2 / uy : Infinity) + 5
}

function shorten(x1, y1, x2, y2, a, b) {
  const dx = x2 - x1
  const dy = y2 - y1
  const len = Math.hypot(dx, dy)
  return [x1 + (dx * a) / len, y1 + (dy * a) / len, x2 - (dx * b) / len, y2 - (dy * b) / len]
}

function LoopTriangle({ loop, id, onPick }) {
  return (
    <svg viewBox="0 0 320 232" className="w-full h-auto" role="img"
         aria-label={`Loop: ${loop.decks.map(deckLabel).join(' beats ')} beats ${deckLabel(loop.decks[0])}`}>
      <defs>
        <marker id={`loop-ah-${id}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill={UP} />
        </marker>
      </defs>
      {loop.decks.map((_, n) => {
        const [x1, y1] = POS[n]
        const [x2, y2] = POS[(n + 1) % 3]
        const d = boxEdge(x2 - x1, y2 - y1)
        const s = shorten(x1, y1, x2, y2, d, d + 1)
        const mx = (x1 + x2) / 2 + (n === 1 ? 0 : n === 0 ? 22 : -22)
        const my = (y1 + y2) / 2 + (n === 1 ? 18 : -4)
        const arrow = loop.arrows[n]
        return (
          <g key={n}>
            <line x1={s[0]} y1={s[1]} x2={s[2]} y2={s[3]} stroke={UP} strokeWidth="2.5" markerEnd={`url(#loop-ah-${id})`} />
            <text x={mx} y={my} textAnchor="middle" fontSize="13" fontWeight="700" fill={UP}>{arrow.winRate}%</text>
            <text x={mx} y={my + 13} textAnchor="middle" fontSize="10" fill="#8b949e">{arrow.games} games</text>
          </g>
        )
      })}
      {loop.decks.map((k, n) => {
        const [x, y] = POS[n]
        const [avatar, elements] = k.split('|')
        const parts = elements.split(' / ')
        return (
          <g key={k} role="button" tabIndex={0} style={{ cursor: 'pointer' }} aria-label={`Follow ${deckLabel(k)} in the Chain Walker`}
             onClick={() => onPick(k)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onPick(k) } }}>
            <rect x={x - BOX_W / 2} y={y - BOX_H / 2} width={BOX_W} height={BOX_H} rx="8" fill="#161b22" stroke="#30363d" />
            <text x={x} y={y - 4} textAnchor="middle" fontSize="13" fontWeight="600" fill="#f0f6fc">{avatar}</text>
            <text x={x} y={y + 13} textAnchor="middle" fontSize="11" fontWeight="600">
              {parts.length === 1 && <tspan fill="#8b949e">Mono </tspan>}
              {parts.map((e, i) => (
                <tspan key={e}>
                  {i > 0 && <tspan fill="#8b949e"> / </tspan>}
                  <tspan fill={ELEMENT_COLORS[e] || '#f0f6fc'}>{e}</tspan>
                </tspan>
              ))}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

/* ---- Chain Walker ---- */
function ChainWalker({ graph, chain, setChain }) {
  const options = graph.decks
  const start = chain[0]
  const cur = chain[chain.length - 1]
  const closed = chain.length > 1 && cur === start
  const { beats: b, losesTo } = useMemo(() => deckMatchups(graph, cur), [graph, cur])
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <label htmlFor="loop-walk-start" className="text-text-muted">Start with</label>
        <select id="loop-walk-start" className={sel} value={start} onChange={(e) => setChain([e.target.value])}>
          {options.map((d) => <option key={d.key} value={d.key}>{deckLabel(d.key)} ({d.games} games)</option>)}
        </select>
        {chain.length > 1 && (
          <>
            <button type="button" onClick={() => setChain(chain.slice(0, -1))}
                    className="px-2 py-1 rounded border border-border bg-bg-raised text-text-muted hover:text-text-primary">Back</button>
            <button type="button" onClick={() => setChain([start])}
                    className="px-2 py-1 rounded border border-border bg-bg-raised text-text-muted hover:text-text-primary">Start over</button>
          </>
        )}
      </div>
      <ol className="flex flex-wrap items-center gap-x-2 gap-y-1.5 text-sm" aria-label="Your chain">
        {chain.map((k, n) => (
          <li key={`${k}-${n}`} className="flex items-center gap-2">
            {n > 0 && <span className="text-xs font-semibold" style={{ color: UP }}>beats →</span>}
            <span className="rounded-full border border-border bg-bg-raised px-2.5 py-0.5"><DeckName k={k} /></span>
          </li>
        ))}
      </ol>
      {closed && (
        <p className="rounded px-3 py-2 text-sm font-semibold" style={{ background: 'rgba(63,185,80,0.15)', color: UP }}>
          Loop closed in {chain.length - 1} steps: every deck in it beats the next one.
        </p>
      )}
      {!closed && chain.length === 1 && (
        <p className="text-xs text-text-muted">Tap a deck it beats to follow the chain. When you reach a deck that beats where you started, the loop closes.</p>
      )}
      <div className="grid gap-5 grid-cols-[repeat(auto-fit,minmax(min(100%,260px),1fr))]">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wider mb-2" style={{ color: UP }}>Beats</p>
          {b.length ? (
            <ul className="grid gap-1.5">
              {b.map((r) => {
                const closes = chain.length > 1 && r.key === start && !closed
                const used = chain.includes(r.key) && r.key !== start
                const disabled = closed || used || (r.key === start && chain.length === 1)
                return (
                  <li key={r.key}>
                    <button type="button" disabled={disabled} onClick={() => setChain([...chain, r.key])}
                            className={`w-full grid grid-cols-[1fr_auto] gap-3 items-center text-left text-sm rounded border px-2 py-1.5 ${closes ? 'border-secondary bg-secondary/10' : 'border-border bg-bg-raised hover:border-text-muted'} ${disabled ? 'opacity-45 cursor-default' : ''}`}>
                      <span className="min-w-0 truncate"><DeckName k={r.key} />{closes && <span className="text-xs text-secondary ml-1.5">closes the loop</span>}</span>
                      <span className="whitespace-nowrap text-right">
                        <span className="font-mono font-semibold" style={{ color: UP }}>{r.vs.winRate}%</span>
                        <span className="text-xs text-text-muted ml-2 inline-block w-16 text-left">{r.vs.games} games</span>
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          ) : <p className="text-sm text-text-muted">Nothing with enough games that it beats more often than not.</p>}
        </div>
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wider mb-2" style={{ color: DOWN }}>Loses to</p>
          {losesTo.length ? (
            <ul className="grid gap-1.5">
              {losesTo.map((r) => (
                <li key={r.key} className="grid grid-cols-[1fr_auto] gap-3 items-center text-sm px-2 py-1.5">
                  <span className="min-w-0 truncate"><DeckName k={r.key} /></span>
                  <span className="whitespace-nowrap text-right">
                    <span className="font-mono font-semibold" style={{ color: DOWN }}>{r.vs.winRate}%</span>
                    <span className="text-xs text-text-muted ml-2 inline-block w-16 text-left">{r.vs.games} games</span>
                  </span>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-text-muted">Nothing with enough games beats it more often than not.</p>}
        </div>
      </div>
    </div>
  )
}

/* ---- Matchup Ring ---- */
export const RING_DEFAULT = 10
export const RING_MAX = 16

function MatchupRing({ graph, picked, setPicked, onPick }) {
  const keys = useDeckSet(graph, picked)
  const [focus, setFocus] = useState('')
  const sel0 = keys.includes(focus) ? focus : keys[0]
  const n = keys.length
  const C = 210
  const R = 135
  const pos = keys.map((_, i) => {
    const t = -Math.PI / 2 + (i * 2 * Math.PI) / n
    return [C + R * Math.cos(t), C + R * Math.sin(t), t]
  })
  const lines = []
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const e = graph.edges.get(`${keys[i]}>${keys[j]}`)
      if (!e || e.games < MIN_LOOP_EDGE_GAMES || e.winRate === 50) continue
      const [w, l, rate] = e.winRate > 50 ? [i, j, e.winRate] : [j, i, 100 - e.winRate]
      lines.push({ w, l, rate: Math.round(rate * 10) / 10, games: e.games })
    }
  }
  const si = keys.indexOf(sel0)
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">
        <span><span className="inline-block w-4 h-0.5 align-middle mr-1.5" style={{ background: UP }} />Picked deck wins</span>
        <span><span className="inline-block w-4 h-0.5 align-middle mr-1.5" style={{ background: DOWN }} />Picked deck loses</span>
        <span>Tap a deck to pick it.</span>
      </div>
      {n < 3 ? (
        <p className="text-sm text-text-muted">Add at least three decks to draw the ring.</p>
      ) : (
        <div className="max-w-xl w-full mx-auto">
          <svg viewBox="-95 0 610 420" className="w-full h-auto" role="img" aria-label="Matchup ring: arrows point from winner to loser">
            <defs>
              {[['w', UP], ['l', DOWN], ['n', '#30363d']].map(([k, c]) => (
                <marker key={k} id={`ring-ah-${k}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth={k === 'n' ? 6 : 11} markerHeight={k === 'n' ? 6 : 11} markerUnits="userSpaceOnUse" orient="auto-start-reverse">
                  <path d="M0,0 L10,5 L0,10 z" fill={c} />
                </marker>
              ))}
            </defs>
            {[...lines].sort((a, b) => (a.w === si || a.l === si) - (b.w === si || b.l === si)).map((ln) => {
              const mine = ln.w === si ? 'w' : ln.l === si ? 'l' : 'n'
              const [x1, y1] = pos[ln.w]
              const [x2, y2] = pos[ln.l]
              const s = shorten(x1, y1, x2, y2, 17, 19)
              const color = mine === 'w' ? UP : mine === 'l' ? DOWN : '#30363d'
              // label sits on the far half of the line from the picked deck, so they don't pile up around it
              const f = mine === 'w' ? 0.62 : 0.38
              const lx = s[0] * (1 - f) + s[2] * f
              const ly = s[1] * (1 - f) + s[3] * f
              return (
                <g key={`${ln.w}-${ln.l}`}>
                  <line x1={s[0]} y1={s[1]} x2={s[2]} y2={s[3]} stroke={color}
                        strokeWidth={mine === 'n' ? 1 : 1.5 + Math.min(4, (ln.rate - 50) / 4)}
                        opacity={mine === 'n' ? 0.6 : 1} markerEnd={`url(#ring-ah-${mine})`} />
                  {mine !== 'n' && (
                    <text x={lx} y={ly} textAnchor="middle" dominantBaseline="middle" fontSize="11" fontWeight="700" fill={color}
                          stroke="#0d1117" strokeWidth="3" paintOrder="stroke">
                      {mine === 'w' ? ln.rate : Math.round((100 - ln.rate) * 10) / 10}%
                    </text>
                  )}
                </g>
              )
            })}
            {keys.map((k, i) => {
              const [x, y, t] = pos[i]
              const on = i === si
              const [avatar, elements] = k.split('|')
              const parts = elements.split(' / ')
              const lx = C + (R + 26) * Math.cos(t)
              const ly = C + (R + 26) * Math.sin(t)
              const anchor = Math.abs(Math.cos(t)) < 0.3 ? 'middle' : Math.cos(t) > 0 ? 'start' : 'end'
              const dy = Math.abs(Math.cos(t)) < 0.3 ? (Math.sin(t) < 0 ? -8 : 8) : 0
              return (
                <g key={k} role="button" tabIndex={0} style={{ cursor: 'pointer' }} aria-label={`Pick ${deckLabel(k)}`} aria-pressed={on}
                   onClick={() => setFocus(k)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setFocus(k) } }}>
                  <circle cx={x} cy={y} r="22" fill="transparent" />
                  <circle cx={x} cy={y} r="13" fill={on ? '#e3b341' : '#161b22'} stroke={on ? '#e3b341' : '#8b949e'} strokeWidth="1.5" />
                  <text x={lx} y={ly + dy - 2} textAnchor={anchor} fontSize="12.5" fontWeight={on ? 700 : 600} fill="#f0f6fc">{avatar}</text>
                  <text x={lx} y={ly + dy + 12} textAnchor={anchor} fontSize="10.5" fontWeight="600">
                    {parts.length === 1 && <tspan fill="#8b949e">Mono </tspan>}
                    {parts.map((e, m) => (
                      <tspan key={e}>
                        {m > 0 && <tspan fill="#8b949e"> / </tspan>}
                        <tspan fill={ELEMENT_COLORS[e] || '#f0f6fc'}>{e}</tspan>
                      </tspan>
                    ))}
                  </text>
                </g>
              )
            })}
          </svg>
        </div>
      )}
      {n >= 3 && sel0 && (
        <p className="text-sm text-center">
          <DeckName k={sel0} />{' '}
          <button type="button" onClick={() => onPick(sel0)} className="text-primary hover:underline ml-1">Follow in Chain Walker</button>
        </p>
      )}
      <DeckSetPicker graph={graph} keys={keys} picked={picked} setPicked={setPicked} label="Decks on the ring" />
    </div>
  )
}

/** Default top decks, or the viewer's own list: add with a menu, tap a chip to remove. */
function DeckSetPicker({ graph, keys, picked, setPicked, label }) {
  const others = graph.decks.filter((d) => !keys.includes(d.key))
  const n = keys.length
  return (
    <div className="grid gap-2 border-t border-border pt-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-text-muted">{label} ({n}):</span>
        <select aria-label={`Add a deck: ${label}`} className={sel} value="" disabled={!others.length || n >= RING_MAX}
                onChange={(e) => e.target.value && setPicked([...keys, e.target.value])}>
          <option value="">{n >= RING_MAX ? `Up to ${RING_MAX} decks` : 'Add a deck…'}</option>
          {others.map((d) => <option key={d.key} value={d.key}>{deckLabel(d.key)} ({d.games} games)</option>)}
        </select>
        {picked && (
          <button type="button" onClick={() => setPicked(null)} className="text-primary hover:underline text-sm">Reset to top {RING_DEFAULT}</button>
        )}
      </div>
      <ul className="flex flex-wrap gap-1.5" aria-label={label}>
        {keys.map((k) => (
          <li key={k}>
            <button type="button" onClick={() => setPicked(keys.filter((x) => x !== k))} aria-label={`Remove ${deckLabel(k)}`}
                    className="rounded-full border border-border bg-bg-raised px-2.5 py-0.5 text-sm hover:border-text-muted">
              <DeckName k={k} /> <span className="text-text-muted ml-1">×</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** The picked keys still in the window, or the most played decks. */
function useDeckSet(graph, picked) {
  const top = graph.decks.slice(0, RING_DEFAULT).map((d) => d.key)
  return (picked || top).filter((k) => graph.decks.some((d) => d.key === k))
}

/* ---- Cleaner matrix ---- */
function MatchupMatrix({ graph, picked, setPicked }) {
  const keys = useDeckSet(graph, picked)
  const [min, setMin] = useState(52)
  const [loopId, setLoopId] = useState('')
  const sub = useMemo(() => {
    const keep = new Set(keys)
    return { decks: graph.decks.filter((d) => keep.has(d.key)), edges: graph.edges }
  }, [graph, keys.join('\n')])
  const loops = useMemo(() => findLoops(sub, min), [sub, min])
  const loop = loops.find((l) => l.decks.join('>') === loopId) || (loopId === 'none' ? null : loops[0] || null)
  const on = new Set(loop ? loop.decks.map((d, n) => `${d}>${loop.decks[(n + 1) % 3]}`) : [])
  const rows = [...sub.decks].sort((a, b) => b.winRate - a.winRate)
  const short = (k) => {
    const [avatar, elements] = k.split('|')
    return [avatar.length > 8 ? `${avatar.slice(0, 7)}.` : avatar, elements.split(' / ')]
  }
  return (
    <div className="grid gap-4 grid-cols-[minmax(0,1fr)]">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        <label className="flex flex-wrap items-center gap-2 text-text-muted min-w-0 max-w-full">
          Highlight loop
          <select aria-label="Highlight a loop" className={sel} value={loop ? loop.decks.join('>') : 'none'} onChange={(e) => setLoopId(e.target.value)}>
            <option value="none">None</option>
            {loops.map((l) => (
              <option key={l.decks.join('>')} value={l.decks.join('>')}>
                {l.decks.map((d) => d.split('|')[0]).join(' → ')} ({l.strength}%+)
              </option>
            ))}
          </select>
        </label>
        <div className="flex items-center gap-2 text-text-muted">
          Each arrow at least
          <div className="flex rounded border border-border overflow-hidden" role="group" aria-label="Loops: each arrow wins at least">
            {LOOP_THRESHOLDS.map((t) => (
              <button key={t} type="button" aria-pressed={min === t} onClick={() => { setMin(t); setLoopId('') }}
                      className={`px-2 py-1 text-xs ${min === t ? 'bg-secondary/20 text-secondary' : 'bg-bg-raised text-text-muted hover:text-text-primary'}`}>
                {t}%
              </button>
            ))}
          </div>
        </div>
        {!loops.length && <span className="text-xs text-text-muted">No loops among these decks at {min}%+.</span>}
      </div>
      {rows.length < 2 ? (
        <p className="text-sm text-text-muted">Add at least two decks to fill the grid.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="border-separate text-xs font-mono" style={{ borderSpacing: 2 }}>
            <thead>
              <tr>
                <th className="sticky left-0 bg-bg-surface" />
                {rows.map((c) => {
                  const [a, els] = short(c.key)
                  return (
                    <th key={c.key} title={deckLabel(c.key)} className="font-sans font-semibold text-text-muted px-1 pb-1 align-bottom leading-tight min-w-[3rem]">
                      {a}<br />
                      {els.map((e) => <span key={e} style={{ color: ELEMENT_COLORS[e] }}>{e[0]}</span>)}
                    </th>
                  )
                })}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key}>
                  <th className="sticky left-0 z-10 bg-bg-surface font-sans font-semibold text-right pr-2 whitespace-nowrap text-sm">
                    <DeckName k={r.key} />
                  </th>
                  {rows.map((c) => {
                    if (c.key === r.key) return <td key={c.key} className="text-center text-text-muted bg-bg-raised rounded">–</td>
                    const e = graph.edges.get(`${r.key}>${c.key}`)
                    const ok = e && e.games >= MIN_LOOP_EDGE_GAMES
                    const hl = on.has(`${r.key}>${c.key}`)
                    return (
                      <td key={c.key} title={e ? `${deckLabel(r.key)} vs ${deckLabel(c.key)}: ${e.winRate}% over ${e.games} games` : 'No games'}
                          className={`text-center rounded h-8 px-1 ${hl ? 'font-bold' : ''}`}
                          style={{ ...(ok ? cellStyle(e.winRate) : cellStyle(null)), ...(hl ? { outline: '2.5px solid #e3b341', outlineOffset: -1 } : {}) }}>
                        {ok ? Math.round(e.winRate) : '·'}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-text-muted">Read across: the row deck&apos;s win rate against the column deck. Decks sorted by overall win rate. A dot means fewer than {MIN_LOOP_EDGE_GAMES} games head to head.</p>
      <DeckSetPicker graph={graph} keys={keys} picked={picked} setPicked={setPicked} label="Decks in the grid" />
    </div>
  )
}

/* ---- Section ---- */
export default function MatchupLoops({ games }) {
  const graph = useMemo(() => deckGraph(games), [games])
  const [min, setMin] = useState(55)
  const [must, setMust] = useState('')
  const [showAll, setShowAll] = useState(false)
  const [chainState, setChain] = useState([])
  const [ringPick, setRingPick] = useState(null) // null = the most played decks
  const [gridPick, setGridPick] = useState(null)
  const walkerRef = useRef(null)

  const loops = useMemo(() => findLoops(graph, min), [graph, min])
  const has = (k) => graph.decks.some((d) => d.key === k)
  const mustKey = has(must) ? must : ''
  const listed = mustKey ? loops.filter((l) => l.decks.includes(mustKey)) : loops
  const shown = showAll ? listed : listed.slice(0, SHOWN)
  // The walker keeps its chain while the decks in it still have enough games
  const chain = chainState.length && chainState.every(has) ? chainState : graph.decks[0] ? [graph.decks[0].key] : []

  const pick = (k) => {
    setChain([k])
    walkerRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  if (graph.decks.length < 3) {
    return <div className={`${panel} text-sm text-text-muted`}>Not enough games in this window to look for loops. Try a longer window.</div>
  }

  return (
    <div className="grid gap-6 grid-cols-[minmax(0,1fr)]">
      {/* Cycle Finder */}
      <div className={`${panel} grid gap-4 grid-cols-[minmax(0,1fr)]`}>
        <div>
          <p className="text-xs uppercase tracking-wider text-text-muted">Cycle Finder</p>
          <p className="text-sm text-text-muted mt-1">
            Every set of three decks where each one beats the next. A loop is only as strong as its weakest arrow, so strongest loops come first. Tap a deck to follow it in the Chain Walker.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <label className="flex flex-wrap items-center gap-2 text-text-muted min-w-0 max-w-full">
            Must include
            <select aria-label="Loops must include" className={sel} value={mustKey} onChange={(e) => { setMust(e.target.value); setShowAll(false) }}>
              <option value="">Any deck</option>
              {graph.decks.map((d) => <option key={d.key} value={d.key}>{deckLabel(d.key)}</option>)}
            </select>
          </label>
          <div className="flex items-center gap-2 text-text-muted">
            Each arrow at least
            <div className="flex rounded border border-border overflow-hidden" role="group" aria-label="Each arrow wins at least">
              {LOOP_THRESHOLDS.map((t) => (
                <button key={t} type="button" aria-pressed={min === t} onClick={() => { setMin(t); setShowAll(false) }}
                        className={`px-2 py-1 text-xs ${min === t ? 'bg-secondary/20 text-secondary' : 'bg-bg-raised text-text-muted hover:text-text-primary'}`}>
                  {t}%
                </button>
              ))}
            </div>
          </div>
        </div>
        {listed.length ? (
          <>
            <p className="text-xs text-text-muted">{listed.length} {listed.length === 1 ? 'loop' : 'loops'} found.</p>
            <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(min(100%,250px),1fr))]">
              {shown.map((l, n) => (
                <div key={l.decks.join('>')} className="bg-bg-raised/40 border border-border rounded-lg p-3 grid gap-1">
                  <div className="flex justify-between items-baseline text-xs text-text-muted">
                    <span className="font-semibold text-text-primary text-sm">Loop {n + 1}</span>
                    <span>every arrow {l.strength}%+</span>
                  </div>
                  <LoopTriangle loop={l} id={n} onPick={pick} />
                </div>
              ))}
            </div>
            {listed.length > SHOWN && (
              <button type="button" onClick={() => setShowAll((s) => !s)} className="justify-self-center text-sm text-primary hover:underline">
                {showAll ? 'Show fewer' : `Show all ${listed.length} loops`}
              </button>
            )}
          </>
        ) : (
          <p className="text-sm text-text-muted">
            No loops where every arrow wins {min}%+{mustKey ? ` with ${deckLabel(mustKey)}` : ''} in this window. Try a lower number or a longer window.
          </p>
        )}
      </div>

      {/* Matchup Ring */}
      <div className={`${panel} grid gap-4 grid-cols-[minmax(0,1fr)]`}>
        <div>
          <p className="text-xs uppercase tracking-wider text-text-muted">Matchup Ring</p>
          <p className="text-sm text-text-muted mt-1">
            The {RING_DEFAULT} most played decks in this window, with an arrow from each winner to the deck it beats. Pick a deck to light up its wins and losses, and add or remove decks below.
          </p>
        </div>
        <MatchupRing graph={graph} picked={ringPick} setPicked={setRingPick} onPick={pick} />
      </div>

      {/* Cleaner matrix */}
      <div className={`${panel} grid gap-4 grid-cols-[minmax(0,1fr)]`}>
        <div>
          <p className="text-xs uppercase tracking-wider text-text-muted">Matchup Grid</p>
          <p className="text-sm text-text-muted mt-1">Every head-to-head win rate for the decks you pick, green to red, with a loop outlined in gold.</p>
        </div>
        <MatchupMatrix graph={graph} picked={gridPick} setPicked={setGridPick} />
      </div>

      {/* Chain Walker */}
      <div ref={walkerRef} className={`${panel} grid gap-4 grid-cols-[minmax(0,1fr)] scroll-mt-24 sm:scroll-mt-64`}>
        <div>
          <p className="text-xs uppercase tracking-wider text-text-muted">Chain Walker</p>
          <p className="text-sm text-text-muted mt-1">Pick a deck, see what it beats and what beats it, then tap to follow the chain.</p>
        </div>
        <ChainWalker graph={graph} chain={chain} setChain={setChain} />
      </div>

      <p className="text-xs text-text-muted text-center">
        A deck is an Avatar plus its top two elements by Spellbook copies, like Deck Archetypes. Each deck needs {MIN_LOOP_DECK_GAMES} games and each arrow {MIN_LOOP_EDGE_GAMES} head-to-head games; mirrors don&apos;t count. Totals only, never a deck list.
      </p>
    </div>
  )
}
