import { useState, useEffect, useMemo, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { getEventsWithAdmin, reorderEvents, updateEventMetadata, createEvent } from '@/api/events'
import { getAvatarImageFiles } from '@/api/cards'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

const YEARS = ['2026', '2025', '2024', '2023']
const FORMATS = ['cornerstone', 'crossroads']

function getAvatarImagePath(name, files) {
  if (!name || !files?.length) return null
  const norm = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, '')
  const n = norm(name)
  for (const f of files) {
    if (norm(f.replace(/\.\w+$/, '')) === n) return f
  }
  for (const f of files) {
    if (norm(f.replace(/\.\w+$/, '')).includes(n)) return f
  }
  for (const f of files) {
    if (n.includes(norm(f.replace(/\.\w+$/, '')))) return f
  }
  return null
}

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
  const [createModal, setCreateModal] = useState(false)
  const [createForm, setCreateForm] = useState({ title: '', ranked: Array(8).fill(''), bulk: '' })
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState(null)
  const [createResult, setCreateResult] = useState(null)
  const [imageFiles, setImageFiles] = useState([])

  useEffect(() => {
    getAvatarImageFiles()
      .then((files) => setImageFiles(files || []))
      .catch(() => {})
  }, [])

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

  const [saveError, setSaveError] = useState(null)

  const saveOrder = useCallback(async () => {
    setSaving(true)
    setSaveError(null)
    try {
      const order = events.map((e) => e.folder)
      const result = await reorderEvents(order)
      if (result.success) setDirty(false)
      else setSaveError(result.error || 'Failed to save order')
    } catch (err) {
      setSaveError(err.message || 'Failed to save order')
    } finally { setSaving(false) }
  }, [events])

  const saveMetadata = useCallback(async () => {
    if (!editModal) return
    setEditSaving(true)
    try {
      const result = await updateEventMetadata(editModal.folder, {
        name: editModal.name,
        rating: editModal.rating,
        event_date: editModal.event_date || null,
      })
      if (result.success) {
        setEvents((prev) =>
          prev.map((e) =>
            e.folder === editModal.folder
              ? { ...e, name: editModal.name, rating: editModal.rating, event_date: editModal.event_date || null }
              : e
          )
        )
        setEditModal(null)
      }
    } catch { /* ignore */ }
    finally { setEditSaving(false) }
  }, [editModal])

  const openCreateModal = () => {
    setCreateForm({ title: '', ranked: Array(8).fill(''), bulk: '' })
    setCreateError(null)
    setCreateResult(null)
    setCreateModal(true)
  }

  const handleCreate = useCallback(async () => {
    if (!createForm.title.trim()) return
    setCreating(true)
    setCreateError(null)
    setCreateResult(null)
    try {
      const bulk_urls = createForm.bulk
        .split('\n')
        .map((u) => u.trim())
        .filter(Boolean)
      const result = await createEvent({
        title: createForm.title.trim(),
        ranked_urls: createForm.ranked,
        bulk_urls,
      })
      if (result.success) {
        // Reload events
        const data = await getEventsWithAdmin()
        setEvents(data.events || [])
        // Show result summary or close
        if (result.warnings?.length) {
          setCreateResult(result)
        } else {
          setCreateModal(false)
        }
      } else {
        setCreateError(result.error || 'Failed to create event')
      }
    } catch (err) {
      const msg = err.status === 502 || err.status === 504 || err.message === 'Failed to fetch'
        ? 'Request timed out — the server may still be processing. Try with fewer URLs or check the event list.'
        : err.message || 'Failed to create event'
      setCreateError(msg)
    } finally {
      setCreating(false)
    }
  }, [createForm])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      {/* Hero */}
      <section className="text-center mb-6">
        <h1 className="text-2xl font-display text-secondary mb-2">Event Results</h1>
        <p className="text-text-muted text-sm">Browse winning decks from competitive Sorcery events</p>
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
        {isAdmin && (
          <button
            className="text-xs bg-primary text-black px-3 py-1.5 rounded font-semibold self-end"
            onClick={openCreateModal}
          >
            + Add Event
          </button>
        )}
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
      {saveError && (
        <p className="text-xs text-red-400 mb-2">Error saving order: {saveError}</p>
      )}

      {/* Featured Latest Event */}
      {filtered.length > 0 && (() => {
        const featured = filtered[0]
        const featuredImg = getAvatarImagePath(featured.winner_avatar, imageFiles)
        return (
          <Link
            to={`/top-8/${featured.folder}`}
            className="relative block mb-6 bg-bg-surface border-2 border-primary/30 rounded-lg overflow-hidden hover:border-primary/60 hover:-translate-y-0.5 transition-all"
            style={{ minHeight: '120px' }}
          >
            {featuredImg && (
              <>
                <div
                  className="absolute inset-0 bg-cover bg-center"
                  style={{ backgroundImage: `url('/avatar-images/${featuredImg}')`, opacity: 0.35, filter: 'brightness(0.8)' }}
                />
                <div className="absolute inset-0 bg-gradient-to-r from-black/60 via-black/40 to-transparent" />
              </>
            )}
            <div className="relative p-5">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-semibold text-primary uppercase tracking-wide">Latest Event</span>
                {featured.event_date_display && (
                  <span className="text-sm text-text-muted">{featured.event_date_display}</span>
                )}
              </div>
              <h2 className="text-xl font-display text-secondary mb-2">{featured.name || featured.folder}</h2>
              <div className="flex flex-wrap items-center gap-4 text-sm text-text-muted">
                {featured.winner_username && (
                  <span>
                    Winner: <span className="text-text">{featured.winner_username}</span>
                    {featured.winner_avatar && <span className="text-text-muted"> ({featured.winner_avatar})</span>}
                  </span>
                )}
                <span>{featured.player_count || 0} decks</span>
              </div>
            </div>
          </Link>
        )
      })()}

      {/* Grid */}
      {filtered.length <= 1 ? (
        filtered.length === 0 && <p className="text-center text-text-muted py-8">No events match your filters.</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.slice(1).map((event, idx) => (
              <div
                key={event.folder}
                draggable={canDrag}
                onDragStart={() => handleDragStart(idx + 1)}
                onDragOver={handleDragOver}
                onDrop={() => handleDrop(idx + 1)}
                className={canDrag ? 'cursor-grab active:cursor-grabbing' : ''}
              >
                <div className="relative h-full">
                  {(() => {
                    const cardImg = getAvatarImagePath(event.winner_avatar, imageFiles)
                    return (
                      <Link
                        to={`/top-8/${event.folder}`}
                        className="block bg-bg-surface border border-border rounded-lg overflow-hidden hover:border-primary/50 hover:-translate-y-0.5 transition-all h-full relative"
                        draggable={false}
                      >
                        {cardImg && (
                          <>
                            <div
                              className="absolute inset-0 bg-cover bg-center"
                              style={{ backgroundImage: `url('/avatar-images/${cardImg}')`, opacity: 0.2, filter: 'brightness(0.7)' }}
                            />
                            <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/40 to-transparent" />
                          </>
                        )}
                        <div className="relative p-4">
                          <div className="flex items-start gap-2">
                            {canDrag && (
                              <span className="text-text-muted/50 select-none mt-0.5">⠁⠁</span>
                            )}
                            <div className="flex-1 min-w-0">
                              <div className="flex items-start justify-between gap-2 mb-1">
                                <h3 className="font-semibold truncate">{event.name || event.folder}</h3>
                                {event.event_date_display && (
                                  <span className="text-xs text-text-muted whitespace-nowrap shrink-0">{event.event_date_display}</span>
                                )}
                              </div>
                              {event.winner_username && (
                                <p className="text-sm text-text-muted mb-1 truncate">
                                  Winner: {event.winner_username}{event.winner_avatar ? ` (${event.winner_avatar})` : ''}
                                </p>
                              )}
                              <div className="text-sm text-text-muted">
                                {event.player_count || 0} decks
                              </div>
                            </div>
                          </div>
                        </div>
                      </Link>
                    )
                  })()}
                  {isAdmin && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        setEditModal({ folder: event.folder, name: event.name || event.folder, rating: event.rating || 1, event_date: event.event_date || '' })
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
          ))}
        </div>
      )}

      {/* Create Event Modal */}
      {createModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setCreateModal(false)}>
          <div className="bg-bg-surface border border-border rounded-lg p-6 w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-display text-secondary mb-4">Add New Event</h3>

            <label className="text-xs text-text-muted block mb-1">Event Title</label>
            <input
              type="text"
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-4"
              placeholder="e.g. SCG Con Dallas 2026"
              value={createForm.title}
              onChange={(e) => setCreateForm((f) => ({ ...f, title: e.target.value }))}
            />

            <p className="text-xs text-text-muted mb-2">Curiosa Deck URLs by Placement (all optional)</p>
            <div className="space-y-2 mb-4">
              {createForm.ranked.map((url, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="text-xs text-text-muted w-8 text-right shrink-0">{i === 0 ? '1st' : i === 1 ? '2nd' : i === 2 ? '3rd' : `${i + 1}th`}</span>
                  <input
                    type="text"
                    className="flex-1 bg-bg-raised border border-border rounded px-3 py-1.5 text-sm"
                    placeholder="https://curiosa.io/decks/..."
                    value={url}
                    onChange={(e) => {
                      const next = [...createForm.ranked]
                      next[i] = e.target.value
                      setCreateForm((f) => ({ ...f, ranked: next }))
                    }}
                  />
                </div>
              ))}
            </div>

            <label className="text-xs text-text-muted block mb-1">Bulk Deck URLs (one per line)</label>
            <textarea
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-4 min-h-[80px]"
              placeholder={"https://curiosa.io/decks/...\nhttps://curiosa.io/decks/..."}
              value={createForm.bulk}
              onChange={(e) => setCreateForm((f) => ({ ...f, bulk: e.target.value }))}
            />

            {createError && (
              <p className="text-accent-red text-xs mb-3">{createError}</p>
            )}

            {createResult && (
              <div className="mb-3 p-3 bg-bg-raised rounded border border-border">
                <p className="text-xs text-green-400 mb-1">
                  Event created: {createResult.top8_added} top 8 deck{createResult.top8_added !== 1 ? 's' : ''}, {createResult.bulk_added} other deck{createResult.bulk_added !== 1 ? 's' : ''} added.
                </p>
                {createResult.warnings?.length > 0 && (
                  <div className="mt-1">
                    <p className="text-xs text-yellow-400 mb-1">Failed to fetch {createResult.warnings.length} URL{createResult.warnings.length !== 1 ? 's' : ''}:</p>
                    <ul className="text-xs text-text-muted space-y-0.5">
                      {createResult.warnings.map((w, i) => <li key={i} className="truncate">{w}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button
                className="text-xs px-3 py-1.5 rounded border border-border text-text-muted hover:text-text"
                onClick={() => setCreateModal(false)}
              >
                {createResult ? 'Done' : 'Cancel'}
              </button>
              {!createResult && (
                <button
                  className="text-xs bg-secondary text-black px-3 py-1.5 rounded font-semibold disabled:opacity-50"
                  onClick={handleCreate}
                  disabled={creating || !createForm.title.trim()}
                >
                  {creating ? 'Creating...' : 'Create Event'}
                </button>
              )}
            </div>
          </div>
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
            <label className="text-xs text-text-muted block mb-1">Event Date</label>
            <input
              type="date"
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-4"
              value={editModal.event_date || ''}
              onChange={(e) => setEditModal((m) => ({ ...m, event_date: e.target.value }))}
            />
            <label className="text-xs text-text-muted block mb-1">Tier</label>
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
