import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import {
  adminListBrackets,
  adminGetBracket,
  adminGetSeedPool,
  adminSyncTickets,
  adminCreateBracket,
  adminSetEntrants,
  adminShuffleSeeds,
  adminMoveEntrant,
  adminPublishBracket,
  adminUnpublishBracket,
  adminDeleteBracket,
} from '@/api/brackets'
import { searchUsers } from '@/api/admin'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

const INPUT = 'w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm'
const LABEL = 'block text-xs uppercase tracking-wider text-text-muted mb-1'

const SOURCES = [
  { value: 'ticket_holders', label: 'Ticket holders' },
  { value: 'overall', label: 'Everyone on the ladder' },
  { value: 'manual', label: 'Empty (add players myself)' },
]

function CreateForm({ onCreated }) {
  const [form, setForm] = useState({ name: '', size: 16, source: 'ticket_holders' })
  const [pool, setPool] = useState(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)

  const loadPool = useCallback(() => {
    if (form.source === 'manual') {
      setPool(null)
      return
    }
    adminGetSeedPool(form.source).then(setPool).catch(() => setPool(null))
  }, [form.source])

  useEffect(() => {
    loadPool()
  }, [loadPool])

  async function syncTickets() {
    setMessage(null)
    try {
      const res = await adminSyncTickets()
      setMessage({ type: 'ok', text: `Synced ${res.count} ticket holders from Discord.` })
      loadPool()
    } catch (e) {
      setMessage({ type: 'error', text: e.message })
    }
  }

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setMessage(null)
    try {
      const res = await adminCreateBracket({
        name: form.name,
        size: Number(form.size),
        source: form.source,
      })
      onCreated(res.slug)
      setForm((f) => ({ ...f, name: '' }))
      setMessage({
        type: 'ok',
        text: res.short_by
          ? `Created with ${res.entrant_count} players — ${res.short_by} short of ${res.requested_size}. Add the rest by hand.`
          : `Created with ${res.entrant_count} seeded players.`,
      })
    } catch (e) {
      setMessage({ type: 'error', text: e.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="bg-bg-surface border border-border rounded-lg p-5 space-y-4">
      <h2 className="text-lg font-display">New bracket</h2>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="sm:col-span-2">
          <label className={LABEL} htmlFor="bracket-name">Name</label>
          <input
            id="bracket-name"
            className={INPUT}
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            placeholder="Season 7 Postseason"
            required
          />
        </div>
        <div>
          <label className={LABEL} htmlFor="bracket-size">Starting players</label>
          <input
            id="bracket-size"
            type="number"
            min="2"
            max="256"
            className={INPUT}
            value={form.size}
            onChange={(e) => setForm((f) => ({ ...f, size: e.target.value }))}
          />
        </div>
        <div className="sm:col-span-3">
          <label className={LABEL} htmlFor="bracket-source">Seed from</label>
          <select
            id="bracket-source"
            className={INPUT}
            value={form.source}
            onChange={(e) => setForm((f) => ({ ...f, source: e.target.value }))}
          >
            {SOURCES.map((source) => (
              <option key={source.value} value={source.value}>{source.label}</option>
            ))}
          </select>
        </div>
      </div>

      {pool && (
        <p className="text-xs text-text-muted">
          {pool.players.length} player{pool.players.length === 1 ? '' : 's'} available
          {pool.event?.event_name ? ` from ${pool.event.event_name}` : ' (lifetime ELO)'}.
          {form.source === 'ticket_holders' && !pool.ticket_filter_applied && (
            <>
              {' '}
              <span className="text-amber-400">
                No ticket-holder roster synced, so nothing is being filtered.
              </span>{' '}
              <button type="button" onClick={syncTickets} className="text-secondary hover:underline">
                Sync from Discord
              </button>
            </>
          )}
          {form.source === 'ticket_holders' && pool.ticket_filter_applied && (
            <>
              {' '}Filtered to {pool.ticket_roster_size} ticket holders.{' '}
              <button type="button" onClick={syncTickets} className="text-secondary hover:underline">
                Re-sync
              </button>
            </>
          )}
        </p>
      )}

      {message && (
        <p className={`text-sm ${message.type === 'ok' ? 'text-accent-green' : 'text-accent-red'}`}>
          {message.text}
        </p>
      )}

      <button
        type="submit"
        disabled={busy}
        className="px-4 py-2 rounded bg-secondary text-black text-sm font-medium disabled:opacity-50"
      >
        {busy ? 'Creating…' : 'Create draft'}
      </button>
    </form>
  )
}

function AddPlayer({ onAdd }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])

  async function run(e) {
    e.preventDefault()
    if (query.trim().length < 2) return
    try {
      const res = await searchUsers(query.trim())
      setResults(res.users || [])
    } catch {
      setResults([])
    }
  }

  return (
    <div className="space-y-2">
      <form onSubmit={run} className="flex gap-2">
        <input
          className={`${INPUT} py-1`}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Add a player by name"
          aria-label="Add a player by name"
        />
        <button type="submit" className="px-3 py-1 rounded border border-border text-sm">
          Search
        </button>
      </form>
      {results.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {results.map((user) => (
            <li key={`${user.provider}-${user.user_id}`}>
              <button
                onClick={() => {
                  onAdd({ user_id: user.user_id, display_name: user.display_name })
                  setResults([])
                  setQuery('')
                }}
                className="px-2 py-1 rounded bg-bg-raised border border-border text-xs hover:border-secondary"
              >
                + {user.display_name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function SeedEditor({ slug, entrants, onChanged }) {
  const [busy, setBusy] = useState(false)

  async function run(action) {
    setBusy(true)
    try {
      await action()
      await onChanged()
    } finally {
      setBusy(false)
    }
  }

  const move = (seed, toSeed) => run(() => adminMoveEntrant(slug, seed, toSeed))
  const remove = (seed) =>
    run(() =>
      adminSetEntrants(
        slug,
        entrants.filter((e) => e.seed !== seed),
      ),
    )
  const add = (player) => run(() => adminSetEntrants(slug, [...entrants, player]))

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold">Seeding ({entrants.length})</h3>
        <button
          onClick={() => run(() => adminShuffleSeeds(slug))}
          disabled={busy}
          className="px-3 py-1 rounded border border-border text-xs disabled:opacity-50"
        >
          Shuffle
        </button>
      </div>

      <ol className="space-y-1">
        {entrants.map((entrant, index) => (
          <li
            key={`${entrant.seed}-${entrant.user_id || entrant.display_name}`}
            className="flex items-center gap-2 bg-bg-raised border border-border rounded px-2 py-1 text-sm"
          >
            <span className="w-6 text-xs text-text-muted">{entrant.seed}</span>
            <span className="flex-1 truncate">
              {entrant.display_name}
              {entrant.elo ? <span className="text-text-muted text-xs"> · {entrant.elo}</span> : null}
              {entrant.is_ticket_holder ? (
                <span className="text-amber-400 text-xs" title="Ticket holder"> · 🎟</span>
              ) : null}
            </span>
            <button
              onClick={() => move(entrant.seed, entrant.seed - 1)}
              disabled={busy || index === 0}
              className="px-1 text-text-muted hover:text-text-primary disabled:opacity-30"
              aria-label={`Move ${entrant.display_name} up`}
            >
              ↑
            </button>
            <button
              onClick={() => move(entrant.seed, entrant.seed + 1)}
              disabled={busy || index === entrants.length - 1}
              className="px-1 text-text-muted hover:text-text-primary disabled:opacity-30"
              aria-label={`Move ${entrant.display_name} down`}
            >
              ↓
            </button>
            <button
              onClick={() => remove(entrant.seed)}
              disabled={busy}
              className="px-1 text-accent-red hover:opacity-80 disabled:opacity-30"
              aria-label={`Remove ${entrant.display_name}`}
            >
              ✕
            </button>
          </li>
        ))}
      </ol>

      <AddPlayer onAdd={add} />
    </div>
  )
}

function BracketRow({ bracket, onChanged }) {
  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState(null)

  const loadDetail = useCallback(async () => {
    try {
      setDetail(await adminGetBracket(bracket.slug))
    } catch {
      setDetail(null)
    }
  }, [bracket.slug])

  useEffect(() => {
    if (open && !detail) loadDetail()
  }, [open, detail, loadDetail])

  async function act(action) {
    setError(null)
    try {
      await action()
      setDetail(null)
      await onChanged()
      if (open) await loadDetail()
    } catch (e) {
      setError(e.message)
    }
  }

  const isDraft = bracket.status === 'draft'

  return (
    <div className="bg-bg-surface border border-border rounded-lg">
      <div className="px-4 py-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-medium">
            {bracket.name}
            <span className="text-text-muted text-sm"> · {bracket.entrant_count} players</span>
          </p>
          <p className="text-xs text-text-muted">
            {isDraft ? 'Draft — not visible to players' : `Published as /brackets/${bracket.slug}`}
            {bracket.champion ? ` · won by ${bracket.champion.display_name}` : ''}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {isDraft ? (
            <button
              onClick={() => act(() => adminPublishBracket(bracket.slug))}
              className="px-3 py-1 rounded bg-secondary text-black text-xs font-medium"
            >
              Publish
            </button>
          ) : (
            <>
              <Link
                to={`/brackets/${bracket.slug}`}
                className="px-3 py-1 rounded border border-border text-xs"
              >
                View
              </Link>
              <button
                onClick={() => {
                  if (window.confirm('Unpublish? The current results will be discarded.')) {
                    act(() => adminUnpublishBracket(bracket.slug))
                  }
                }}
                className="px-3 py-1 rounded border border-border text-xs"
              >
                Unpublish
              </button>
            </>
          )}
          {isDraft && (
            <button
              onClick={() => setOpen((v) => !v)}
              className="px-3 py-1 rounded border border-border text-xs"
            >
              {open ? 'Close' : 'Edit seeds'}
            </button>
          )}
          <button
            onClick={() => {
              if (window.confirm(`Delete "${bracket.name}"?`)) {
                act(() => adminDeleteBracket(bracket.slug))
              }
            }}
            className="px-3 py-1 rounded text-xs text-accent-red"
          >
            Delete
          </button>
        </div>
      </div>

      {error && <p className="px-4 pb-3 text-sm text-accent-red">{error}</p>}

      {open && (
        <div className="px-4 pb-4 border-t border-border pt-4">
          {!detail && <Spinner />}
          {detail && (
            <SeedEditor
              slug={bracket.slug}
              entrants={detail.entrants}
              onChanged={async () => {
                await loadDetail()
                await onChanged()
              }}
            />
          )}
        </div>
      )}
    </div>
  )
}

export default function BracketsAdmin() {
  usePageTitle('Brackets Admin')
  const [brackets, setBrackets] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      const res = await adminListBrackets()
      setBrackets(res.brackets || [])
    } catch {
      setError('Could not load brackets.')
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 space-y-5">
      <div className="flex items-baseline justify-between gap-3">
        <h1 className="text-2xl font-display">Brackets</h1>
        <Link to="/brackets" className="text-sm text-secondary hover:underline">
          Public page
        </Link>
      </div>

      <CreateForm onCreated={load} />

      {error && <p className="text-accent-red text-sm">{error}</p>}
      {!brackets && !error && <Spinner />}
      {brackets?.length === 0 && <p className="text-text-muted text-sm">No brackets yet.</p>}
      {brackets?.map((bracket) => (
        <BracketRow key={bracket.slug} bracket={bracket} onChanged={load} />
      ))}
    </div>
  )
}
