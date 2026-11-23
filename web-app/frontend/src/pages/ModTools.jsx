import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { get, post, del } from '@/api/client'
import { useAuth } from '@/context/AuthContext'
import usePageTitle from '@/hooks/usePageTitle'
import Spinner from '@/components/ui/Spinner'
import ModerationActions, { moderationSummary } from '@/components/admin/ModerationActions'
import { REASON_LABELS } from '@/components/admin/PlayerReportsSection'

// Mod Tools: player reports, player lookup and timeouts / bans for
// moderators. Shows report and moderation data only (no profile links);
// the API enforces the same limits (routes/api/mod_tools.py).

const ENDPOINT = '/api/mod/action'
const PER_PAGE = 25

const SORTS = [
  { key: 'newest', label: 'Newest first' },
  { key: 'oldest', label: 'Oldest first' },
  { key: 'most_reported', label: 'Most reported player' },
  { key: 'name', label: 'Player name (A-Z)' },
]
const STATES = [
  { key: 'all', label: 'All reports' },
  { key: 'open', label: 'Needs action' },
  { key: 'actioned', label: 'Action taken' },
]

const inputCls = 'bg-bg-elevated border border-border rounded px-2 py-1.5 text-sm text-text-primary'

function formatDate(value, withTime = false) {
  if (!value) return '-'
  const d = new Date(value.includes('T') ? value : value.replace(' ', 'T') + 'Z')
  if (isNaN(d.getTime())) return value
  return withTime
    ? d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
    : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

function reasonText(reasons) {
  return reasons?.length
    ? `Reported after a match: ${reasons.map(r => REASON_LABELS[r] ?? r).join('; ')}`
    : 'Reported after a match'
}

function StatusChips({ status }) {
  if (!status) return null
  const chips = []
  if (status.banned) chips.push(['Banned', 'bg-accent-red/15 text-accent-red'])
  if (status.timed_out_until) chips.push([`Timed out until ${formatDate(status.timed_out_until, true)}`, 'bg-amber-500/15 text-amber-400'])
  if (status.pairing_block) {
    const until = status.pairing_block.expires_at ? ` until ${formatDate(status.pairing_block.expires_at, true)}` : ' (lifetime)'
    chips.push([`Pairing blocked${until}`, 'bg-amber-500/15 text-amber-400'])
  }
  if (!chips.length) return null
  return (
    <div className="flex flex-wrap gap-1">
      {chips.map(([text, cls]) => (
        <span key={text} className={`text-[11px] px-2 py-0.5 rounded-full ${cls}`}>{text}</span>
      ))}
    </div>
  )
}

function Pager({ page, total, onPage, loading }) {
  const pages = Math.max(1, Math.ceil(total / PER_PAGE))
  if (pages <= 1) return null
  return (
    <div className="flex items-center gap-3 text-sm">
      <button onClick={() => onPage(page - 1)} disabled={page <= 1 || loading}
        className="px-3 py-1 border border-border rounded hover:bg-bg-elevated disabled:opacity-40">Previous</button>
      <span className="text-xs text-text-muted">Page {page} of {pages}</span>
      <button onClick={() => onPage(page + 1)} disabled={page >= pages || loading}
        className="px-3 py-1 border border-border rounded hover:bg-bg-elevated disabled:opacity-40">Next</button>
    </div>
  )
}

function ReportsTab({ focus, onClearFocus }) {
  const [sort, setSort] = useState('newest')
  const [state, setState] = useState('all')
  const [reason, setReason] = useState('')
  const [q, setQ] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState({ entries: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Wait a moment after typing before searching
  useEffect(() => {
    const t = setTimeout(() => setSearch(q.trim()), 300)
    return () => clearTimeout(t)
  }, [q])
  useEffect(() => { setPage(1) }, [sort, state, reason, search, focus])

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    const params = new URLSearchParams({ sort, state, limit: PER_PAGE, offset: (page - 1) * PER_PAGE })
    if (reason) params.set('reason', reason)
    if (search) params.set('q', search)
    if (focus) params.set('reported_id', focus.user_id)
    get(`/api/mod/reports?${params}`)
      .then(d => setData({ entries: d.entries ?? [], total: d.total ?? 0 }))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [sort, state, reason, search, page, focus])
  useEffect(() => { load() }, [load])

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
        <input
          type="search" value={q} onChange={e => setQ(e.target.value)}
          placeholder="Search name or Discord ID" aria-label="Search reports" className={inputCls}
        />
        <select value={sort} onChange={e => setSort(e.target.value)} aria-label="Sort reports" className={inputCls}>
          {SORTS.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
        </select>
        <select value={state} onChange={e => setState(e.target.value)} aria-label="Show" className={inputCls}>
          {STATES.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
        </select>
        <select value={reason} onChange={e => setReason(e.target.value)} aria-label="Reason" className={inputCls}>
          <option value="">Any reason</option>
          {Object.entries(REASON_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>

      {focus && (
        <div className="flex items-center justify-between gap-2 bg-brand-blue/10 border border-brand-blue/40 rounded px-3 py-2 text-sm">
          <span>Reports on <strong>{focus.name}</strong></span>
          <button onClick={() => onClearFocus()} className="text-xs underline text-text-muted hover:text-text-primary">Show everyone</button>
        </div>
      )}

      <div className="text-xs text-text-muted">{loading ? 'Loading...' : `${data.total} report${data.total === 1 ? '' : 's'}`}</div>

      {loading ? (
        <div className="flex justify-center py-8"><Spinner /></div>
      ) : error ? (
        <div className="text-sm text-accent-red">{error}</div>
      ) : data.entries.length === 0 ? (
        <div className="text-sm text-text-muted bg-bg-raised border border-border rounded-lg px-4 py-6">No reports match.</div>
      ) : (
        <ul className="space-y-3">
          {data.entries.map(e => (
            <li key={e.id} className="bg-bg-raised border border-border rounded-lg p-4 space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link to={`/mod-tools/player/${encodeURIComponent(e.reported_id)}`}
                      className="font-semibold text-text-primary break-all hover:underline">{e.reported_name}</Link>
                    {e.reports_against > 1 && (
                      <span className="text-[11px] px-2 py-0.5 rounded-full bg-accent-red/15 text-accent-red">
                        {e.reports_against} reports
                      </span>
                    )}
                    <span className={`text-[11px] px-2 py-0.5 rounded-full ${e.actioned ? 'bg-emerald-500/15 text-emerald-400' : 'bg-bg-elevated text-text-muted'}`}>
                      {e.actioned ? 'Action taken' : 'Needs action'}
                    </span>
                  </div>
                  <div className="text-xs text-text-muted font-mono">{e.reported_id}</div>
                </div>
                <div className="text-xs text-text-muted whitespace-nowrap">{formatDate(e.created_at)}</div>
              </div>

              <div className="grid gap-3 md:grid-cols-2 text-sm">
                <div>
                  <div className="text-xs text-text-muted mb-1">What happened</div>
                  {e.reasons?.length ? (
                    <ul className="list-disc pl-4 space-y-0.5 text-text-primary">
                      {e.reasons.map(r => <li key={r}>{REASON_LABELS[r] ?? r}</li>)}
                    </ul>
                  ) : <span className="opacity-40">-</span>}
                </div>
                <div>
                  <div className="text-xs text-text-muted mb-1">What they wrote</div>
                  {e.details
                    ? <p className="whitespace-pre-wrap break-words text-text-primary">{e.details}</p>
                    : <span className="opacity-40">-</span>}
                </div>
              </div>

              <div className="text-xs text-text-muted">
                Reported by {e.reporter_name}
                {e.match_type && <span className="capitalize"> · {e.match_type} match</span>}
                {e.source === 'sorcery-online' && <span> · via Play Sorcery Online</span>}
              </div>

              <StatusChips status={e.status} />
              <div className="flex flex-wrap items-end justify-between gap-2 border-t border-border/60 pt-3">
                <ModerationActions
                  userId={e.reported_id} userName={e.reported_name} canModerate={e.can_moderate}
                  moderation={e.moderation} status={e.status} sourceKind="report" sourceRef={e.id}
                  playerReason={reasonText(e.reasons)} endpoint={ENDPOINT}
                />
                <Link to={`/mod-tools/player/${encodeURIComponent(e.reported_id)}`}
                  className="text-xs underline text-text-muted hover:text-text-primary">Mod page</Link>
                {!focus && e.reports_against > 1 && (
                  <button onClick={() => onClearFocus({ user_id: e.reported_id, name: e.reported_name })}
                    className="text-xs underline text-text-muted hover:text-text-primary">
                    See all {e.reports_against} reports on them
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      <Pager page={page} total={data.total} onPage={setPage} loading={loading} />
    </div>
  )
}

function PlayersTab({ onShowReports }) {
  const [q, setQ] = useState('')
  const [players, setPlayers] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const run = (e) => {
    e?.preventDefault()
    if (q.trim().length < 2) return
    setLoading(true)
    setError(null)
    get(`/api/mod/players?q=${encodeURIComponent(q.trim())}`)
      .then(d => setPlayers(d.players ?? []))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }

  return (
    <div className="space-y-4">
      <form onSubmit={run} className="flex gap-2">
        <input type="search" value={q} onChange={e => setQ(e.target.value)}
          placeholder="Player name or Discord ID" aria-label="Find a player" className={`${inputCls} flex-1`} />
        <button type="submit" disabled={q.trim().length < 2 || loading}
          className="px-4 py-1.5 text-sm rounded bg-brand-blue text-white hover:bg-brand-blue-light disabled:opacity-50">
          Search
        </button>
      </form>
      {loading ? <div className="flex justify-center py-8"><Spinner /></div>
        : error ? <div className="text-sm text-accent-red">{error}</div>
        : players === null ? <p className="text-sm text-text-muted">Look someone up to see their reports and time them out or ban them, even if nobody has reported them.</p>
        : players.length === 0 ? <div className="text-sm text-text-muted">Nobody found.</div>
        : (
          <ul className="space-y-3">
            {players.map(p => (
              <li key={p.user_id} className="bg-bg-raised border border-border rounded-lg p-4 space-y-3">
                <div>
                  <Link to={`/mod-tools/player/${encodeURIComponent(p.user_id)}`}
                    className="font-semibold text-text-primary break-all hover:underline">{p.name}</Link>
                  <div className="text-xs text-text-muted font-mono">{p.user_id}</div>
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">
                  <span><strong className="text-text-primary">{p.reports_against}</strong> {p.reports_against === 1 ? 'report' : 'reports'} against</span>
                  <span><strong className="text-text-primary">{p.reports_filed}</strong> {p.reports_filed === 1 ? 'report' : 'reports'} filed</span>
                  <span>Blocked by <strong className="text-text-primary">{p.blocked_by}</strong></span>
                </div>
                <StatusChips status={p.status} />
                <div className="flex flex-wrap items-end justify-between gap-2 border-t border-border/60 pt-3">
                  <ModerationActions userId={p.user_id} userName={p.name} canModerate={p.can_moderate}
                    moderation={p.moderation} status={p.status} playerReason="" endpoint={ENDPOINT} />
                  <Link to={`/mod-tools/player/${encodeURIComponent(p.user_id)}`}
                    className="text-xs underline text-text-muted hover:text-text-primary">Mod page</Link>
                  {p.reports_against > 0 && (
                    <button onClick={() => onShowReports({ user_id: p.user_id, name: p.name })}
                      className="text-xs underline text-text-muted hover:text-text-primary">View reports</button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
    </div>
  )
}

function ActionsTab() {
  const [page, setPage] = useState(1)
  const [data, setData] = useState({ entries: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  useEffect(() => {
    setLoading(true)
    get(`/api/mod/actions?limit=${PER_PAGE}&offset=${(page - 1) * PER_PAGE}`)
      .then(d => setData({ entries: d.entries ?? [], total: d.total ?? 0 }))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [page])

  if (loading) return <div className="flex justify-center py-8"><Spinner /></div>
  if (error) return <div className="text-sm text-accent-red">{error}</div>
  return (
    <div className="space-y-3">
      {data.entries.length === 0 ? <div className="text-sm text-text-muted">No actions yet.</div> : (
        <ul className="bg-bg-raised border border-border rounded-lg divide-y divide-border/60">
          {data.entries.map(a => (
            <li key={a.id} className="px-4 py-3 text-sm space-y-0.5">
              <div className="flex flex-wrap justify-between gap-2">
                <span className="font-medium text-text-primary break-all">{a.target_name || a.target_id}</span>
                <span className="text-xs text-text-muted">{formatDate(a.created_at, true)}</span>
              </div>
              <div className="text-xs text-text-muted">{moderationSummary(a)}</div>
              {a.reason && <div className="text-xs text-text-muted italic break-words">"{a.reason}"</div>}
            </li>
          ))}
        </ul>
      )}
      <Pager page={page} total={data.total} onPage={setPage} loading={loading} />
    </div>
  )
}

function ModeratorsTab() {
  const [mods, setMods] = useState([])
  const [id, setId] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [confirmRemove, setConfirmRemove] = useState(null)

  const load = useCallback(() => {
    get('/api/mod/moderators').then(d => setMods(d.moderators ?? [])).catch(e => setError(e.message))
  }, [])
  useEffect(() => { load() }, [load])

  const add = (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    post('/api/mod/moderators', { discord_id: id.trim() })
      .then(() => { setId(''); load() })
      .catch(err => setError(err.message))
      .finally(() => setBusy(false))
  }
  const remove = (uid) => {
    del(`/api/mod/moderators/${uid}`).then(() => { setConfirmRemove(null); load() }).catch(err => setError(err.message))
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-text-muted">
        Moderators see this page only: player reports, player search, and timeouts, bans and pairing blocks.
        They can't open any other admin page. Find a Discord ID by right-clicking someone in Discord and choosing Copy User ID.
      </p>
      <form onSubmit={add} className="flex gap-2">
        <input value={id} onChange={e => setId(e.target.value.replace(/\D/g, ''))} inputMode="numeric"
          placeholder="Discord ID" aria-label="Discord ID" className={`${inputCls} flex-1 font-mono`} />
        <button type="submit" disabled={busy || id.length < 15}
          className="px-4 py-1.5 text-sm rounded bg-brand-blue text-white hover:bg-brand-blue-light disabled:opacity-50">
          Add moderator
        </button>
      </form>
      {error && <div className="text-sm text-accent-red">{error}</div>}
      {mods.length === 0 ? <div className="text-sm text-text-muted">No moderators yet.</div> : (
        <ul className="bg-bg-raised border border-border rounded-lg divide-y divide-border/60">
          {mods.map(m => (
            <li key={m.discord_user_id} className="px-4 py-3 flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="text-sm text-text-primary break-all">{m.name}</div>
                <div className="text-xs text-text-muted font-mono">{m.discord_user_id}</div>
                <div className="text-xs text-text-muted">Added {formatDate(m.added_at)}{m.added_by_name ? ` by ${m.added_by_name}` : ''}</div>
              </div>
              {confirmRemove === m.discord_user_id ? (
                <div className="flex gap-2">
                  <button onClick={() => setConfirmRemove(null)} className="px-2 py-1 text-xs border border-border rounded">Cancel</button>
                  <button onClick={() => remove(m.discord_user_id)} className="px-2 py-1 text-xs rounded bg-accent-red text-white">Remove</button>
                </div>
              ) : (
                <button onClick={() => setConfirmRemove(m.discord_user_id)}
                  className="px-2 py-1 text-xs border border-border rounded hover:bg-bg-elevated">Remove</button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function ModTools() {
  usePageTitle('Mod Tools')
  const { user } = useAuth()
  const [tab, setTab] = useState('reports')
  const [focus, setFocus] = useState(null)

  const tabs = [
    { key: 'reports', label: 'Reports' },
    { key: 'players', label: 'Find a player' },
    { key: 'actions', label: 'Recent actions' },
    ...(user?.is_admin ? [{ key: 'moderators', label: 'Moderators' }] : []),
  ]

  const showReports = (player) => { setFocus(player); setTab('reports') }

  return (
    <div className="space-y-5 max-w-4xl mx-auto">
      <div>
        <h1 className="text-2xl font-display text-secondary">Mod Tools</h1>
        <p className="text-sm text-text-muted">Player reports, timeouts, bans and pairing blocks.</p>
      </div>
      <div role="tablist" aria-label="Mod Tools" className="flex flex-wrap gap-1 bg-bg-surface border border-border rounded-lg p-1 w-fit max-w-full">
        {tabs.map(t => (
          <button key={t.key} role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}
            className={`px-3 py-1.5 rounded text-sm font-semibold transition-colors ${
              tab === t.key ? 'bg-bg-elevated text-secondary' : 'text-text-muted hover:text-text'}`}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'reports' && <ReportsTab focus={focus} onClearFocus={(p) => setFocus(p ?? null)} />}
      {tab === 'players' && <PlayersTab onShowReports={showReports} />}
      {tab === 'actions' && <ActionsTab />}
      {tab === 'moderators' && user?.is_admin && <ModeratorsTab />}
    </div>
  )
}
