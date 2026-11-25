import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'
import { get, post } from '@/api/client'
import usePageTitle from '@/hooks/usePageTitle'
import { useAuth } from '@/context/AuthContext'
import Spinner from '@/components/ui/Spinner'
import ModerationActions, { moderationSummary } from '@/components/admin/ModerationActions'
import { REASON_LABELS } from '@/components/admin/PlayerReportsSection'

// Mod page for one player: every report, block, timeout/ban/pairing block,
// mod note, group chat (with its saved transcript) and repeat-offender flag,
// newest first. Moderation data only (routes/api/mod_tools.py).

const ENDPOINT = '/api/mod/action'

const KINDS = [
  { key: 'all', label: 'Everything' },
  { key: 'report', label: 'Reports' },
  { key: 'block', label: 'Blocks' },
  { key: 'action', label: 'Actions' },
  { key: 'note', label: 'Notes' },
  { key: 'chat', label: 'Group chats' },
  { key: 'flag', label: 'Flags' },
]

const KIND_STYLE = {
  report: ['Report', 'bg-orange-500/15 text-orange-400'],
  block: ['Block', 'bg-accent-red/15 text-accent-red'],
  action: ['Action', 'bg-brand-blue/15 text-brand-blue-light'],
  note: ['Note', 'bg-bg-elevated text-text-primary'],
  chat: ['Group chat', 'bg-indigo-500/15 text-indigo-300'],
  flag: ['Heads-up', 'bg-amber-500/15 text-amber-400'],
}

function toDate(value) {
  if (!value) return null
  const d = new Date(value.includes('T') ? value : value.replace(' ', 'T') + 'Z')
  return isNaN(d.getTime()) ? null : d
}

function formatDate(value) {
  const d = toDate(value)
  return d ? d.toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '-'
}

function reasonText(reasons) {
  return reasons?.length
    ? `Reported after a match: ${reasons.map(r => REASON_LABELS[r] ?? r).join('; ')}`
    : 'Reported after a match'
}

function timeline(data) {
  const items = []
  for (const r of data.reports) items.push({ kind: 'report', at: r.created_at, key: `r${r.id}`, r })
  for (const b of data.blocks) items.push({ kind: 'block', at: b.created_at, key: `b${b.user_id}${b.created_at}`, b })
  for (const a of data.actions) items.push({ kind: 'action', at: a.created_at, key: `a${a.id}`, a })
  for (const n of data.notes) items.push({ kind: 'note', at: n.created_at, key: `n${n.id}`, n })
  for (const c of data.chats) items.push({ kind: 'chat', at: c.created_at, key: `c${c.id}`, c })
  for (const f of data.flags) items.push({ kind: 'flag', at: f.created_at, key: `f${f.created_at}`, f })
  return items.sort((x, y) => (toDate(y.at)?.getTime() ?? 0) - (toDate(x.at)?.getTime() ?? 0))
}

function Transcript({ chat }) {
  const [open, setOpen] = useState(false)
  if (!chat.transcript) {
    return <div className="text-xs text-text-muted">{chat.closed_at ? 'No messages were saved.' : 'Still open in Discord. The conversation is saved here when a moderator presses Close chat.'}</div>
  }
  return (
    <div className="space-y-2">
      <button onClick={() => setOpen(o => !o)} className="text-xs underline text-text-muted hover:text-text-primary">
        {open ? 'Hide conversation' : `Show conversation (${chat.message_count ?? '?'} messages)`}
      </button>
      {open && (
        <pre className="whitespace-pre-wrap break-words text-xs bg-bg-elevated border border-border rounded p-3 max-h-96 overflow-y-auto font-sans text-text-primary">
          {chat.transcript}
        </pre>
      )}
    </div>
  )
}

function Item({ item }) {
  const [label, cls] = KIND_STYLE[item.kind]
  let body = null
  if (item.kind === 'report') {
    const r = item.r
    body = (
      <>
        <div className="text-sm text-text-primary">
          {r.reasons?.length ? r.reasons.map(x => REASON_LABELS[x] ?? x).join(', ') : 'Reported'}
        </div>
        {r.details && <p className="text-sm whitespace-pre-wrap break-words text-text-muted">"{r.details}"</p>}
        <div className="text-xs text-text-muted">
          Report #{r.id} by {r.reporter_name}
          {r.match_type && <span className="capitalize"> · {r.match_type} match</span>}
          {r.source === 'sorcery-online' && <span> · via Play Sorcery Online</span>}
        </div>
      </>
    )
  } else if (item.kind === 'block') {
    body = (
      <>
        <div className="text-sm text-text-primary">Blocked by {item.b.blocker_name}</div>
        {item.b.reason && <p className="text-sm break-words text-text-muted">"{item.b.reason}"</p>}
      </>
    )
  } else if (item.kind === 'action') {
    body = (
      <>
        <div className="text-sm text-text-primary">{moderationSummary(item.a)}</div>
        {item.a.reason && <p className="text-sm break-words text-text-muted italic">"{item.a.reason}"</p>}
      </>
    )
  } else if (item.kind === 'note') {
    body = (
      <>
        <p className="text-sm whitespace-pre-wrap break-words text-text-primary">{item.n.note}</p>
        <div className="text-xs text-text-muted">by {item.n.by_name || 'a moderator'}</div>
      </>
    )
  } else if (item.kind === 'chat') {
    const c = item.c
    body = (
      <>
        <div className="text-sm text-text-primary">
          Opened by {c.opened_by_name || 'a moderator'}
          {c.source_kind === 'report' && c.source_ref ? ` from report #${c.source_ref}` : ''}
          {c.closed_at ? `, closed by ${c.closed_by_name || 'a moderator'} ${formatDate(c.closed_at)}` : ' · still open'}
        </div>
        <Transcript chat={c} />
      </>
    )
  } else {
    body = <div className="text-sm text-text-primary">The bot flagged them in the mod channel for repeated reports and blocks.</div>
  }
  return (
    <li className="bg-bg-raised border border-border rounded-lg p-4 space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className={`text-[11px] px-2 py-0.5 rounded-full ${cls}`}>{label}</span>
        <span className="text-xs text-text-muted">{formatDate(item.at)}</span>
      </div>
      {body}
    </li>
  )
}

function NoteBox({ userId, onSaved }) {
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const save = (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    post(`/api/mod/players/${encodeURIComponent(userId)}/notes`, { note: note.trim() })
      .then(() => { setNote(''); onSaved() })
      .catch(err => setError(err.message))
      .finally(() => setBusy(false))
  }
  return (
    <form onSubmit={save} className="bg-bg-raised border border-border rounded-lg p-4 space-y-2">
      <label htmlFor="mod-note" className="text-sm font-semibold text-text-primary">Add a mod note</label>
      <textarea id="mod-note" value={note} onChange={e => setNote(e.target.value)} rows={3} maxLength={1000}
        placeholder="Only moderators see notes. e.g. Talked to them in group chat, they apologised."
        className="w-full bg-bg-elevated border border-border rounded px-2 py-1.5 text-sm text-text-primary" />
      {error && <div className="text-sm text-accent-red">{error}</div>}
      <div className="flex justify-end">
        <button type="submit" disabled={busy || note.trim().length < 3}
          className="px-4 py-1.5 text-sm rounded bg-brand-blue text-white hover:bg-brand-blue-light disabled:opacity-50">
          Save note
        </button>
      </div>
    </form>
  )
}

function SendSummaryButton({ userId }) {
  const [state, setState] = useState('idle')
  const [error, setError] = useState(null)
  const send = () => {
    setState('busy')
    setError(null)
    post(`/api/mod/players/${encodeURIComponent(userId)}/send-summary`, {})
      .then(() => setState('sent'))
      .catch(err => { setError(err.message); setState('idle') })
  }
  return (
    <div className="space-y-1">
      <button onClick={send} disabled={state !== 'idle'}
        className="px-3 py-1.5 text-sm rounded bg-brand-blue text-white hover:bg-brand-blue-light disabled:opacity-60">
        {state === 'sent' ? 'Sent to the mod channel ✓' : state === 'busy' ? 'Sending...' : 'Send summary to mod channel'}
      </button>
      {state === 'sent' && <div className="text-xs text-text-muted">The bot posts it within 30 seconds, with Timeout, Ban, Pairing Block, Group chat and Note buttons.</div>}
      {error && <div className="text-xs text-accent-red">{error}</div>}
    </div>
  )
}

const FLIP_TEXT = { pending: 'Waiting for the bot', done: 'Flipped', error: 'Not changed' }

function MatchesSection({ userId, name }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [picked, setPicked] = useState(new Set())
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState(null)

  const load = useCallback(() => {
    get(`/api/mod/players/${encodeURIComponent(userId)}/matches`)
      .then(d => setData(d))
      .catch(e => setError(e.message))
  }, [userId])
  useEffect(() => { load() }, [load])

  if (error) return <div className="text-sm text-accent-red">{error}</div>
  if (!data) return <div className="flex justify-center py-6"><Spinner /></div>

  const flippable = data.matches.filter(m => m.flip?.status !== 'pending')
  const wins = flippable.filter(m => m.won)
  const toggle = (id) => setPicked(prev => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })
  const submit = () => {
    setBusy(true)
    post(`/api/mod/players/${encodeURIComponent(userId)}/flip-matches`, { match_ids: [...picked], confirm: true })
      .then(d => {
        setNotice(`${d.queued} match${d.queued === 1 ? '' : 'es'} sent to the bot. Refresh in a minute to see the result.`)
        setPicked(new Set())
        setConfirming(false)
        load()
      })
      .catch(err => setError(err.message))
      .finally(() => setBusy(false))
  }
  const pickedWins = data.matches.filter(m => picked.has(m.id) && m.won).length

  return (
    <div className="bg-bg-raised border border-border rounded-lg p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold text-text-primary">Matches this season</h2>
          <p className="text-xs text-text-muted">Admins only. Flipping gives the win to the other player and recalculates every later game for both, same as <code>!correct_match</code>.</p>
        </div>
        <button onClick={load} className="text-xs underline text-text-muted hover:text-text-primary">Refresh</button>
      </div>
      {notice && <div className="text-sm bg-emerald-500/10 border border-emerald-500/40 rounded px-3 py-2">{notice}</div>}
      {data.matches.length === 0 ? <div className="text-sm text-text-muted">No matches this season.</div> : (
        <>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => setPicked(new Set(wins.map(m => m.id)))} disabled={!wins.length}
              className="px-3 py-1 text-xs border border-border rounded hover:bg-bg-elevated disabled:opacity-40">
              Select all their wins ({wins.length})
            </button>
            <button onClick={() => setPicked(new Set())} disabled={!picked.size}
              className="px-3 py-1 text-xs border border-border rounded hover:bg-bg-elevated disabled:opacity-40">Clear</button>
            <button onClick={() => setConfirming(true)} disabled={!picked.size}
              className="px-3 py-1 text-xs rounded bg-accent-red text-white disabled:opacity-40">
              Flip {picked.size || ''} result{picked.size === 1 ? '' : 's'}
            </button>
          </div>
          <ul className="divide-y divide-border/60 border border-border rounded max-h-[28rem] overflow-y-auto">
            {data.matches.map(m => {
              const locked = m.flip?.status === 'pending'
              return (
                <li key={m.id} className="flex items-start gap-3 px-3 py-2 text-sm">
                  <input type="checkbox" className="mt-1" aria-label={`Match #${m.id}`}
                    checked={picked.has(m.id)} disabled={locked} onChange={() => toggle(m.id)} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`text-[11px] px-2 py-0.5 rounded-full ${m.won ? 'bg-emerald-500/15 text-emerald-400' : 'bg-bg-elevated text-text-muted'}`}>
                        {m.won ? 'Won' : 'Lost'}
                      </span>
                      <span className="text-text-primary break-all">vs {m.opponent_name || m.opponent_id}</span>
                    </div>
                    <div className="text-xs text-text-muted">
                      #{m.id} · {formatDate(m.timestamp)}
                      {m.match_type && <span className="capitalize"> · {m.match_type}</span>}
                      {m.avatar && <span> · {m.avatar}</span>}
                    </div>
                    {m.flip && (
                      <div className={`text-xs ${m.flip.status === 'error' ? 'text-accent-red' : 'text-text-muted'}`}>
                        {FLIP_TEXT[m.flip.status] ?? m.flip.status}{m.flip.result ? `: ${m.flip.result}` : ''}
                      </div>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        </>
      )}
      {confirming && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4" role="dialog" aria-modal="true">
          <div className="w-full max-w-md bg-bg-raised border border-border rounded-lg p-5 space-y-3 shadow-xl">
            <h3 className="text-base font-semibold text-text-primary">Flip {picked.size} match result{picked.size === 1 ? '' : 's'}?</h3>
            <p className="text-sm text-text-muted">
              {pickedWins} win{pickedWins === 1 ? '' : 's'} for {name} become losses and {picked.size - pickedWins} loss{picked.size - pickedWins === 1 ? '' : 'es'} become wins.
              Ratings for both players in each game, and every later game they played, are recalculated by the bot.
              Matches from an ended season can't be changed.
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setConfirming(false)} className="px-3 py-1.5 text-sm border border-border rounded">Cancel</button>
              <button onClick={submit} disabled={busy} className="px-3 py-1.5 text-sm rounded bg-accent-red text-white disabled:opacity-50">
                {busy ? 'Sending...' : 'Flip results'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function ModPlayer() {
  const { userId } = useParams()
  const { user } = useAuth()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [kind, setKind] = useState('all')
  usePageTitle(data?.player?.name ? `Mod: ${data.player.name}` : 'Mod Tools')

  const load = useCallback(() => {
    get(`/api/mod/players/${encodeURIComponent(userId)}/record`)
      .then(d => setData(d))
      .catch(e => setError(e.message))
  }, [userId])
  useEffect(() => { load() }, [load])

  const items = useMemo(() => (data ? timeline(data) : []), [data])
  const shown = kind === 'all' ? items : items.filter(i => i.kind === kind)

  if (error) return <div className="max-w-4xl mx-auto text-sm text-accent-red">{error}</div>
  if (!data) return <div className="flex justify-center py-12"><Spinner /></div>

  const p = data.player
  const counts = items.reduce((acc, i) => ({ ...acc, [i.kind]: (acc[i.kind] ?? 0) + 1 }), {})
  const lastReport = data.reports[0]

  return (
    <div className="space-y-5 max-w-4xl mx-auto">
      <Link to="/mod-tools" className="text-xs underline text-text-muted hover:text-text-primary">← Mod Tools</Link>
      <div className="bg-bg-raised border border-border rounded-lg p-4 space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-2xl font-display text-secondary break-all">{p.name}</h1>
            <div className="text-xs text-text-muted font-mono">{p.user_id}</div>
          </div>
          <SendSummaryButton userId={p.user_id} />
        </div>
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 text-center">
          {[['Reports', counts.report], ['Blocks', counts.block], ['Actions', counts.action],
            ['Notes', counts.note], ['Chats', counts.chat], ['Flags', counts.flag]].map(([l, n]) => (
            <div key={l} className="bg-bg-elevated rounded px-2 py-2">
              <div className="text-lg font-semibold text-text-primary">{n ?? 0}</div>
              <div className="text-[11px] text-text-muted">{l}</div>
            </div>
          ))}
        </div>
        <div className="text-xs text-text-muted">They have filed {data.reports_filed} report{data.reports_filed === 1 ? '' : 's'} themselves.</div>
        <div className="border-t border-border/60 pt-3">
          <ModerationActions userId={p.user_id} userName={p.name} canModerate={p.can_moderate}
            moderation={p.moderation} status={p.status}
            sourceKind={lastReport ? 'report' : undefined} sourceRef={lastReport?.id}
            playerReason={lastReport ? reasonText(lastReport.reasons) : ''} endpoint={ENDPOINT} />
        </div>
      </div>

      <NoteBox userId={p.user_id} onSaved={load} />

      {user?.is_admin && <MatchesSection userId={p.user_id} name={p.name} />}

      <div role="tablist" aria-label="Show" className="flex flex-wrap gap-1 bg-bg-surface border border-border rounded-lg p-1 w-fit max-w-full">
        {KINDS.map(k => (
          <button key={k.key} role="tab" aria-selected={kind === k.key} onClick={() => setKind(k.key)}
            className={`px-3 py-1.5 rounded text-sm font-semibold transition-colors ${
              kind === k.key ? 'bg-bg-elevated text-secondary' : 'text-text-muted hover:text-text'}`}>
            {k.label}{k.key !== 'all' && counts[k.key] ? ` (${counts[k.key]})` : ''}
          </button>
        ))}
      </div>

      {shown.length === 0
        ? <div className="text-sm text-text-muted bg-bg-raised border border-border rounded-lg px-4 py-6">Nothing here yet.</div>
        : <ul className="space-y-3">{shown.map(i => <Item key={i.key} item={i} />)}</ul>}
    </div>
  )
}
