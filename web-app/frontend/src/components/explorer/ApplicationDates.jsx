import { useState } from 'react'

const MONTH = { month: 'short', day: 'numeric', timeZone: 'UTC' }
const WEEKDAY = { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' }

const toDate = (iso) => new Date(`${iso}T00:00:00Z`)
const fmt = (iso, opts = MONTH) => toDate(iso).toLocaleDateString('en-US', opts)

/** "Sat, Apr 10", "Apr 10 – Apr 11", or the words we couldn't read. */
export function dateLabel(row) {
  if (!row.start_date) return `Couldn't read “${row.raw_text || ''}”`
  if (row.start_date === row.end_date) return fmt(row.start_date, WEEKDAY)
  return `${fmt(row.start_date)} – ${fmt(row.end_date)}`
}

// How sure the parser was, worded for the Council.
const CONFIDENCE = {
  high: { label: 'Exact', className: 'border-accent-green/40 text-accent-green' },
  medium: { label: 'Year assumed', className: 'border-sky-400/40 text-sky-300' },
  low: { label: 'Vague', className: 'border-amber-400/40 text-amber-300' },
  none: { label: 'Unreadable', className: 'border-accent-red/40 text-accent-red' },
}

const SOURCE = { applicant: 'Picked by applicant', admin: 'Set by the Council', parser: 'Read from their answer' }

function DateChip({ row }) {
  const style = CONFIDENCE[row.confidence] || CONFIDENCE.none
  const vague = row.source === 'parser' && row.precision !== 'day' && row.precision !== 'range'
  return (
    <li
      className={`inline-flex items-center gap-1.5 border rounded-full px-2.5 py-0.5 text-xs ${style.className}`}
      title={`${SOURCE[row.source] || ''}${row.raw_text ? ` from “${row.raw_text}”` : ''}`}
    >
      {row.confirmed_at && <span aria-label="Confirmed">✓</span>}
      <span>{dateLabel(row)}</span>
      {vague && row.start_date && <span className="text-text-muted">“{row.raw_text}”</span>}
      {!row.confirmed_at && row.source === 'parser' && (
        <span className="text-text-muted">· {style.label}</span>
      )}
    </li>
  )
}

const blankRows = (dates) => {
  const rows = (dates || [])
    .filter((d) => d.start_date)
    .slice(0, 3)
    .map((d) => ({ start: d.start_date, end: d.end_date === d.start_date ? '' : d.end_date }))
  while (rows.length < 3) rows.push({ start: '', end: '' })
  return rows
}

/**
 * The preferred dates read from an application, as chips a Council member
 * can confirm ("Looks right") or fix by hand. Fixed or confirmed dates are
 * never re-read from the applicant's text.
 */
export default function ApplicationDates({ dates, needsCheck, busy, onConfirm, onSave }) {
  const [editing, setEditing] = useState(false)
  const [rows, setRows] = useState(() => blankRows(dates))
  const confirmed = (dates || []).some((d) => d.confirmed_at)

  const startEditing = () => {
    setRows(blankRows(dates))
    setEditing(true)
  }
  const change = (i, key) => (e) =>
    setRows((list) => list.map((r, j) => (j === i ? { ...r, [key]: e.target.value } : r)))

  const save = async () => {
    const payload = rows.filter((r) => r.start).map((r) => ({ start: r.start, end: r.end || r.start }))
    const ok = await onSave(payload)
    if (ok !== false) setEditing(false)
  }

  return (
    <div className="space-y-2">
      {dates?.length ? (
        <ul className="flex flex-wrap gap-1.5" aria-label="Dates read from the application">
          {dates.map((row) => <DateChip key={row.id} row={row} />)}
        </ul>
      ) : (
        <p className="text-xs text-text-muted">No dates yet.</p>
      )}

      {editing ? (
        <div className="space-y-2 border border-border rounded p-3">
          {rows.map((row, i) => (
            <div key={i} className="grid grid-cols-2 gap-2">
              <label className="block text-xs text-text-muted space-y-1">
                <span>Choice {i + 1}</span>
                <input
                  type="date"
                  value={row.start}
                  onChange={change(i, 'start')}
                  className="w-full bg-bg-surface border border-border rounded px-2 py-1 text-sm text-text-primary"
                />
              </label>
              <label className="block text-xs text-text-muted space-y-1">
                <span>Until (optional)</span>
                <input
                  type="date"
                  value={row.end}
                  min={row.start || undefined}
                  onChange={change(i, 'end')}
                  className="w-full bg-bg-surface border border-border rounded px-2 py-1 text-sm text-text-primary"
                />
              </label>
            </div>
          ))}
          <div className="flex gap-2">
            <button
              onClick={save}
              disabled={busy}
              className="px-3 py-1 text-xs bg-secondary text-black font-medium rounded hover:opacity-90 disabled:opacity-40"
            >
              Save dates
            </button>
            <button
              onClick={() => setEditing(false)}
              className="px-3 py-1 text-xs border border-border rounded text-text-muted hover:text-text-primary"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          {dates?.length > 0 && !confirmed && (
            <button
              onClick={onConfirm}
              disabled={busy}
              className="px-3 py-1 text-xs border border-accent-green/40 text-accent-green rounded hover:bg-accent-green/10 disabled:opacity-40"
            >
              Looks right
            </button>
          )}
          <button
            onClick={startEditing}
            disabled={busy}
            className="px-3 py-1 text-xs border border-border rounded text-text-muted hover:text-text-primary disabled:opacity-40"
          >
            {dates?.length ? 'Fix dates' : 'Add dates'}
          </button>
          {needsCheck && <span className="text-xs text-amber-300">Needs a check</span>}
          {confirmed && <span className="text-xs text-text-muted">Checked by {dates.find((d) => d.confirmed_by)?.confirmed_by}</span>}
        </div>
      )}
    </div>
  )
}
