import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import usePageTitle from '@/hooks/usePageTitle'
import { searchPlayers } from '@/api/players'
import {
  getPaperFinishesReview,
  linkPaperName,
  rejectPaperName,
  unlinkPaperName,
  assignPaperResult,
  clearPaperResult,
  setPaperEventBadges,
} from '@/api/paperFinishes'
import { resetPaperFinishesCache } from '@/components/player/PaperFinishes'

/**
 * Admin page for the paper tournament badges: how every top cut result on
 * the Top 8 page matched a Summit player, with the calls an admin can make.
 */

const STATUS_TEXT = {
  auto: 'Same name',
  linked: 'Linked by admin',
  assigned: 'Given by admin',
  nobody: 'Not a Summit player',
  shared_uploader: 'Deck posted by someone else',
  ambiguous: 'Name shared by several players',
  short_name: 'Name too short to link on its own',
  unmatched: 'No Summit player',
}

const NEEDS_LOOK = new Set(['shared_uploader', 'ambiguous', 'short_name'])

const TABS = [
  { id: 'look', label: 'Needs a look' },
  { id: 'matched', label: 'Badges given' },
  { id: 'none', label: 'No match' },
  { id: 'events', label: 'Events' },
]

function tabFor(row) {
  if (['auto', 'linked', 'assigned'].includes(row.status)) return 'matched'
  if (NEEDS_LOOK.has(row.status) || (row.status === 'unmatched' && row.candidates.length)) return 'look'
  return 'none'
}

function PlayerPicker({ onPick, label = 'Pick player' }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const timer = useRef(null)

  useEffect(() => {
    clearTimeout(timer.current)
    if (q.trim().length < 2) {
      setResults([])
      return undefined
    }
    timer.current = setTimeout(() => {
      searchPlayers(q.trim())
        .then((res) => setResults(res.players || []))
        .catch(() => setResults([]))
    }, 250)
    return () => clearTimeout(timer.current)
  }, [q])

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="px-2.5 py-1 rounded-lg border border-border text-sm hover:border-secondary">
        {label}
      </button>
    )
  }
  return (
    <div className="relative">
      <input
        autoFocus
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => e.key === 'Escape' && setOpen(false)}
        placeholder="Search Summit players..."
        className="h-9 w-56 rounded-lg border border-border bg-bg-raised px-3 text-sm text-text-primary"
      />
      {results.length > 0 && (
        <ul className="absolute z-20 mt-1 w-64 max-h-64 overflow-auto rounded-lg border border-border bg-bg-surface shadow-lg">
          {results.map((p) => (
            <li key={p.user_id}>
              <button
                type="button"
                onClick={() => {
                  setOpen(false)
                  setQ('')
                  onPick(p)
                }}
                className="w-full text-left px-3 py-2 text-sm hover:bg-white/5"
              >
                {p.display_name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function PaperName({ row }) {
  const name = row.names[0] || row.posted_by || 'Unknown'
  return (
    <div className="min-w-0">
      <div className="font-semibold text-text-primary break-words">{name}</div>
      <div className="text-xs text-text-muted">
        {row.name_source === 'registration' ? 'Registered name' : `Deck posted by ${row.posted_by || 'unknown'}`}
      </div>
    </div>
  )
}

function ResultRow({ row, act }) {
  const paperName = row.names[0] || ''
  const btn = 'px-2.5 py-1 rounded-lg border text-sm'
  return (
    <li className="grid grid-cols-1 md:grid-cols-[7rem_minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1.6fr)] gap-x-4 gap-y-2 px-4 py-3 items-center">
      <div className="text-sm">
        <strong className="text-text-primary">{row.label}</strong>
        <div className="text-xs text-text-muted">{row.avatar}</div>
      </div>
      <div className="min-w-0">
        <Link to={`/top-8/${encodeURIComponent(row.folder)}`} className="text-sm text-text-primary hover:text-secondary">
          {row.event}
        </Link>
        <div className="text-xs text-text-muted">{row.event_date_display}</div>
      </div>
      <PaperName row={row} />
      <div className="flex flex-wrap items-center gap-2">
        {row.player && (
          <span className="text-sm">
            <Link to={`/player/${row.player.user_id}`} className="font-semibold text-secondary hover:underline">
              {row.player.name}
            </Link>
            <span className="text-text-muted"> · {STATUS_TEXT[row.status]}</span>
            {!row.earns_badge && <span className="text-text-muted"> (event switched off)</span>}
          </span>
        )}
        {!row.player && <span className="text-sm text-text-muted">{STATUS_TEXT[row.status]}</span>}

        {row.status === 'auto' && (
          <button type="button" className={`${btn} border-accent-red/50 hover:border-accent-red`} onClick={() => act(() => rejectPaperName(paperName, row.player.user_id))}>
            Not them
          </button>
        )}
        {row.status === 'linked' && (
          <button type="button" className={`${btn} border-border hover:border-accent-red`} onClick={() => act(() => unlinkPaperName(row.name_key, row.player.user_id))}>
            Unlink
          </button>
        )}
        {(row.status === 'assigned' || row.status === 'nobody') && (
          <button type="button" className={`${btn} border-border hover:border-accent-red`} onClick={() => act(() => clearPaperResult(row.folder, row.deck_id))}>
            Undo
          </button>
        )}

        {!row.player && row.status !== 'nobody' && (
          <>
            {row.status !== 'shared_uploader' && row.candidates.map((c) => (
              <span key={c.user_id} className="inline-flex items-center gap-1">
                <button type="button" className={`${btn} border-secondary/50 hover:border-secondary`} onClick={() => act(() => linkPaperName(paperName, c.user_id))}>
                  Link {c.name}
                </button>
                <button type="button" title={`${paperName} is not ${c.name}`} className={`${btn} border-border hover:border-accent-red`} onClick={() => act(() => rejectPaperName(paperName, c.user_id))}>
                  ✕
                </button>
              </span>
            ))}
            {row.status === 'shared_uploader' ? (
              <PlayerPicker label="Give to player" onPick={(p) => act(() => assignPaperResult(row.folder, row.deck_id, p.user_id))} />
            ) : (
              paperName && <PlayerPicker label="Link to player" onPick={(p) => act(() => linkPaperName(paperName, p.user_id))} />
            )}
            {row.deck_id && (
              <button type="button" className={`${btn} border-border hover:border-text-muted text-text-muted`} onClick={() => act(() => assignPaperResult(row.folder, row.deck_id, ''))}>
                Nobody
              </button>
            )}
          </>
        )}
      </div>
    </li>
  )
}

export default function PaperBadges() {
  usePageTitle('Paper Tournament Badges')
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState('look')
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    getPaperFinishesReview()
      .then((res) => {
        setData(res)
        setError(null)
      })
      .catch((e) => setError(e.message))
  }, [])

  useEffect(load, [load])

  const act = async (call) => {
    setBusy(true)
    try {
      await call()
      resetPaperFinishesCache()
      load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const groups = useMemo(() => {
    const out = { look: [], matched: [], none: [] }
    for (const row of data?.results || []) out[tabFor(row)].push(row)
    // Name calls first; decks an organiser posted for everyone come last.
    out.look.sort((a, b) => (a.status === 'shared_uploader') - (b.status === 'shared_uploader'))
    return out
  }, [data])

  if (error && !data) return <p className="text-accent-red">{error}</p>
  if (!data) return <p className="text-text-muted">Loading results...</p>

  const given = groups.matched.filter((r) => r.earns_badge).length

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div>
        <Link to="/admin" className="text-sm text-text-muted hover:text-text-primary">← Admin</Link>
        <h1 className="text-2xl font-display text-secondary mt-1">Paper Tournament Badges</h1>
        <p className="text-sm text-text-muted mt-1 max-w-3xl">
          Every top cut on the Top 8 page, matched to Summit players by name. A matched player gets a badge on their
          profile (Winner, Finalist, Top 4, Top 8) from the order of the event's Top 8 list, so reorder an event there
          if a finish is wrong.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-2 sm:gap-3">
        {[
          [given, 'Badges on profiles'],
          [groups.look.length, 'Need a look'],
          [groups.none.length, 'No Summit match'],
        ].map(([value, label]) => (
          <div key={label} className="bg-bg-surface border border-border rounded-xl p-3 sm:p-4">
            <div className="text-2xl sm:text-3xl font-bold text-text-primary tabular-nums">{value}</div>
            <div className="text-xs sm:text-sm text-text-muted">{label}</div>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap gap-2" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 h-10 rounded-lg text-sm font-semibold border ${tab === t.id ? 'bg-secondary text-black border-secondary' : 'border-border text-text-primary hover:border-secondary'}`}
          >
            {t.label}
            {t.id !== 'events' && <span className="ml-1.5 opacity-70">{groups[t.id].length}</span>}
          </button>
        ))}
      </div>

      {error && <p className="text-accent-red text-sm">{error}</p>}

      {tab !== 'events' && (
        <ul className={`bg-bg-surface border border-border rounded-xl divide-y divide-border ${busy ? 'opacity-60' : ''}`}>
          {groups[tab].length === 0 && <li className="px-4 py-6 text-sm text-text-muted">Nothing here.</li>}
          {groups[tab].map((row) => (
            <ResultRow key={`${row.folder}-${row.place}`} row={row} act={act} />
          ))}
        </ul>
      )}

      {tab === 'events' && (
        <ul className="bg-bg-surface border border-border rounded-xl divide-y divide-border">
          {data.events.map((ev) => (
            <li key={ev.folder} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <div className="flex-1 min-w-[14rem]">
                <Link to={`/top-8/${encodeURIComponent(ev.folder)}`} className="font-semibold text-text-primary hover:text-secondary">
                  {ev.name}
                </Link>
                <div className="text-xs text-text-muted">
                  {[ev.event_date_display, ev.has_pairings ? 'Registered names' : 'Deck owner names', !ev.default_on && 'Off by default (Summit or TTS event)'].filter(Boolean).join(' · ')}
                </div>
              </div>
              <label className="inline-flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={ev.awards_badges}
                  disabled={busy}
                  onChange={(e) => act(() => setPaperEventBadges(ev.folder, e.target.checked))}
                  className="h-4 w-4 accent-secondary"
                />
                Gives badges
              </label>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
