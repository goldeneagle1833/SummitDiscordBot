import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import usePageTitle from '@/hooks/usePageTitle'
import PlayerPicker from '@/components/admin/PlayerPicker'
import {
  getPaperFinishesReview,
  linkPaperName,
  rejectPaperName,
  unlinkPaperName,
  assignPaperResult,
  clearPaperResult,
  setPaperEventBadges,
  addManualPaperResult,
  updateManualPaperResult,
  deleteManualPaperResult,
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
  { id: 'manual', label: 'Added by hand' },
]

const PLACES = [
  [1, 'Winner'],
  [2, 'Finalist'],
  [4, 'Top 4'],
  [8, 'Top 8'],
  [16, 'Top 16'],
  [32, 'Top 32'],
  [64, 'Top 64'],
]

const EMPTY_FORM = { player: null, event: '', event_date: '', place: 1, avatar: '' }

function tabFor(row) {
  if (['auto', 'linked', 'assigned'].includes(row.status)) return 'matched'
  if (NEEDS_LOOK.has(row.status) || (row.status === 'unmatched' && row.candidates.length)) return 'look'
  return 'none'
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

/**
 * Results for events that are not on the Top 8 page: pick a player, type the
 * event, pick a placement (Winner unless changed). Each shows on the
 * player's profile like an imported finish, and can be edited or removed.
 */
function ManualResults({ rows, act, busy }) {
  const [form, setForm] = useState(EMPTY_FORM)
  const [editing, setEditing] = useState(null)
  const [formError, setFormError] = useState(null)
  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }))
  const input = 'h-10 w-full rounded-lg border border-border bg-bg-raised px-3 text-sm text-text-primary'

  const reset = () => {
    setForm(EMPTY_FORM)
    setEditing(null)
    setFormError(null)
  }

  const save = async (e) => {
    e.preventDefault()
    if (!form.player) return setFormError('Pick a player first.')
    if (!form.event.trim()) return setFormError('Type the event name.')
    const body = {
      user_id: form.player.user_id,
      event: form.event.trim(),
      event_date: form.event_date || null,
      place: Number(form.place),
      avatar: form.avatar.trim() || null,
    }
    const ok = await act(() => (editing ? updateManualPaperResult(editing, body) : addManualPaperResult(body)))
    if (ok) reset()
  }

  const edit = (row) => {
    setEditing(row.manual_id)
    setFormError(null)
    setForm({
      player: row.player,
      event: row.event,
      event_date: row.event_date || '',
      place: row.place,
      avatar: row.avatar || '',
    })
  }

  return (
    <div className="space-y-4">
      <form onSubmit={save} className="bg-bg-surface border border-border rounded-xl p-4 space-y-3" aria-label="Add a result by hand">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-semibold text-text-primary">{editing ? 'Edit result' : 'Add a result by hand'}</h2>
          <p className="text-xs text-text-muted">For events that are not on the Top 8 page. Shows on the player's profile like the others.</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1.6fr)_10rem_9rem_minmax(0,1fr)] gap-3 items-end">
          <div className="space-y-1">
            <span className="block text-xs text-text-muted">Player</span>
            <div className="flex flex-wrap items-center gap-2 min-h-10">
              {form.player && <strong className="text-secondary text-sm" data-testid="manual-player">{form.player.name}</strong>}
              <PlayerPicker
                label={form.player ? 'Change' : 'Choose player'}
                onPick={(p) => setForm((f) => ({ ...f, player: { user_id: p.user_id, name: p.display_name } }))}
              />
            </div>
          </div>
          <label className="space-y-1">
            <span className="block text-xs text-text-muted">Event name</span>
            <input value={form.event} onChange={set('event')} maxLength={120} placeholder="e.g. Store Championship" className={input} />
          </label>
          <label className="space-y-1">
            <span className="block text-xs text-text-muted">Date</span>
            <input type="date" value={form.event_date} onChange={set('event_date')} className={input} />
          </label>
          <label className="space-y-1">
            <span className="block text-xs text-text-muted">Placement</span>
            <select value={form.place} onChange={set('place')} className={input}>
              {PLACES.map(([place, label]) => (
                <option key={place} value={place}>{label}</option>
              ))}
            </select>
          </label>
          <label className="space-y-1">
            <span className="block text-xs text-text-muted">Avatar (optional)</span>
            <input value={form.avatar} onChange={set('avatar')} maxLength={60} placeholder="e.g. Druid" className={input} />
          </label>
        </div>
        {formError && <p className="text-accent-red text-sm">{formError}</p>}
        <div className="flex gap-2">
          <button type="submit" disabled={busy} className="px-4 h-10 rounded-lg text-sm font-semibold bg-secondary text-black disabled:opacity-60">
            {editing ? 'Save changes' : 'Add result'}
          </button>
          {(editing || form.player || form.event) && (
            <button type="button" onClick={reset} className="px-4 h-10 rounded-lg text-sm border border-border hover:border-text-muted">
              Cancel
            </button>
          )}
        </div>
      </form>

      <ul className={`bg-bg-surface border border-border rounded-xl divide-y divide-border ${busy ? 'opacity-60' : ''}`}>
        {rows.length === 0 && <li className="px-4 py-6 text-sm text-text-muted">No results added by hand yet.</li>}
        {rows.map((row) => (
          <li key={row.manual_id} className="grid grid-cols-1 md:grid-cols-[7rem_minmax(0,1.6fr)_minmax(0,1fr)_auto] gap-x-4 gap-y-2 px-4 py-3 items-center">
            <div className="text-sm">
              <strong className="text-text-primary">{row.label}</strong>
              <div className="text-xs text-text-muted">{row.avatar}</div>
            </div>
            <div className="min-w-0">
              <div className="text-sm text-text-primary break-words">{row.event}</div>
              <div className="text-xs text-text-muted">{row.event_date_display || 'No date'}</div>
            </div>
            <div className="text-sm min-w-0">
              <Link to={`/player/${row.player.user_id}`} className="font-semibold text-secondary hover:underline">
                {row.player.name}
              </Link>
              {row.set_by && <div className="text-xs text-text-muted">Added by {row.set_by}</div>}
            </div>
            <div className="flex gap-2">
              <button type="button" className="px-2.5 py-1 rounded-lg border border-border hover:border-secondary text-sm" onClick={() => edit(row)}>
                Edit
              </button>
              <button
                type="button"
                className="px-2.5 py-1 rounded-lg border border-border hover:border-accent-red text-sm"
                onClick={() => {
                  if (window.confirm(`Remove ${row.label} · ${row.event} from ${row.player.name}?`)) {
                    act(() => deleteManualPaperResult(row.manual_id))
                    if (editing === row.manual_id) reset()
                  }
                }}
              >
                Remove
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function PaperBadges() {
  usePageTitle('Paper Tournament Badges')
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState('look')
  const [busy, setBusy] = useState(false)
  const [playerQuery, setPlayerQuery] = useState('')
  const [eventQuery, setEventQuery] = useState('')

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
      setError(null)
      return true
    } catch (e) {
      setError(e.message)
      return false
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

  // The search boxes narrow every tab: player against the paper names, who
  // posted the deck and the Summit player (matched or suggested); event
  // against the event's name.
  const filtered = useMemo(() => {
    const player = playerQuery.trim().toLowerCase()
    const event = eventQuery.trim().toLowerCase()
    const eventHit = (name) => !event || (name || '').toLowerCase().includes(event)
    const playerHit = (row) =>
      !player ||
      [...row.names, row.posted_by, row.player?.name, ...row.candidates.map((c) => c.name)]
        .some((n) => (n || '').toLowerCase().includes(player))
    const keep = (rows) => rows.filter((row) => eventHit(row.event) && playerHit(row))
    return {
      look: keep(groups.look),
      matched: keep(groups.matched),
      none: keep(groups.none),
      events: (data?.events || []).filter((ev) => eventHit(ev.name)),
      manual: (data?.manual || []).filter((m) => eventHit(m.event) && (!player || (m.player?.name || '').toLowerCase().includes(player))),
    }
  }, [groups, data, playerQuery, eventQuery])
  const searching = Boolean(playerQuery.trim() || eventQuery.trim())

  if (error && !data) return <p className="text-accent-red">{error}</p>
  if (!data) return <p className="text-text-muted">Loading results...</p>

  const given = groups.matched.filter((r) => r.earns_badge).length

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div>
        <Link to="/admin" className="text-sm text-text-muted hover:text-text-primary">← Admin</Link>
        <div className="flex flex-wrap items-center justify-between gap-3 mt-1">
          <h1 className="text-2xl font-display text-secondary">Paper Tournament Badges</h1>
          <button
            type="button"
            onClick={() => setTab('manual')}
            className="px-4 h-10 rounded-lg text-sm font-semibold border border-secondary text-secondary hover:bg-secondary hover:text-black"
          >
            + Add a result by hand
          </button>
        </div>
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

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-3">
        <input
          type="search"
          value={playerQuery}
          onChange={(e) => setPlayerQuery(e.target.value)}
          placeholder="Search player name..."
          aria-label="Search player name"
          className="h-10 rounded-lg border border-border bg-bg-raised px-3 text-sm text-text-primary"
        />
        <input
          type="search"
          value={eventQuery}
          onChange={(e) => setEventQuery(e.target.value)}
          placeholder="Search event name..."
          aria-label="Search event name"
          className="h-10 rounded-lg border border-border bg-bg-raised px-3 text-sm text-text-primary"
        />
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
            {((t.id !== 'events' && t.id !== 'manual') || searching || (t.id === 'manual' && filtered.manual.length > 0)) && <span className="ml-1.5 opacity-70">{filtered[t.id].length}</span>}
          </button>
        ))}
      </div>

      {error && <p className="text-accent-red text-sm">{error}</p>}

      {tab !== 'events' && tab !== 'manual' && (
        <ul className={`bg-bg-surface border border-border rounded-xl divide-y divide-border ${busy ? 'opacity-60' : ''}`}>
          {filtered[tab].length === 0 && (
            <li className="px-4 py-6 text-sm text-text-muted">{searching ? 'Nothing matches your search.' : 'Nothing here.'}</li>
          )}
          {filtered[tab].map((row) => (
            <ResultRow key={`${row.folder}-${row.place}`} row={row} act={act} />
          ))}
        </ul>
      )}

      {tab === 'manual' && <ManualResults rows={filtered.manual} act={act} busy={busy} />}

      {tab === 'events' && (
        <ul className="bg-bg-surface border border-border rounded-xl divide-y divide-border">
          {filtered.events.length === 0 && (
            <li className="px-4 py-6 text-sm text-text-muted">Nothing matches your search.</li>
          )}
          {filtered.events.map((ev) => (
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
