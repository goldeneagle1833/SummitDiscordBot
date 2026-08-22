import { useState, useEffect, useMemo, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { getEventsWithAdmin, getEvent, reorderEvents, updateEventMetadata, createEvent, pollEventJob, setFeaturedEvent } from '@/api/events'
import { getAvatarImageFiles } from '@/api/cards'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

const ELEMENT_COLORS = {
  Fire: { label: 'text-red-400', bar: 'bg-red-500' },
  Water: { label: 'text-blue-400', bar: 'bg-blue-500' },
  Earth: { label: 'text-amber-700', bar: 'bg-amber-700' },
  Air: { label: 'text-sky-300', bar: 'bg-sky-400' },
}

const YEARS = ['2026', '2025', '2024', '2023']
const SORT_OPTIONS = [
  { value: 'date-desc', label: 'Newest First' },
  { value: 'date-asc', label: 'Oldest First' },
  { value: 'players-desc', label: 'Most Players' },
  { value: 'players-asc', label: 'Fewest Players' },
]

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

function parseEventDate(ev) {
  if (ev.event_date) return new Date(ev.event_date).getTime()
  // Try to extract year from name/folder
  const match = ((ev.name || '') + ' ' + (ev.folder || '')).match(/20\d{2}/)
  return match ? new Date(match[0] + '-01-01').getTime() : 0
}

function sortEvents(events, sortBy) {
  const sorted = [...events]
  switch (sortBy) {
    case 'date-desc':
      return sorted.sort((a, b) => parseEventDate(b) - parseEventDate(a))
    case 'date-asc':
      return sorted.sort((a, b) => parseEventDate(a) - parseEventDate(b))
    case 'players-desc':
      return sorted.sort((a, b) => (b.player_count || 0) - (a.player_count || 0))
    case 'players-asc':
      return sorted.sort((a, b) => (a.player_count || 0) - (b.player_count || 0))
    default:
      return sorted
  }
}

function getEventYear(ev) {
  if (ev.event_date) {
    const m = ev.event_date.match(/^(20\d{2})/)
    if (m) return m[1]
  }
  const combined = ((ev.name || '') + ' ' + (ev.folder || '')).toLowerCase()
  const match = combined.match(/20\d{2}/)
  return match ? match[0] : 'Other'
}

function groupByYear(events) {
  const groups = {}
  for (const ev of events) {
    const year = getEventYear(ev)
    if (!groups[year]) groups[year] = []
    groups[year].push(ev)
  }
  // Sort year keys descending (Other at end)
  return Object.entries(groups).sort(([a], [b]) => {
    if (a === 'Other') return 1
    if (b === 'Other') return -1
    return Number(b) - Number(a)
  })
}

export default function Events() {
  usePageTitle('Top 8 Decks by Event')
  const [events, setEvents] = useState([])
  const [isAdmin, setIsAdmin] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [yearFilter, setYearFilter] = useState('')
  const [sortBy, setSortBy] = useState('date-desc')
  const [selectedFolder, setSelectedFolder] = useState(null)
  const [featuredFolder, setFeaturedFolder] = useState(null)
  const [imageFiles, setImageFiles] = useState([])
  const [selectedTop8, setSelectedTop8] = useState([])
  const [selectedEventData, setSelectedEventData] = useState(null)

  // Admin state
  const [editModal, setEditModal] = useState(null)
  const [editSaving, setEditSaving] = useState(false)
  const [createModal, setCreateModal] = useState(false)
  const [createForm, setCreateForm] = useState({ title: '', ranked: Array(8).fill(''), bulk: '' })
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState(null)
  const [createResult, setCreateResult] = useState(null)
  const [createProgress, setCreateProgress] = useState(null)

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
        setFeaturedFolder(data.featured_event || null)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(() => {
    let result = events
    if (yearFilter) {
      result = result.filter((ev) => getEventYear(ev) === yearFilter)
    }
    return sortEvents(result, sortBy)
  }, [events, yearFilter, sortBy])

  // Auto-select: featured event, or first in filtered list
  const selected = useMemo(() => {
    if (selectedFolder) {
      const found = filtered.find((e) => e.folder === selectedFolder)
      if (found) return found
    }
    if (featuredFolder) {
      const found = filtered.find((e) => e.folder === featuredFolder)
      if (found) return found
    }
    return filtered[0] || null
  }, [filtered, selectedFolder, featuredFolder])

  // Fetch event detail for selected event preview
  useEffect(() => {
    if (!selected) { setSelectedTop8([]); setSelectedEventData(null); return }
    getEvent(selected.folder)
      .then((data) => {
        setSelectedTop8(data.top8_decks || [])
        setSelectedEventData(data)
      })
      .catch(() => { setSelectedTop8([]); setSelectedEventData(null) })
  }, [selected?.folder])

  const yearGroups = useMemo(() => groupByYear(filtered), [filtered])

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
    setCreateProgress('Submitting...')
    try {
      const bulk_urls = createForm.bulk
        .split('\n')
        .map((u) => u.trim())
        .filter(Boolean)
      const submitResult = await createEvent({
        title: createForm.title.trim(),
        ranked_urls: createForm.ranked,
        bulk_urls,
      })
      if (!submitResult.success || !submitResult.job_id) {
        setCreateError(submitResult.error || 'Failed to start event creation')
        return
      }
      const result = await pollEventJob(submitResult.job_id, {
        onProgress: (p) => setCreateProgress(p),
      })
      if (result.success) {
        const data = await getEventsWithAdmin()
        setEvents(data.events || [])
        if (result.warnings?.length) {
          setCreateResult(result)
        } else {
          setCreateModal(false)
        }
      } else {
        setCreateError(result.error || 'Failed to create event')
      }
    } catch (err) {
      setCreateError(err.message || 'Failed to create event')
    } finally {
      setCreating(false)
      setCreateProgress(null)
    }
  }, [createForm])

  const handleSetFeatured = useCallback(async (folder) => {
    try {
      const result = await setFeaturedEvent(folder)
      if (result.success) setFeaturedFolder(folder)
    } catch { /* ignore */ }
  }, [])

  const handleClearFeatured = useCallback(async () => {
    try {
      const result = await setFeaturedEvent(null)
      if (result.success) setFeaturedFolder(null)
    } catch { /* ignore */ }
  }, [])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  const selectedImg = selected ? getAvatarImagePath(selected.winner_avatar, imageFiles) : null

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
          and I&apos;ll be happy to add them!
        </p>
      </section>

      {/* Split View */}
      <div className="flex flex-col lg:flex-row gap-4">
        {/* Left Panel — Featured/Selected Event Preview */}
        <div className="lg:w-5/12 xl:w-5/12 shrink-0">
          {selected ? (
            <div className="sticky top-20 max-h-[calc(100vh-6rem)] overflow-y-auto">
              <div className="relative rounded-lg overflow-hidden border-2 border-primary/30 bg-bg-surface" style={{ minHeight: '280px' }}>
                {selectedImg && (
                  <>
                    <div
                      className="absolute inset-0 bg-cover bg-center"
                      style={{ backgroundImage: `url('/avatar-images/${selectedImg}')`, opacity: 0.35, filter: 'brightness(0.8)' }}
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent" />
                  </>
                )}
                <div className="relative p-6 flex flex-col justify-end min-h-[280px]">
                  <div className="flex items-center gap-2 mb-2">
                    {selected.folder === (featuredFolder || filtered[0]?.folder) && (
                      <span className="text-xs font-semibold text-primary uppercase tracking-wide bg-primary/10 px-2 py-0.5 rounded">
                        Latest
                      </span>
                    )}
                    {selected.rating > 0 && (
                      <span className="text-yellow-400 text-sm">
                        {'★'.repeat(selected.rating)}{'☆'.repeat(3 - selected.rating)}
                      </span>
                    )}
                  </div>
                  <h2 className="text-2xl font-display text-secondary mb-2">{selected.name || selected.folder}</h2>
                  {selected.event_date_display && (
                    <p className="text-sm text-text-muted mb-2">{selected.event_date_display}</p>
                  )}
                  <div className="flex flex-wrap items-center gap-4 text-sm text-text-muted mb-4">
                    {selected.winner_username && (
                      <span>
                        Winner: <span className="text-text font-semibold">{selected.winner_username}</span>
                        {selected.winner_avatar && <span className="text-text-muted"> ({selected.winner_avatar})</span>}
                      </span>
                    )}
                    <span>{selected.player_count || 0} decks</span>
                  </div>
                  <Link
                    to={`/top-8/${selected.folder}`}
                    className="inline-flex items-center gap-2 bg-primary text-black px-4 py-2 rounded font-semibold text-sm hover:bg-primary-light transition-colors w-fit"
                  >
                    View Decks
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                      <path fillRule="evenodd" d="M3 10a.75.75 0 01.75-.75h10.638L10.23 5.29a.75.75 0 111.04-1.08l5.5 5.25a.75.75 0 010 1.08l-5.5 5.25a.75.75 0 11-1.04-1.08l4.158-3.96H3.75A.75.75 0 013 10z" clipRule="evenodd" />
                    </svg>
                  </Link>
                  {isAdmin && (
                    <div className="absolute top-3 right-3 flex gap-1">
                      {featuredFolder === selected.folder ? (
                        <button
                          onClick={handleClearFeatured}
                          className="text-xs text-text-muted hover:text-accent-red bg-bg-raised/80 px-2 py-1 rounded transition-colors"
                        >
                          Unpin
                        </button>
                      ) : (
                        <button
                          onClick={() => handleSetFeatured(selected.folder)}
                          className="p-1.5 rounded bg-bg-raised/80 hover:bg-bg-raised text-text-muted hover:text-primary transition-colors"
                          title="Pin as featured"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                            <path d="M10.868 2.884c-.321-.772-1.415-.772-1.736 0l-1.83 4.401-4.753.381c-.833.067-1.171 1.107-.536 1.651l3.62 3.102-1.106 4.637c-.194.813.691 1.456 1.405 1.02L10 15.591l4.069 2.485c.713.436 1.598-.207 1.404-1.02l-1.106-4.637 3.62-3.102c.635-.544.297-1.584-.536-1.65l-4.752-.382-1.831-4.401z" />
                          </svg>
                        </button>
                      )}
                      <button
                        onClick={() => setEditModal({ folder: selected.folder, name: selected.name || selected.folder, rating: selected.rating || 1, event_date: selected.event_date || '' })}
                        className="p-1.5 rounded bg-bg-raised/80 hover:bg-bg-raised text-text-muted hover:text-secondary transition-colors"
                        title="Edit event"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                          <path d="M2.695 14.763l-1.262 3.154a.5.5 0 00.65.65l3.155-1.262a4 4 0 001.343-.885L17.5 5.5a2.121 2.121 0 00-3-3L3.58 13.42a4 4 0 00-.885 1.343z" />
                        </svg>
                      </button>
                    </div>
                  )}
                </div>
              </div>
              {/* Event Details Card */}
              {(selectedTop8.length > 0 || selectedEventData) && (
                <div className="mt-3 bg-bg-surface border border-border rounded-lg divide-y divide-border">
                  {/* Element + Avatar Stats (top) */}
                  {selectedEventData && (
                    <div className="grid grid-cols-2 divide-x divide-border">
                      {/* Dominant Element Distribution */}
                      {selectedEventData.element_stats?.dominant_element?.length > 0 && (
                        <div className="p-4">
                          <h3 className="text-[11px] font-semibold text-text-muted uppercase tracking-widest mb-3">Elements</h3>
                          <div className="space-y-2">
                            {[...selectedEventData.element_stats.dominant_element].sort((a, b) => b.percent - a.percent).map((el) => {
                              const colors = ELEMENT_COLORS[el.name] || {}
                              return (
                                <div key={el.name}>
                                  <div className="flex items-baseline justify-between mb-1">
                                    <span className={`text-xs font-medium ${colors.label || 'text-text-muted'}`}>{el.name}</span>
                                    <span className="text-[10px] text-text-muted/60 tabular-nums">{el.percent}%</span>
                                  </div>
                                  <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
                                    <div
                                      className={`h-full rounded-full ${colors.bar || 'bg-gray-500'} transition-all duration-500`}
                                      style={{ width: `${Math.max(el.percent, 3)}%` }}
                                    />
                                  </div>
                                </div>
                              )
                            })}
                          </div>
                        </div>
                      )}
                      {/* Avatar Distribution */}
                      {selectedEventData.all_decks?.length > 0 && (() => {
                        const counts = {}
                        for (const d of selectedEventData.all_decks) {
                          const av = d.avatar || 'Unknown'
                          counts[av] = (counts[av] || 0) + 1
                        }
                        const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1])
                        const uniqueCount = sorted.length
                        return (
                          <div className="p-4">
                            <div className="flex items-baseline justify-between mb-3">
                              <h3 className="text-[11px] font-semibold text-text-muted uppercase tracking-widest">Avatars</h3>
                              <span className="text-[10px] text-text-muted/50">{uniqueCount} unique</span>
                            </div>
                            <div className="space-y-1.5">
                              {sorted.slice(0, 8).map(([avatar, count]) => (
                                <div key={avatar} className="flex items-center gap-2 text-xs">
                                  <span className="text-text/90 truncate flex-1">{avatar}</span>
                                  <span className="text-text-muted/60 tabular-nums shrink-0">{count}</span>
                                </div>
                              ))}
                              {sorted.length > 8 && (
                                <p className="text-[10px] text-text-muted/40 pt-0.5">+{sorted.length - 8} more</p>
                              )}
                            </div>
                          </div>
                        )
                      })()}
                    </div>
                  )}
                  {/* Placements (bottom) */}
                  {selectedTop8.length > 0 && (
                    <div className="p-4">
                      <h3 className="text-[11px] font-semibold text-text-muted uppercase tracking-widest mb-3">Placements</h3>
                      <ol className="space-y-1.5">
                        {selectedTop8.slice(0, 8).map((deck, i) => {
                          const elems = deck.elements || []
                          const content = (
                            <>
                              <span className={`w-5 text-xs font-bold shrink-0 tabular-nums ${
                                i === 0 ? 'text-yellow-400' : i === 1 ? 'text-gray-300' : i === 2 ? 'text-amber-600' : 'text-text-muted/60'
                              }`}>
                                {i + 1}.
                              </span>
                              <span className={`truncate ${i < 3 ? 'text-text font-medium' : 'text-text/80'}`}>{deck.player}</span>
                              <span className="ml-auto flex items-center gap-1.5 shrink-0">
                                <span className="text-secondary text-xs">{deck.avatar}</span>
                                {elems.length > 0 && (
                                  <span className="text-text-muted/40 text-[10px]">
                                    {elems.join('/')}
                                  </span>
                                )}
                              </span>
                            </>
                          )
                          return deck.deck_id ? (
                            <li key={deck.deck_id}>
                              <Link
                                to={`/deck-rec/${deck.deck_id}`}
                                className="flex items-center text-sm gap-2 hover:bg-white/5 rounded px-1 -mx-1 py-0.5 transition-colors"
                              >
                                {content}
                              </Link>
                            </li>
                          ) : (
                            <li key={i} className="flex items-center text-sm gap-2 px-1 -mx-1 py-0.5">
                              {content}
                            </li>
                          )
                        })}
                      </ol>
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="rounded-lg border border-border bg-bg-surface p-8 text-center text-text-muted">
              No events found
            </div>
          )}
        </div>

        {/* Right Panel — Event List */}
        <div className="flex-1 min-w-0">
          {/* Filters + Sort */}
          <div className="flex flex-wrap items-end gap-3 mb-4 p-3 bg-bg-surface rounded-lg border border-border">
            <div>
              <label className="text-xs text-text-muted block mb-1">Sort</label>
              <select
                className="bg-bg-raised border border-border rounded px-3 py-1.5 text-sm"
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
              >
                {SORT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
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
            <span className="text-text-muted text-xs ml-auto self-end pb-1">
              {filtered.length} event{filtered.length !== 1 ? 's' : ''}
            </span>
            {isAdmin && (
              <button
                className="text-xs bg-primary text-black px-3 py-1.5 rounded font-semibold self-end"
                onClick={openCreateModal}
              >
                + Add Event
              </button>
            )}
          </div>

          {/* Event List grouped by year */}
          <div className="space-y-4">
            {yearGroups.length === 0 && (
              <p className="text-center text-text-muted py-8">No events match your filters.</p>
            )}
            {yearGroups.map(([year, yearEvents]) => (
              <div key={year}>
                <div className="flex items-center gap-3 mb-2">
                  <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wider">{year}</h3>
                  <div className="flex-1 h-px bg-border" />
                  <span className="text-xs text-text-muted">{yearEvents.length}</span>
                </div>
                <div className="space-y-1">
                  {yearEvents.map((event) => {
                    const isSelected = selected?.folder === event.folder
                    const isLatest = event.folder === (featuredFolder || filtered[0]?.folder)
                    return (
                      <button
                        key={event.folder}
                        onClick={() => setSelectedFolder(event.folder)}
                        className={`w-full text-left rounded-lg p-3 transition-all group ${
                          isSelected
                            ? 'bg-primary/10 border border-primary/40'
                            : 'bg-bg-surface border border-border hover:border-primary/30 hover:bg-bg-elevated/50'
                        }`}
                      >
                        <div className="flex items-center gap-3">
                          {/* Selection indicator */}
                          <div className={`w-2 h-2 rounded-full shrink-0 ${isSelected ? 'bg-primary' : 'bg-border'}`} />

                          {/* Event info */}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-0.5">
                              <span className={`font-semibold truncate ${isSelected ? 'text-primary-light' : 'text-text'}`}>
                                {event.name || event.folder}
                              </span>
                              {isLatest && (
                                <span className="text-[10px] font-semibold text-primary uppercase tracking-wide bg-primary/10 px-1.5 py-0.5 rounded shrink-0">
                                  New
                                </span>
                              )}
                            </div>
                            <div className="flex items-center gap-3 text-xs text-text-muted">
                              {event.event_date_display && <span>{event.event_date_display}</span>}
                              {event.winner_username && <span className="truncate">Winner: {event.winner_username}</span>}
                              <span className="shrink-0">{event.player_count || 0} decks</span>
                            </div>
                          </div>

                          {/* View link */}
                          <Link
                            to={`/top-8/${event.folder}`}
                            onClick={(e) => e.stopPropagation()}
                            className="shrink-0 text-xs text-text-muted hover:text-primary transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100"
                          >
                            View →
                          </Link>
                        </div>
                      </button>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

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
                  {creating ? (createProgress || 'Creating...') : 'Create Event'}
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
