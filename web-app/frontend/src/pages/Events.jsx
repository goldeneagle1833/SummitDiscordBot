import { useState, useEffect, useMemo, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { getEventsWithAdmin, reorderEvents, updateEventMetadata } from '@/api/events'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

const YEARS = ['2026', '2025', '2024', '2023']
const FORMATS = ['cornerstone', 'crossroads']

export default function Events() {
  usePageTitle('Top 8 Decks by Event')
  const [events, setEvents] = useState([])
  const [isAdmin, setIsAdmin] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [yearFilter, setYearFilter] = useState('')
  const [formatFilter, setFormatFilter] = useState('')
  const [dragIdx, setDragIdx] = useState(null)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [editModal, setEditModal] = useState(null) // { folder, name, rating }
  const [editSaving, setEditSaving] = useState(false)

  useEffect(() => {
    getEventsWithAdmin()
      .then((data) => {
        setEvents(data.events || [])
        setIsAdmin(data.is_admin || false)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(() => {
    return events.filter((ev) => {
      const combined = ((ev.name || '') + ' ' + (ev.folder || '')).toLowerCase()
      if (yearFilter && !combined.includes(yearFilter)) return false
      if (formatFilter && !combined.includes(formatFilter)) return false
      return true
    })
  }, [events, yearFilter, formatFilter])

  const canDrag = isAdmin && !yearFilter && !formatFilter

  const handleDragStart = (idx) => setDragIdx(idx)
  const handleDragOver = (e) => e.preventDefault()
  const handleDrop = useCallback((targetIdx) => {
    if (dragIdx === null || dragIdx === targetIdx) return
    setEvents((prev) => {
      const reordered = [...prev]
      const [moved] = reordered.splice(dragIdx, 1)
      reordered.splice(targetIdx, 0, moved)
      return reordered
    })
    setDirty(true)
    setDragIdx(null)
  }, [dragIdx])

  const saveOrder = useCallback(async () => {
    setSaving(true)
    try {
      const order = events.map((e) => e.folder)
      const result = await reorderEvents(order)
      if (result.success) setDirty(false)
    } catch { /* ignore */ }
    finally { setSaving(false) }
  }, [events])

  const saveMetadata = useCallback(async () => {
    if (!editModal) return
    setEditSaving(true)
    try {
      const result = await updateEventMetadata(editModal.folder, {
        name: editModal.name,
        rating: editModal.rating,
      })
      if (result.success) {
        setEvents((prev) =>
          prev.map((e) =>
            e.folder === editModal.folder
              ? { ...e, name: editModal.name, rating: editModal.rating }
              : e
          )
        )
        setEditModal(null)
      }
    } catch { /* ignore */ }
    finally { setEditSaving(false) }
  }, [editModal])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      {/* Hero */}
      <section className="text-center mb-6">
        <h1 className="text-2xl font-display text-secondary mb-2">Top 8 Decks by Event</h1>
        <p className="text-text-muted text-sm">Browse winning decks from competitive events</p>
        <p className="text-text-muted/50 text-xs mt-1">
          Want to see your event here? Send me a list of Curiosa deck URLs on the{' '}
          <a href="https://discord.gg/ZDqHSK9VGx" target="_blank" rel="noopener noreferrer" className="text-[#5865f2] hover:underline">
            Summit Discord
          </a>{' '}
          and I'll be happy to add them!
        </p>
      </section>

      {/* Filters + Save */}
      <div className="flex flex-wrap items-end gap-4 mb-4 p-3 bg-bg-surface rounded-lg border border-border">
        <div>
          <label className="text-xs text-text-muted block mb-1">Year</label>
          <select
            className="bg-bg-raised border border-border rounded px-3 py-1.5 text-sm"
            value={yearFilter}
            onChange={(e) => setYearFilter(e.target.value)}
          >
            <option value="">All Years</option>
            {YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-text-muted block mb-1">Format</label>
          <select
            className="bg-bg-raised border border-border rounded px-3 py-1.5 text-sm"
            value={formatFilter}
            onChange={(e) => setFormatFilter(e.target.value)}
          >
            <option value="">All Formats</option>
            {FORMATS.map((f) => <option key={f} value={f}>{f.charAt(0).toUpperCase() + f.slice(1)}</option>)}
          </select>
        </div>
        <span className="text-text-muted text-xs ml-auto self-end pb-1">
          {filtered.length} of {events.length} events
        </span>
        {isAdmin && dirty && (
          <button
            className="text-xs bg-secondary text-black px-3 py-1.5 rounded font-semibold disabled:opacity-50 self-end"
            onClick={saveOrder}
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Save Order'}
          </button>
        )}
      </div>

      {isAdmin && !canDrag && dirty && (
        <p className="text-xs text-text-muted mb-2">Clear filters to drag and reorder events.</p>
      )}

      {/* Grid */}
      {filtered.length === 0 ? (
        <p className="text-center text-text-muted py-8">No events match your filters.</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((event, idx) => {
            const stars = event.rating || 1
            return (
              <div
                key={event.folder}
                draggable={canDrag}
                onDragStart={() => handleDragStart(idx)}
                onDragOver={handleDragOver}
                onDrop={() => handleDrop(idx)}
                className={canDrag ? 'cursor-grab active:cursor-grabbing' : ''}
              >
                <div className="relative h-full">
                  <Link
                    to={`/top-8/${event.folder}`}
                    className="block bg-bg-surface border border-border rounded-lg p-4 hover:border-primary/50 hover:-translate-y-0.5 transition-all h-full"
                    draggable={false}
                  >
                    <div className="flex items-start gap-2">
                      {canDrag && (
                        <span className="text-text-muted/50 select-none mt-0.5">⠁⠁</span>
                      )}
                      <div className="flex-1 min-w-0">
                        <h3 className="font-semibold truncate mb-1">{event.name || event.folder}</h3>
                        <div className="flex gap-0.5 mb-1">
                          {[1, 2, 3].map((i) => (
                            <span key={i} className={i <= stars ? 'text-yellow-400' : 'text-white/20'}>★</span>
                          ))}
                        </div>
                        <div className="text-sm text-text-muted">
                          {event.player_count || 0} decks
                        </div>
                        {event.has_top8 && (
                          <span className="inline-block mt-1.5 text-xs bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded">
                            Top 8 Available
                          </span>
                        )}
                      </div>
                    </div>
                  </Link>
                  {isAdmin && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        setEditModal({ folder: event.folder, name: event.name || event.folder, rating: stars })
                      }}
                      className="absolute top-2 right-2 p-1.5 rounded bg-bg-raised/80 hover:bg-bg-raised text-text-muted hover:text-secondary transition-colors"
                      title="Edit event"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                        <path d="M2.695 14.763l-1.262 3.154a.5.5 0 00.65.65l3.155-1.262a4 4 0 001.343-.885L17.5 5.5a2.121 2.121 0 00-3-3L3.58 13.42a4 4 0 00-.885 1.343z" />
                      </svg>
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Edit Event Modal */}
      {editModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setEditModal(null)}>
          <div className="bg-bg-surface border border-border rounded-lg p-6 w-full max-w-sm mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-display text-secondary mb-4">Edit Event</h3>
            <label className="text-xs text-text-muted block mb-1">Title</label>
            <input
              type="text"
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-4"
              value={editModal.name}
              onChange={(e) => setEditModal((m) => ({ ...m, name: e.target.value }))}
            />
            <label className="text-xs text-text-muted block mb-1">Stars</label>
            <div className="flex gap-1 mb-4">
              {[1, 2, 3].map((i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setEditModal((m) => ({ ...m, rating: i }))}
                  className={`text-2xl ${i <= editModal.rating ? 'text-yellow-400' : 'text-white/20'} hover:text-yellow-300 transition-colors`}
                >
                  ★
                </button>
              ))}
            </div>
            <div className="flex justify-end gap-2">
              <button
                className="text-xs px-3 py-1.5 rounded border border-border text-text-muted hover:text-text"
                onClick={() => setEditModal(null)}
              >
                Cancel
              </button>
              <button
                className="text-xs bg-secondary text-black px-3 py-1.5 rounded font-semibold disabled:opacity-50"
                onClick={saveMetadata}
                disabled={editSaving || !editModal.name.trim()}
              >
                {editSaving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
