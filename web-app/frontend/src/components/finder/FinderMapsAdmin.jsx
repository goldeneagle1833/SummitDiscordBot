import { useState } from 'react'
import HallMap from '@/components/finder/HallMap'
import {
  createFinderMap, deleteFinderMap, updateFinderMap, uploadFinderMapImage,
} from '@/api/eventFinder'

const ZONES = [
  ['America/New_York', 'Eastern'],
  ['America/Chicago', 'Central'],
  ['America/Denver', 'Mountain'],
  ['America/Phoenix', 'Arizona'],
  ['America/Los_Angeles', 'Pacific'],
  ['Europe/London', 'UK'],
  ['Europe/Berlin', 'Central Europe'],
]

const BLANK = {
  name: '', image_url: null, start_date: '', end_date: '',
  daily_start: '08:00', daily_end: '20:00', timezone: 'America/New_York', spots: [],
}

// Admin: set up an event's hall map, dates, hours and quick spots.
export default function FinderMapsAdmin({ maps, onChange }) {
  const [form, setForm] = useState(null) // null = closed; {id?} = editing
  const [placing, setPlacing] = useState(null) // index of spot being placed
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))
  const setSpot = (i, patch) => setForm((f) => ({
    ...f, spots: f.spots.map((s, j) => (j === i ? { ...s, ...patch } : s)),
  }))

  const upload = async (file) => {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      set('image_url', await uploadFinderMapImage(file))
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    const { id, ...fields } = form
    const body = {
      name: fields.name, image_url: fields.image_url, start_date: fields.start_date,
      end_date: fields.end_date, daily_start: fields.daily_start, daily_end: fields.daily_end,
      timezone: fields.timezone, spots: fields.spots.filter((s) => s.label.trim()),
    }
    try {
      if (id) await updateFinderMap(id, body)
      else await createFinderMap(body)
      setForm(null)
      setPlacing(null)
      onChange()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (m) => {
    if (!window.confirm(`Delete the ${m.name} map? Everyone sharing on it is switched off.`)) return
    await deleteFinderMap(m.id).catch((e) => setError(e.message))
    onChange()
  }

  const input = 'bg-bg-elevated border border-border rounded px-3 py-2 text-text w-full'

  return (
    <section className="bg-bg-surface border border-dashed border-border rounded-lg p-4 sm:p-5">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xl font-display text-secondary">Event maps <span className="text-xs text-text-muted font-sans">(admins only)</span></h2>
        {!form && (
          <button type="button" onClick={() => setForm({ ...BLANK })} className="text-primary hover:underline text-sm">
            + New event map
          </button>
        )}
      </div>
      {error && <p className="text-accent-red text-sm mt-2">{error}</p>}

      {!form && (
        <ul className="divide-y divide-border mt-2">
          {maps.length === 0 && <li className="py-2 text-text-muted text-sm">No event maps yet.</li>}
          {maps.map((m) => (
            <li key={m.id} className="py-2 flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-text">{m.name}</p>
                <p className="text-xs text-text-muted">
                  {m.start_date} to {m.end_date} · {m.daily_start} to {m.daily_end} · {m.image_url ? 'map uploaded' : 'no map image yet'}
                </p>
              </div>
              <div className="flex gap-3 text-sm">
                <button type="button" onClick={() => setForm({ ...BLANK, ...m })} className="text-primary hover:underline">Edit</button>
                <button type="button" onClick={() => remove(m)} className="text-text-muted hover:text-accent-red">Delete</button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {form && (
        <form onSubmit={submit} className="mt-3 space-y-3">
          <label className="block text-sm">
            <span className="text-text-muted">Event name</span>
            <input className={input} value={form.name} onChange={(e) => set('name', e.target.value)} placeholder="Avatar of the Realm" required />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="block text-sm">
              <span className="text-text-muted">First day</span>
              <input type="date" className={input} value={form.start_date} onChange={(e) => set('start_date', e.target.value)} required />
            </label>
            <label className="block text-sm">
              <span className="text-text-muted">Last day</span>
              <input type="date" className={input} value={form.end_date} onChange={(e) => set('end_date', e.target.value)} required />
            </label>
            <label className="block text-sm">
              <span className="text-text-muted">Show spots from</span>
              <input type="time" className={input} value={form.daily_start} onChange={(e) => set('daily_start', e.target.value)} />
            </label>
            <label className="block text-sm">
              <span className="text-text-muted">Until</span>
              <input type="time" className={input} value={form.daily_end} onChange={(e) => set('daily_end', e.target.value)} />
            </label>
          </div>
          <label className="block text-sm">
            <span className="text-text-muted">Venue time zone</span>
            <select className={input} value={form.timezone} onChange={(e) => set('timezone', e.target.value)}>
              {ZONES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>

          <div className="text-sm">
            <span className="text-text-muted">Hall map image (JPG, PNG or WEBP; screenshot a PDF first)</span>
            <input type="file" accept="image/png,image/jpeg,image/webp" className="block mt-1 text-text-muted" onChange={(e) => upload(e.target.files?.[0])} />
          </div>

          <div>
            <p className="text-sm text-text-muted mb-1">
              Quick spots players can tap (Booth, Stage, Food...).
              {placing != null ? ` Now tap the map to place "${form.spots[placing]?.label || 'this spot'}".` : ' Use "Place" then tap the map.'}
            </p>
            <div className="space-y-2">
              {form.spots.map((s, i) => (
                <div key={i} className="flex gap-2 items-center">
                  <input className={input} value={s.label} maxLength={60} onChange={(e) => setSpot(i, { label: e.target.value })} placeholder="Summit booth" />
                  <button type="button" onClick={() => setPlacing(placing === i ? null : i)}
                    className={`text-sm whitespace-nowrap ${placing === i ? 'text-secondary' : 'text-primary'} hover:underline`}>
                    {placing === i ? 'Tap map…' : s.x != null ? 'Move' : 'Place'}
                  </button>
                  <button type="button" onClick={() => setForm((f) => ({ ...f, spots: f.spots.filter((_, j) => j !== i) }))}
                    className="text-sm text-text-muted hover:text-accent-red" aria-label="Remove spot">✕</button>
                </div>
              ))}
            </div>
            <button type="button" onClick={() => set('spots', [...form.spots, { label: '', x: null, y: null }])}
              className="text-sm text-primary hover:underline mt-2">+ Add spot</button>
          </div>

          <HallMap
            map={form}
            spots={form.spots.filter((s) => s.label)}
            onPick={placing != null ? (x, y) => { setSpot(placing, { x, y }); setPlacing(null) } : undefined}
          />

          <div className="flex gap-3">
            <button type="submit" disabled={busy} className="px-4 py-2 rounded bg-primary text-bg-dark font-semibold disabled:opacity-50">
              {form.id ? 'Save changes' : 'Create event map'}
            </button>
            <button type="button" onClick={() => { setForm(null); setPlacing(null) }} className="px-4 py-2 text-text-muted hover:text-text">Cancel</button>
          </div>
        </form>
      )}
    </section>
  )
}
