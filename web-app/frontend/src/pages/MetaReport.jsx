import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { getMetaReport, listMetaReports, subscribeMetaReport } from '@/api/metaReports'
import Spinner from '@/components/ui/Spinner'
import ShareLinkButton from '@/components/ui/ShareLinkButton'
import TryDeckButton from '@/components/deck/TryDeckButton'
import usePageTitle from '@/hooks/usePageTitle'

/**
 * Meta Report: what the Summit plays and wins with, one report per half-month.
 *
 * Every number is built on the server (services/meta_report.py) from Summit
 * ranked games (totals only), PSO's ranked card data and the Top 8 page. This
 * page only lays it out; the report picker switches between published reports.
 */

const ELEMENT_COLORS = { Earth: '#a07a4a', Fire: '#d9553a', Water: '#4d8fd6', Air: '#b3b6d4' }
const TIER_COLORS = { S: '#ffd700', A: '#e6c200', B: '#a8bcf0', C: '#8b949e' }
const UP = '#3fb950'
const DOWN = '#f47067'

function ElementPair({ pair }) {
  const parts = String(pair || '').split(' / ').filter(Boolean)
  return (
    <span className="text-xs">
      {parts.map((e, i) => (
        <span key={e}>
          {i > 0 && <span className="text-text-muted"> / </span>}
          <span style={{ color: ELEMENT_COLORS[e] || 'inherit' }}>{e}</span>
        </span>
      ))}
    </span>
  )
}

function Move({ move }) {
  if (move === 'new') return <span className="text-[11px] font-mono text-secondary">NEW</span>
  if (typeof move !== 'number' || move === 0) return null
  return (
    <span className="text-[11px] font-mono" style={{ color: move > 0 ? UP : DOWN }}>
      {move > 0 ? `▲${move}` : `▼${-move}`}
    </span>
  )
}

function Section({ title, sub, children, className = '' }) {
  return (
    <section className={`min-w-0 ${className}`}>
      <h2 className="font-display text-2xl text-text-primary mb-1">{title}</h2>
      {sub && <p className="text-sm text-text-muted mb-3 max-w-prose">{sub}</p>}
      {children}
    </section>
  )
}

const panel = 'bg-bg-surface border border-border rounded-lg p-4'

function Story({ story }) {
  if (!story?.length) return <p className="text-text-muted text-sm">No takeaways for this report.</p>
  return (
    <ol className="grid gap-3">
      {story.map((s, i) => (
        <li key={i} className="grid grid-cols-[28px_1fr] gap-2">
          <span className="font-display text-secondary text-2xl leading-none">{i + 1}</span>
          <p>
            <span className="font-semibold">{s.headline}</span>{' '}
            <span className="text-text-muted">{s.detail}</span>
          </p>
        </li>
      ))}
    </ol>
  )
}

function Tiers({ archetypes }) {
  const groups = { S: [], A: [], B: [], C: [] }
  archetypes.forEach((a) => groups[a.tier]?.push(a))
  return (
    <div className={`${panel} grid gap-2`}>
      {Object.entries(groups).map(([tier, list]) => (
        <div key={tier} className="grid grid-cols-[44px_1fr] gap-2.5">
          <div
            className="grid place-items-center font-display font-bold text-2xl rounded text-bg-dark"
            style={{ background: TIER_COLORS[tier] }}
          >
            {tier}
          </div>
          <div className="flex flex-wrap gap-1.5 items-center min-h-10">
            {list.length ? list.map((a) => (
              <span
                key={`${a.avatar}|${a.elements}`}
                className="bg-bg-raised border border-border rounded px-2 py-1 text-sm flex gap-1.5 items-center"
                title={`${a.share}% of decks · ${a.winRate}% win rate · ${a.games} games`}
              >
                {a.avatar} <ElementPair pair={a.elements} /> <Move move={a.move} />
              </span>
            )) : <span className="text-text-muted text-sm">None this period</span>}
          </div>
        </div>
      ))}
    </div>
  )
}

// Place labels most-played first and skip any that would collide, so a
// crowded corner shows dots (with hover titles) instead of a pile of text.
function placeLabels(points, width) {
  const placed = []
  const boxes = []
  const overlaps = (b) => boxes.some((o) => b.x1 < o.x2 && b.x2 > o.x1 && b.y1 < o.y2 && b.y2 > o.y1)
  const dots = points.map((p) => ({ x1: p.x - 7, x2: p.x + 7, y1: p.y - 7, y2: p.y + 7 }))
  ;[...points].sort((a, b) => b.games - a.games).forEach((p) => {
    const w = p.label.length * 6.2
    for (const side of p.x > width - 120 ? ['left', 'right'] : ['right', 'left']) {
      const x1 = side === 'right' ? p.x + 9 : p.x - 9 - w
      const box = { x1, x2: x1 + w, y1: p.y - 9, y2: p.y + 5 }
      const hitsDot = dots.some((d, i) => points[i] !== p && box.x1 < d.x2 && box.x2 > d.x1 && box.y1 < d.y2 && box.y2 > d.y1)
      if (!overlaps(box) && !hitsDot) {
        boxes.push(box)
        placed.push({ ...p, lx: side === 'right' ? p.x + 9 : p.x - 9, anchor: side === 'right' ? 'start' : 'end' })
        return
      }
    }
  })
  return placed
}

function MetaMap({ archetypes }) {
  const [picked, setPicked] = useState(null)
  if (!archetypes.length) return null
  const W = 460, H = 300, L = 40, R = 12, T = 14, B = 34
  const maxShare = Math.max(4, Math.ceil(Math.max(...archetypes.map((a) => a.share)) / 2) * 2)
  const wrs = archetypes.map((a) => a.winRate)
  const lo = Math.min(45, Math.floor(Math.min(...wrs) / 5) * 5)
  const hi = Math.max(55, Math.ceil(Math.max(...wrs) / 5) * 5)
  const X = (v) => L + (v / maxShare) * (W - L - R)
  const Y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B)
  const step = (hi - lo) > 30 ? 10 : 5
  const yTicks = []
  for (let v = lo; v <= hi; v += step) yTicks.push(v)
  const xTicks = [0, maxShare / 4, maxShare / 2, (3 * maxShare) / 4, maxShare]
  const points = archetypes.map((a) => ({ ...a, x: X(a.share), y: Y(a.winRate), label: a.avatar }))
  const labels = placeLabels(points, W)
  return (
    <div className={panel}>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto block" role="img" aria-label="Archetypes by share of decks and win rate">
        {yTicks.map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={Y(v)} y2={Y(v)} stroke="#30363d" />
            <text x={L - 6} y={Y(v) + 4} textAnchor="end" fontSize="11" fill="#8b949e">{v}%</text>
          </g>
        ))}
        {xTicks.map((v) => (
          <text key={v} x={X(v)} y={H - B + 16} textAnchor="middle" fontSize="11" fill="#8b949e">{Number.isInteger(v) ? v : v.toFixed(1)}%</text>
        ))}
        <line x1={L} x2={W - R} y1={Y(50)} y2={Y(50)} stroke="#8b949e" strokeDasharray="3 4" />
        <g fontSize="10" fill="#8b949e" opacity="0.8" style={{ letterSpacing: '0.06em' }}>
          <text x={L + 6} y={T + 12}>SLEEPERS</text>
          <text x={W - R - 6} y={T + 12} textAnchor="end">DECK TO BEAT</text>
          <text x={L + 6} y={H - B - 8}>STRUGGLING</text>
          <text x={W - R - 6} y={H - B - 8} textAnchor="end">OVERPLAYED</text>
        </g>
        <text x={(L + W - R) / 2} y={H - 4} textAnchor="middle" fontSize="11" fill="#8b949e">Share of decks</text>
        {points.map((a) => (
          <circle key={`${a.avatar}|${a.elements}`} cx={a.x} cy={a.y} r="5.5" fill={TIER_COLORS[a.tier]}
                  stroke={picked?.avatar === a.avatar && picked?.elements === a.elements ? '#f0f6fc' : '#0d1117'} strokeWidth="1.5" className="cursor-pointer"
                  onClick={() => setPicked(archetypes.find((x) => x.avatar === a.avatar && x.elements === a.elements))}>
            <title>{`${a.avatar}: ${a.share}% of decks, ${a.winRate}% win rate, ${a.games} games`}</title>
          </circle>
        ))}
        {labels.map((a) => (
          <text key={`l-${a.avatar}|${a.elements}`} x={a.lx} y={a.y + 4} textAnchor={a.anchor} fontSize="11" fill="#f0f6fc">{a.label}</text>
        ))}
      </svg>
      {picked ? (
        <p className="text-sm mt-1">
          {picked.avatar} <ElementPair pair={picked.elements} />{' '}
          <span className="text-text-muted">{picked.share}% of decks · {picked.winRate}% win rate · {picked.games} games · {picked.tier} tier</span>
        </p>
      ) : labels.length < points.length && (
        <p className="text-xs text-text-muted mt-1">Labels show the most-played decks. Tap a dot for any deck.</p>
      )}
    </div>
  )
}

function Spark({ points }) {
  const vals = (points || []).filter((v) => typeof v === 'number')
  if (vals.length < 2) return null
  const w = 70, h = 20
  const min = Math.min(...vals) - 1, max = Math.max(...vals) + 1
  const pts = vals.map((v, i) => [i * (w - 4) / (vals.length - 1) + 2, h - 2 - (v - min) / (max - min) * (h - 4)])
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join('')
  const color = vals[vals.length - 1] >= vals[0] ? UP : DOWN
  const last = pts[pts.length - 1]
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-[70px] h-5" aria-hidden="true">
      <path d={d} fill="none" stroke={color} strokeWidth="1.5" />
      <circle cx={last[0]} cy={last[1]} r="2.2" fill={color} />
    </svg>
  )
}

function cardDetail(c) {
  return `in ${c.share}% of decks${c.winRate != null ? ` · wins ${c.winRate}% when played` : ''}`
}

function CardList({ title, cards }) {
  return (
    <div className={panel}>
      <p className="text-xs uppercase tracking-wider text-text-muted mb-2.5">{title}</p>
      {cards?.length ? (
        <ul className="grid gap-2">
          {cards.map((c) => (
            <li key={c.name} className="grid grid-cols-[1fr_auto] gap-2 items-center text-sm">
              <div className="min-w-0">
                <Link to={`/card/${encodeURIComponent(c.name)}`} className="hover:text-secondary">{c.name}</Link>
                <div className="text-xs text-text-muted">{cardDetail(c)}</div>
              </div>
              <div className="flex gap-2.5 items-center">
                <Spark points={c.trend} />
                {c.change != null && (
                  <span className="font-mono text-sm tabular-nums" style={{ color: c.change > 0 ? UP : DOWN }}>
                    {c.change > 0 ? '+' : ''}{c.change}
                  </span>
                )}
              </div>
            </li>
          ))}
        </ul>
      ) : <p className="text-sm text-text-muted">Nothing moved much.</p>}
    </div>
  )
}

function Cards({ cards }) {
  if (!cards?.available) {
    return (
      <div className={`${panel} text-sm text-text-muted`}>
        {cards?.empty
          ? 'Play Sorcery Online has no ranked card data for this period.'
          : "Play Sorcery Online hadn't released card data for this period when the report was built."}
      </div>
    )
  }
  const s = cards.sleeper
  const top = cards.mode === 'top'
  const minGames = cards.minGames || 20
  const tile = `${panel} min-w-0`
  return (
    <div className="grid gap-4">
      {cards.staples?.length > 0 && (
        <p className="text-sm">
          <span className="text-xs uppercase tracking-wider text-text-muted mr-2">Staples</span>
          {cards.staples.map((c, i) => (
            <span key={c.name}>
              {i > 0 && <span className="text-text-muted"> · </span>}
              <Link to={`/card/${encodeURIComponent(c.name)}`} className="hover:text-secondary">{c.name}</Link>
              <span className="text-text-muted"> {c.share}%</span>
            </span>
          ))}
        </p>
      )}
      <div className="grid gap-4 grid-cols-[repeat(auto-fit,minmax(min(100%,300px),1fr))]">
        {(cards.spotlights || []).map((t) => (
          <div key={t.kind} className={tile}>
            <p className="text-xs uppercase tracking-wider text-text-muted mb-2.5">{t.label}</p>
            <Link to={`/card/${encodeURIComponent(t.name)}`} className="font-display text-xl hover:text-secondary">{t.name}</Link>
            <p className="mt-1 text-sm text-text-muted">{t.detail}</p>
          </div>
        ))}
        {s && (
          <div className={`${tile} border-secondary/40`}>
            <p className="text-xs uppercase tracking-wider text-text-muted mb-2.5">Sleeper pick</p>
            <Link to={`/card/${encodeURIComponent(s.name)}`} className="font-display text-2xl text-secondary hover:underline">{s.name}</Link>
            <p className="mt-1 text-sm">
              Wins {s.winRate}% of games it&apos;s played in{' '}
              <span className="text-text-muted">but is in only {s.share}% of decks ({s.games} games)</span>
            </p>
            <p className="text-xs text-text-muted mt-2">A winning card few people run: under {cards.maxSleeperShare || 10}% of decks, {minGames}+ games.</p>
          </div>
        )}
      </div>
      {!top && (
        <div className="grid gap-4 grid-cols-[repeat(auto-fit,minmax(min(100%,300px),1fr))]">
          <CardList title="Rising" cards={cards.rising} />
          <CardList title="Falling" cards={cards.falling} />
        </div>
      )}
    </div>
  )
}

function cellStyle(v) {
  if (v == null) return { background: '#21262d', color: '#8b949e' }
  const t = Math.max(-1, Math.min(1, (v - 50) / 12))
  const rgb = t >= 0 ? '63,185,80' : '244,112,103'
  return { background: `rgba(${rgb},${(Math.abs(t) * 0.55 + 0.08).toFixed(2)})`, color: '#f0f6fc' }
}

function Matchups({ matchups }) {
  const names = matchups?.archetypes || []
  const cells = matchups?.cells || []
  const callouts = useMemo(() => {
    const list = []
    names.forEach((row, i) => names.forEach((col, j) => {
      const c = cells[i]?.[j]
      if (c && c.winRate != null) list.push({ row, col, ...c })
    }))
    if (!list.length) return []
    const best = list.reduce((a, b) => (b.winRate > a.winRate ? b : a))
    const even = list.reduce((a, b) => (Math.abs(b.winRate - 50) < Math.abs(a.winRate - 50) ? b : a))
    return [
      { title: 'Most lopsided', text: `${best.row.avatar} beats ${best.col.avatar} ${best.winRate}% of the time.` },
      { title: 'Closest to even', text: `${even.row.avatar} vs ${even.col.avatar} sits at ${even.winRate}%.` },
    ]
  }, [names, cells])

  const hasNumbers = cells.some((row) => row.some((c) => c && c.winRate != null))
  if (names.length < 2 || !hasNumbers) {
    return <div className={`${panel} text-sm text-text-muted`}>Not enough ranked games between the top Avatars for matchups this period.</div>
  }
  return (
    <>
      <div className={`${panel} overflow-x-auto`}>
        <table className="border-separate [border-spacing:3px] text-sm tabular-nums min-w-[520px]">
          <thead>
            <tr>
              <th />
              {names.map((n) => (
                <th key={`${n.avatar}|${n.elements}`} className="text-xs font-medium text-text-muted px-1.5 py-1 text-center">
                  vs {n.avatar}<div><ElementPair pair={n.elements} /></div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {names.map((n, i) => (
              <tr key={`${n.avatar}|${n.elements}`}>
                <th className="text-xs font-medium text-text-muted px-1.5 py-1 text-left whitespace-nowrap">
                  {n.avatar} <ElementPair pair={n.elements} />
                </th>
                {names.map((_, j) => {
                  const c = cells[i]?.[j]
                  const v = c?.winRate ?? null
                  return (
                    <td key={j} className="text-center px-1.5 py-2 rounded font-mono" style={cellStyle(v)}
                        title={c ? `${c.games} games` : undefined}>
                      {v == null ? '—' : `${v}%`}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {callouts.length > 0 && (
        <div className="grid gap-3 mt-3 grid-cols-[repeat(auto-fit,minmax(min(100%,230px),1fr))]">
          {callouts.map((c) => (
            <div key={c.title} className="border-l-[3px] border-secondary pl-3 py-1">
              <b className="block text-sm">{c.title}</b>
              <span className="text-sm text-text-muted">{c.text}</span>
            </div>
          ))}
        </div>
      )}
    </>
  )
}

function Tournaments({ events }) {
  if (!events?.length) {
    return <div className={`${panel} text-sm text-text-muted`}>No Top 8 events were added for this period.</div>
  }
  return (
    <div className={`${panel} grid`}>
      {events.map((e) => (
        <div key={e.folder} className="grid grid-cols-[1fr_auto] gap-2.5 items-center py-2.5 border-b border-border last:border-0">
          <div className="min-w-0">
            <div className="font-semibold">{e.name}</div>
            <div className="text-sm text-text-muted">
              {e.players ? `${e.players} decks · ` : ''}{e.date}
              {e.winnerAvatar && <> · {e.winnerAvatar} <ElementPair pair={e.winnerElements} /> won</>}
            </div>
          </div>
          <Link to={`/top-8/${encodeURIComponent(e.folder)}`} className="text-primary text-sm hover:underline">Top 8 lists</Link>
        </div>
      ))}
    </div>
  )
}

function DeckToTry({ deck }) {
  if (!deck) return <div className={`${panel} text-sm text-text-muted`}>No public Top 8 list this period.</div>
  return (
    <div className={panel}>
      <p className="text-xs uppercase tracking-wider text-text-muted mb-2.5">
        {deck.avatar} · <ElementPair pair={deck.elements} />
      </p>
      <p className="font-semibold">{deck.deckName || `${deck.avatar} deck`}</p>
      <p className="text-sm text-text-muted mb-3">
        {ordinal(deck.placement)} place{deck.player ? ` by ${deck.player}` : ''}, {deck.event}
      </p>
      <div className="flex gap-2 flex-wrap">
        <TryDeckButton deckId={deck.deckId} />
        <Link to={`/deck-rec/${encodeURIComponent(deck.deckId)}`}
              className="text-sm px-4 py-2 rounded border border-border hover:border-secondary">
          View list
        </Link>
      </div>
    </div>
  )
}

function ordinal(n) {
  const s = ['th', 'st', 'nd', 'rd'], v = n % 100
  return n + (s[(v - 20) % 10] || s[v] || s[0])
}

function EmailSignup() {
  const [email, setEmail] = useState('')
  const [state, setState] = useState({ status: 'idle', message: '' })
  const submit = async (e) => {
    e.preventDefault()
    setState({ status: 'busy', message: '' })
    try {
      const res = await subscribeMetaReport(email.trim())
      setState({
        status: 'done',
        message: res.status === 'subscribed'
          ? "You're already on the list."
          : 'Check your inbox and click the link to confirm.',
      })
    } catch (err) {
      setState({ status: 'error', message: err.message || 'Something went wrong. Try again.' })
    }
  }
  return (
    <div className={`${panel} flex flex-wrap gap-3 items-end justify-between`}>
      <div className="min-w-0">
        <p className="font-semibold">Get each report by email</p>
        <p className="text-sm text-text-muted">Twice a month. Unsubscribe from any email in one click.</p>
      </div>
      {state.status === 'done' ? (
        <p className="text-sm text-secondary" role="status">{state.message}</p>
      ) : (
        <form onSubmit={submit} className="flex flex-wrap gap-2 items-center">
          <label htmlFor="meta-email" className="sr-only">Email address</label>
          <input
            id="meta-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className="bg-bg-dark border border-border rounded px-3 py-2 text-sm min-w-0 w-64 max-w-full"
          />
          <button type="submit" disabled={state.status === 'busy'}
                  className="bg-secondary hover:bg-secondary/80 text-black font-medium text-sm px-4 py-2 rounded disabled:opacity-60">
            {state.status === 'busy' ? 'Sending…' : 'Sign up'}
          </button>
          {state.status === 'error' && <p className="text-sm text-accent-red w-full" role="alert">{state.message}</p>}
        </form>
      )}
    </div>
  )
}

function discordSummary(report) {
  const lines = [`**Summit Meta Report** (${report.period?.label})`]
  ;(report.story || []).forEach((s, i) => lines.push(`${i + 1}. ${s.headline}`))
  lines.push(new URL(`/meta-report/${report.slug}`, window.location.origin).toString())
  return lines.join('\n')
}

export default function MetaReport() {
  const { slug } = useParams()
  const navigate = useNavigate()
  const [reports, setReports] = useState(null)
  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)
  const [copied, setCopied] = useState(false)

  usePageTitle(report ? `Meta Report: ${report.period?.label}` : 'Meta Report')

  useEffect(() => {
    listMetaReports()
      .then((res) => setReports(res.reports || []))
      .catch(() => setReports([]))
  }, [])

  const current = slug || reports?.[0]?.slug

  useEffect(() => {
    if (!current) return
    let cancelled = false
    setError(null)
    getMetaReport(current)
      .then((res) => { if (!cancelled) setReport(res) })
      .catch((err) => { if (!cancelled) { setReport(null); setError(err) } })
    return () => { cancelled = true }
  }, [current])

  const copySummary = useCallback(async () => {
    if (!report) return
    try {
      await navigator.clipboard.writeText(discordSummary(report))
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      window.prompt('Copy this summary:', discordSummary(report))
    }
  }, [report])

  const archetypes = report?.ranked?.archetypes || []
  const loading = reports === null || (current && !report && !error)

  return (
    <div className="max-w-6xl mx-auto">
      <header className="pt-2 pb-3">
        <h1 className="font-display text-secondary text-3xl md:text-4xl">Meta Report</h1>
        <p className="text-text-muted mt-1 max-w-prose">
          What the Summit is playing and winning with. A new report comes out on the 1st and 16th of each month.
        </p>
      </header>

      {reports && reports.length > 0 && (
        <div className="md:sticky md:top-16 z-20 bg-bg-base/95 backdrop-blur-sm border border-border rounded-lg px-4 py-2.5">
          <div className="flex flex-wrap gap-x-4 gap-y-2 items-center">
            <div>
              <label htmlFor="meta-period" className="block text-[11px] uppercase tracking-wider text-text-muted mb-0.5">Report</label>
              <select
                id="meta-period"
                value={current || ''}
                onChange={(e) => navigate(`/meta-report/${e.target.value}`)}
                className="bg-bg-surface border border-border rounded px-3 py-2 text-sm max-w-full"
              >
                {reports.map((r) => (
                  <option key={r.slug} value={r.slug}>{`${r.publishLabel} report · covers ${r.label}`}</option>
                ))}
              </select>
            </div>
            {report && (
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-text-muted flex-1 min-w-[200px]">
                <span><b className="text-text-primary tabular-nums">{(report.ranked?.rankedGames || 0).toLocaleString()}</b> ranked games</span>
                <span><b className="text-text-primary">{report.tournaments?.events?.length || 0}</b> Top 8 events</span>
              </div>
            )}
            {report && (
              <div className="flex gap-2 flex-wrap">
                <ShareLinkButton
                  path={`/meta-report/${report.slug}`}
                  nativeShare
                  shareTitle={`Summit Meta Report: ${report.period?.label}`}
                  shareText={report.story?.[0]?.headline}
                  hint="Share this report"
                  className="bg-secondary hover:bg-secondary/80 text-black font-medium text-sm px-4 py-2"
                />
                <button type="button" onClick={copySummary}
                        className="text-sm px-4 py-2 rounded border border-border hover:border-secondary">
                  {copied ? 'Copied' : 'Copy for Discord'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {loading ? (
        <Spinner className="py-20" />
      ) : !reports?.length ? (
        <div className={`${panel} mt-6 text-text-muted`}>The first Meta Report hasn&apos;t been published yet. Check back on the 1st or 16th.</div>
      ) : error ? (
        <div className={`${panel} mt-6 text-text-muted`}>
          {error.status === 404 ? "That report doesn't exist." : "Couldn't load this report. Try again in a moment."}
        </div>
      ) : (
        <div className="grid gap-9 mt-6">
          <Section title="The story this period">
            <div className={panel}><Story story={report.story} /></div>
          </Section>

          <div className="grid gap-5 grid-cols-[repeat(auto-fit,minmax(min(100%,460px),1fr))]">
            <Section title="Tiers" sub="Each Avatar, placed by win rate and how much it's played in ranked. Arrows show the move since the last report.">
              {archetypes.length ? <Tiers archetypes={archetypes} /> : <div className={`${panel} text-sm text-text-muted`}>Not enough ranked games this period.</div>}
            </Section>
            <Section title="Meta map" sub="Play rate across, win rate up. Top right is the deck to beat; top left is the sleeper nobody's on yet.">
              <MetaMap archetypes={archetypes} />
            </Section>
          </div>

          <Section title="Staples and spotlights" sub={`The cards everyone runs, plus three spotlights that change every report, from Play Sorcery Online's ranked games. Win rates need ${report.cards?.minGames || 20}+ games.${report.cards?.mode === 'top' ? '' : ' Rising and Falling compare with the last report.'}`}>
            <Cards cards={report.cards} />
          </Section>

          <Section title="What beats what" sub={`The six most-played Avatars, row against column, in Summit ranked games. Totals only; cells under ${report.ranked?.matchups?.minGames || 10} games stay blank.`}>
            <Matchups matchups={report.ranked?.matchups} />
          </Section>

          <div className="grid gap-5 grid-cols-[repeat(auto-fit,minmax(min(100%,460px),1fr))]">
            <Section title="Tournament corner" sub="Top 8 events from this period. Deck lists come from the Top 8 page only.">
              <Tournaments events={report.tournaments?.events} />
            </Section>
            <Section title="Deck to try" sub="A public Top 8 list from an archetype on the rise, ready to test on Play Sorcery Online.">
              <DeckToTry deck={report.tournaments?.deckToTry} />
            </Section>
          </div>

          <EmailSignup />

          <Section title="How this report is made">
            <ul className={`${panel} text-sm text-text-muted grid gap-1.5 list-disc pl-8`}>
              <li>Each report covers half a month and comes out one month later, the same delay as the ranked card data on Card Win Rates. The report on the 1st covers the previous month&apos;s 1st to 15th; the report on the 16th covers the 16th to month end.</li>
              <li>Ranked games count toward totals only. No ranked deck lists or player names appear in a report.</li>
              <li>Deck lists come only from public Top 8 events.</li>
              <li>Small samples are hidden: archetypes need 10 games, matchups 20 and the sleeper pick 50.</li>
            </ul>
          </Section>
        </div>
      )}
    </div>
  )
}
