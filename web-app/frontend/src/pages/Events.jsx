import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { getEventsWithAdmin, getEvent, reorderEvents, updateEventMetadata, createEvent, importEventFromUrl, pollEventJob, setFeaturedEvent, getTop8DeckIndex, searchTop8Card } from '@/api/events'
import { getAvatarImageFiles } from '@/api/cards'
import Spinner from '@/components/ui/Spinner'
import { SubmitEventModal, ReviewSubmissionsModal } from '@/components/events/EventSubmissions'
import ShareLinkButton from '@/components/ui/ShareLinkButton'
import usePageTitle from '@/hooks/usePageTitle'
import { useIsDesktop, usePrefersReducedMotion } from '@/hooks/useMediaQuery'

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

// Event types an admin can tag an event with. The server sends its own list
// (event_tags); this is the fallback if it doesn't.
const DEFAULT_EVENT_TAGS = ['Grand Contest', 'Cornerstone', 'Local']
const UNTAGGED = '__untagged__'
const TAG_STYLES = {
  'Grand Contest': 'text-yellow-300 bg-yellow-400/10 border-yellow-400/30',
  Cornerstone: 'text-sky-300 bg-sky-400/10 border-sky-400/30',
  Local: 'text-emerald-300 bg-emerald-400/10 border-emerald-400/30',
}

function EventTagBadge({ tag, className = '' }) {
  if (!tag) return null
  return (
    <span className={`text-[10px] font-semibold uppercase tracking-wide border px-1.5 py-0.5 rounded shrink-0 ${TAG_STYLES[tag] || 'text-text-muted bg-white/5 border-border'} ${className}`}>
      {tag}
    </span>
  )
}

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

const ELEMENTS = ['Fire', 'Water', 'Earth', 'Air']
const PLACE_OPTIONS = [
  { value: '', label: 'Any deck' },
  { value: '8', label: 'Top 8' },
  { value: '4', label: 'Top 4' },
  { value: '2', label: 'Finalists' },
  { value: '1', label: 'Winners' },
]
const STAR_OPTIONS = [
  { value: '', label: 'Any' },
  { value: '2', label: '★★ and up' },
  { value: '3', label: '★★★ only' },
]

function placeLabel(place) {
  if (place == null) return 'Played'
  if (place === 1) return '1st'
  if (place === 2) return '2nd'
  if (place <= 4) return 'Top 4'
  if (place <= 8) return 'Top 8'
  return `#${place}`
}

function placeClass(place) {
  if (place === 1) return 'text-yellow-300 bg-yellow-400/10 border-yellow-400/30'
  if (place === 2) return 'text-gray-200 bg-white/5 border-white/20'
  if (place != null && place <= 8) return 'text-primary-light bg-primary/10 border-primary/30'
  return 'text-text-muted bg-white/5 border-border'
}

const norm = (s) => (s || '').toLowerCase()

/**
 * Work out which events (and which of their decks) match the deck filters.
 * Returns null when no deck-level filter or search is on, otherwise a Map of
 * folder -> matching decks (only events that match at all are in the map).
 */
function matchEventDecks(events, deckIndex, { query, avatar, elements, place, cardMatches }) {
  const q = norm(query).trim()
  const deckFilterOn = Boolean(avatar || elements.length || place || cardMatches)
  if (!q && !deckFilterOn) return null
  const out = new Map()
  for (const ev of events) {
    const rows = deckIndex?.[ev.folder] || []
    const cardHits = cardMatches ? new Set(cardMatches[ev.folder] || []) : null
    const decks = []
    rows.forEach((r, i) => {
      const [p, player, av, els, id] = r
      if (avatar && av !== avatar) return
      if (elements.length && !elements.every((e) => (els || []).includes(e))) return
      if (place && (p == null || p > Number(place))) return
      if (cardHits && !cardHits.has(i)) return
      decks.push({ place: p, player, avatar: av, elements: els || [], deck_id: id })
    })
    const nameHit = q && (norm(ev.name).includes(q) || norm(ev.folder).includes(q))
    const playerHits = q ? decks.filter((d) => norm(d.player).includes(q)) : decks
    let shown
    if (q && !nameHit) {
      if (!playerHits.length) continue
      shown = playerHits
    } else if (deckFilterOn) {
      if (!decks.length) continue
      shown = decks
    } else {
      shown = [] // event name search only: no deck list needed
    }
    shown.sort((a, b) => (a.place ?? 9999) - (b.place ?? 9999))
    out.set(ev.folder, shown)
  }
  return out
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
  const [searchParams, setSearchParams] = useSearchParams()
  const [yearFilter, setYearFilter] = useState(() => searchParams.get('year') || '')
  const [tagFilter, setTagFilter] = useState(() => searchParams.get('type') || '')
  const [eventTags, setEventTags] = useState(DEFAULT_EVENT_TAGS)
  const [sortBy, setSortBy] = useState('date-desc')

  // Deck filters (kept in the URL so a filtered view can be shared)
  const [query, setQuery] = useState(() => searchParams.get('q') || '')
  const [avatarFilter, setAvatarFilter] = useState(() => searchParams.get('avatar') || '')
  const [elementFilter, setElementFilter] = useState(() =>
    (searchParams.get('el') || '').split(',').filter((e) => ELEMENTS.includes(e)))
  const [placeFilter, setPlaceFilter] = useState(() => searchParams.get('place') || '')
  const [starFilter, setStarFilter] = useState(() => searchParams.get('stars') || '')
  const [cardInput, setCardInput] = useState(() => searchParams.get('card') || '')
  const [cardFilter, setCardFilter] = useState(() => searchParams.get('card') || '')
  const [cardMatches, setCardMatches] = useState(null)
  const [cardLoading, setCardLoading] = useState(false)
  const [deckIndex, setDeckIndex] = useState(null)
  const [deckIndexError, setDeckIndexError] = useState(false)
  const [moreFiltersOpen, setMoreFiltersOpen] = useState(false)
  const [selectedFolder, setSelectedFolder] = useState(null)
  const [featuredFolder, setFeaturedFolder] = useState(null)
  const [imageFiles, setImageFiles] = useState([])
  const [selectedTop8, setSelectedTop8] = useState([])
  const [selectedEventData, setSelectedEventData] = useState(null)

  // Mobile accordion behaviour + a11y
  const isDesktop = useIsDesktop()
  const reducedMotion = usePrefersReducedMotion()
  const rowRefs = useRef({})               // folder -> row <button>
  const userPickedRef = useRef(false)      // only scroll/announce after a real tap
  const [announcement, setAnnouncement] = useState('')

  // Admin state
  const [editModal, setEditModal] = useState(null)
  const [editSaving, setEditSaving] = useState(false)
  const [createModal, setCreateModal] = useState(false)
  const [createMode, setCreateMode] = useState('import') // 'import' or 'manual'
  const [createForm, setCreateForm] = useState({ title: '', ranked: Array(8).fill(''), bulk: '', eventUrl: '' })
  const [importUrl, setImportUrl] = useState('')
  const [importTitle, setImportTitle] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState(null)
  const [createResult, setCreateResult] = useState(null)
  const [createProgress, setCreateProgress] = useState(null)

  // Player submissions (anyone logged in can send in an event; admins approve)
  const [loggedIn, setLoggedIn] = useState(false)
  const [pendingSubmissions, setPendingSubmissions] = useState(0)
  const [localThreshold, setLocalThreshold] = useState(16)
  const [submitModal, setSubmitModal] = useState(() =>
    searchParams.get('submit') === '1' ? 'submit' : searchParams.get('submissions') === 'mine' ? 'mine' : null)
  const [reviewModal, setReviewModal] = useState(() => searchParams.get('review') === '1')

  // Compare mode
  const [compareMode, setCompareMode] = useState(false)
  const [compareSelection, setCompareSelection] = useState(new Set())
  const navigate = useNavigate()

  const toggleCompareEvent = useCallback((folder) => {
    setCompareSelection((prev) => {
      const next = new Set(prev)
      if (next.has(folder)) next.delete(folder)
      else if (next.size < 10) next.add(folder)
      return next
    })
  }, [])

  const handleCompare = useCallback(() => {
    if (compareSelection.size >= 2) {
      navigate(`/top-8/compare?events=${[...compareSelection].join(',')}`)
    }
  }, [compareSelection, navigate])

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
        setLoggedIn(!!data.logged_in)
        setPendingSubmissions(data.pending_submissions || 0)
        if (data.local_player_threshold) setLocalThreshold(data.local_player_threshold)
        setFeaturedFolder(data.featured_event || null)
        if (Array.isArray(data.event_tags) && data.event_tags.length) setEventTags(data.event_tags)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  // Deck summaries for the avatar / player / element / placement filters.
  useEffect(() => {
    getTop8DeckIndex()
      .then((data) => setDeckIndex(data || { events: {}, avatars: [], cards: [] }))
      .catch(() => setDeckIndexError(true))
  }, [])

  // Card filter: the server knows which decks run which cards.
  useEffect(() => {
    if (!cardFilter) { setCardMatches(null); return }
    let cancelled = false
    setCardLoading(true)
    searchTop8Card(cardFilter)
      .then((data) => { if (!cancelled) setCardMatches(data?.matches || {}) })
      .catch(() => { if (!cancelled) setCardMatches({}) })
      .finally(() => { if (!cancelled) setCardLoading(false) })
    return () => { cancelled = true }
  }, [cardFilter])

  // Apply the typed card once it matches a real card name (or on Enter).
  const cardNames = deckIndex?.cards
  useEffect(() => {
    const typed = cardInput.trim()
    if (!typed) { setCardFilter(''); return }
    const exact = cardNames?.find((c) => c.toLowerCase() === typed.toLowerCase())
    if (exact) setCardFilter(exact)
  }, [cardInput, cardNames])

  // Mirror the filters into the URL (replace, so Back still leaves the page).
  useEffect(() => {
    const next = new URLSearchParams()
    if (query.trim()) next.set('q', query.trim())
    if (avatarFilter) next.set('avatar', avatarFilter)
    if (elementFilter.length) next.set('el', elementFilter.join(','))
    if (placeFilter) next.set('place', placeFilter)
    if (cardFilter) next.set('card', cardFilter)
    if (starFilter) next.set('stars', starFilter)
    if (yearFilter) next.set('year', yearFilter)
    if (tagFilter) next.set('type', tagFilter)
    if (next.toString() !== searchParams.toString()) setSearchParams(next, { replace: true })
  }, [query, avatarFilter, elementFilter, placeFilter, cardFilter, starFilter, yearFilter, tagFilter]) // eslint-disable-line react-hooks/exhaustive-deps

  const toggleElement = useCallback((el) => {
    setElementFilter((prev) => (prev.includes(el) ? prev.filter((e) => e !== el) : [...prev, el]))
  }, [])

  const secondaryCount = (elementFilter.length ? 1 : 0) + (yearFilter ? 1 : 0) + (tagFilter ? 1 : 0) + (starFilter ? 1 : 0) + (sortBy !== 'date-desc' ? 1 : 0)
  const showMoreFilters = moreFiltersOpen
  const deckFiltersOn = Boolean(avatarFilter || elementFilter.length || placeFilter || cardFilter)
  const anyFilterOn = Boolean(deckFiltersOn || query.trim() || starFilter || yearFilter || tagFilter)
  const clearFilters = useCallback(() => {
    setQuery(''); setAvatarFilter(''); setElementFilter([]); setPlaceFilter('')
    setCardInput(''); setCardFilter(''); setStarFilter(''); setYearFilter(''); setTagFilter('')
  }, [])
  // Deck filters need the deck index (and the card search, if a card is set).
  const deckDataPending = (deckFiltersOn || query.trim()) && !deckIndex && !deckIndexError
  const cardPending = Boolean(cardFilter) && (cardLoading || cardMatches == null)

  const filtered = useMemo(() => {
    let result = events
    if (starFilter) {
      result = result.filter((ev) => (ev.rating || 0) >= Number(starFilter))
    }
    if (yearFilter) {
      result = result.filter((ev) => getEventYear(ev) === yearFilter)
    }
    if (tagFilter === UNTAGGED) {
      result = result.filter((ev) => !ev.tag)
    } else if (tagFilter) {
      result = result.filter((ev) => ev.tag === tagFilter)
    }
    return sortEvents(result, sortBy)
  }, [events, yearFilter, tagFilter, sortBy, starFilter])

  // folder -> matching decks, or null when no deck filter / search is on.
  const deckMatches = useMemo(() => {
    if (deckDataPending || cardPending) return null
    return matchEventDecks(filtered, deckIndex?.events, {
      query,
      avatar: avatarFilter,
      elements: elementFilter,
      place: placeFilter,
      cardMatches: cardFilter ? cardMatches : null,
    })
  }, [filtered, deckIndex, query, avatarFilter, elementFilter, placeFilter, cardFilter, cardMatches, deckDataPending, cardPending])

  const visibleEvents = useMemo(() => {
    if (!deckMatches) return (deckDataPending || cardPending) && (deckFiltersOn || query.trim()) ? [] : filtered
    return filtered.filter((ev) => deckMatches.has(ev.folder))
  }, [filtered, deckMatches, deckDataPending, cardPending, deckFiltersOn, query])
  const matchedDeckCount = useMemo(() => {
    if (!deckMatches) return 0
    let n = 0
    for (const d of deckMatches.values()) n += d.length
    return n
  }, [deckMatches])

  // Auto-select: featured event, or first in filtered list
  const selected = useMemo(() => {
    if (selectedFolder) {
      const found = visibleEvents.find((e) => e.folder === selectedFolder)
      if (found) return found
    }
    if (featuredFolder) {
      const found = visibleEvents.find((e) => e.folder === featuredFolder)
      if (found) return found
    }
    return visibleEvents[0] || null
  }, [visibleEvents, selectedFolder, featuredFolder])

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

  // After the user picks an event: keep the tapped row in view on mobile (an
  // earlier row collapsing above it would otherwise shove it off-screen) and
  // tell screen-reader users what changed, since the preview lives elsewhere.
  useEffect(() => {
    if (!userPickedRef.current || !selected) return
    userPickedRef.current = false
    setAnnouncement(`Showing ${selected.name || selected.folder}`)
    if (isDesktop) return
    const row = rowRefs.current[selected.folder]
    if (!row || typeof row.scrollIntoView !== 'function') return
    // Let the accordion render first so the measurement is right.
    const id = requestAnimationFrame(() => {
      row.scrollIntoView({ block: 'start', behavior: reducedMotion ? 'auto' : 'smooth' })
    })
    return () => cancelAnimationFrame(id)
  }, [selected?.folder, isDesktop, reducedMotion])

  // Highlight the selected event's placements that match the deck filters.
  const selectedMatchIds = useMemo(
    () => new Set((selected && deckMatches?.get(selected.folder)?.map((d) => d.deck_id).filter(Boolean)) || []),
    [selected, deckMatches],
  )

  const yearGroups = useMemo(() => groupByYear(visibleEvents), [visibleEvents])

  const saveMetadata = useCallback(async () => {
    if (!editModal) return
    setEditSaving(true)
    try {
      const result = await updateEventMetadata(editModal.folder, {
        name: editModal.name,
        rating: editModal.rating,
        event_date: editModal.event_date || null,
        tag: editModal.tag || '',
        attendance: editModal.attendance === '' ? 0 : Number(editModal.attendance),
      })
      if (result.success) {
        setEvents((prev) =>
          prev.map((e) =>
            e.folder === editModal.folder
              ? { ...e, name: editModal.name, rating: editModal.rating, event_date: editModal.event_date || null, tag: editModal.tag || null, attendance: editModal.attendance === '' ? null : Number(editModal.attendance) || null }
              : e
          )
        )
        setEditModal(null)
      }
    } catch { /* ignore */ }
    finally { setEditSaving(false) }
  }, [editModal])

  const openCreateModal = () => {
    setCreateForm({ title: '', ranked: Array(8).fill(''), bulk: '', eventUrl: '' })
    setImportUrl('')
    setImportTitle('')
    setCreateMode('import')
    setCreateError(null)
    setCreateResult(null)
    setCreateModal(true)
  }

  const handleCreate = useCallback(async () => {
    if (createMode === 'import') {
      if (!importUrl.trim()) return
    } else {
      if (!createForm.title.trim() || !createForm.eventUrl.trim()) return
    }
    setCreating(true)
    setCreateError(null)
    setCreateResult(null)
    setCreateProgress('Submitting...')
    try {
      let submitResult
      if (createMode === 'import') {
        submitResult = await importEventFromUrl({
          title: importTitle.trim(),
          event_url: importUrl.trim(),
        })
      } else {
        const bulk_urls = createForm.bulk
          .split('\n')
          .map((u) => u.trim())
          .filter(Boolean)
        submitResult = await createEvent({
          title: createForm.title.trim(),
          ranked_urls: createForm.ranked,
          event_url: createForm.eventUrl.trim(),
          bulk_urls,
        })
      }
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
  }, [createForm, createMode, importUrl, importTitle])

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

  // Decks in this event that match the deck filters, shown under its row.
  const renderDeckMatches = (event, { inPanel = false } = {}) => {
    const decks = deckMatches?.get(event.folder)
    if (!decks || !decks.length) return null
    const limit = 5
    const shown = decks.slice(0, limit)
    return (
      <div className={inPanel ? 'p-3 border-b border-border' : 'border border-t-0 border-border rounded-b-lg bg-bg-surface/60 px-3 py-2'}>
        <p className="text-[10px] font-semibold text-text-muted uppercase tracking-widest mb-1">
          {decks.length} matching deck{decks.length !== 1 ? 's' : ''}
        </p>
        <ul className="space-y-0.5">
          {shown.map((d, i) => {
            const body = (
              <>
                <span className={`text-[10px] font-semibold border px-1.5 py-0.5 rounded shrink-0 w-12 text-center ${placeClass(d.place)}`}>
                  {placeLabel(d.place)}
                </span>
                <span className="truncate text-text/90">{d.player}</span>
                <span className="ml-auto flex items-center gap-1 shrink-0 text-[11px]">
                  <span className="text-secondary">{d.avatar}</span>
                  {d.elements.length > 0 && <span className="text-white/80">({d.elements.join('/')})</span>}
                </span>
              </>
            )
            return (
              <li key={d.deck_id || i}>
                {d.deck_id ? (
                  <Link to={`/deck-rec/${d.deck_id}`} className="flex items-center gap-2 text-xs rounded px-1 -mx-1 py-0.5 hover:bg-white/5">
                    {body}
                  </Link>
                ) : (
                  <div className="flex items-center gap-2 text-xs px-1 -mx-1 py-0.5">{body}</div>
                )}
              </li>
            )
          })}
        </ul>
        {decks.length > limit && (
          <Link to={`/top-8/${event.folder}`} className="text-[11px] text-primary hover:underline">
            +{decks.length - limit} more in this event →
          </Link>
        )}
      </div>
    )
  }

  // The big event preview tile. On desktop it sits in the sticky left panel;
  // on mobile it renders inside the accordion, right under the tapped row.
  const renderHeroCard = (event, { inAccordion = false } = {}) => {
    const img = getAvatarImagePath(event.winner_avatar, imageFiles)
    return (
      <div className={`relative overflow-hidden bg-bg-surface ${inAccordion ? 'border-b border-border' : 'rounded-lg border-2 border-primary/30'}`} style={{ minHeight: inAccordion ? '220px' : '280px' }}>
        {img && (
          <>
            <div
              className="absolute inset-0 bg-cover bg-center"
              style={{ backgroundImage: `url('/avatar-images/${img}')`, opacity: 0.35, filter: 'brightness(0.8)' }}
            />
            <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent" />
          </>
        )}
        <div className={`relative flex flex-col justify-end ${inAccordion ? 'p-4 min-h-[220px]' : 'p-6 min-h-[280px]'}`}>
          <div className="flex items-center gap-2 mb-2">
            {event.folder === (featuredFolder || filtered[0]?.folder) && (
              <span className="text-xs font-semibold text-primary uppercase tracking-wide bg-primary/10 px-2 py-0.5 rounded">
                Latest
              </span>
            )}
            <EventTagBadge tag={event.tag} />
            {event.rating > 0 && (
              <span className="text-yellow-400 text-sm">
                {'★'.repeat(event.rating)}{'☆'.repeat(3 - event.rating)}
              </span>
            )}
          </div>
          <h2 className={`font-display text-secondary mb-2 ${inAccordion ? 'text-xl' : 'text-2xl'}`}>{event.name || event.folder}</h2>
          {event.event_date_display && (
            <p className="text-sm text-text-muted mb-2">{event.event_date_display}</p>
          )}
          <div className="flex flex-wrap items-center gap-4 text-sm text-text-muted mb-4">
            {event.winner_username && (
              <span>
                Winner: <span className="text-text font-semibold">{event.winner_username}</span>
                {event.winner_avatar && <span className="text-text-muted"> ({event.winner_avatar})</span>}
              </span>
            )}
            {event.attendance > 0 && <span>{event.attendance} players</span>}
            <span>{event.player_count || 0} decks</span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
          <Link
            to={`/top-8/${event.folder}`}
            className="inline-flex items-center gap-2 bg-primary text-black px-4 py-2 rounded font-semibold text-sm hover:bg-primary-light transition-colors w-fit"
          >
            View Decks
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4" aria-hidden="true">
              <path fillRule="evenodd" d="M3 10a.75.75 0 01.75-.75h10.638L10.23 5.29a.75.75 0 111.04-1.08l5.5 5.25a.75.75 0 010 1.08l-5.5 5.25a.75.75 0 11-1.04-1.08l4.158-3.96H3.75A.75.75 0 013 10z" clipRule="evenodd" />
            </svg>
          </Link>
          <ShareLinkButton
            path={`/top-8/${encodeURIComponent(event.folder)}`}
            className="bg-bg-raised/80 text-text px-4 py-2 font-semibold text-sm border border-border hover:text-primary"
          />
          </div>
          {isAdmin && (
            <div className="absolute top-3 right-3 flex gap-1">
              {featuredFolder === event.folder ? (
                <button
                  onClick={handleClearFeatured}
                  className="text-xs text-text-muted hover:text-accent-red bg-bg-raised/80 px-2 py-1 rounded transition-colors"
                >
                  Unpin
                </button>
              ) : (
                <button
                  onClick={() => handleSetFeatured(event.folder)}
                  className="p-1.5 rounded bg-bg-raised/80 hover:bg-bg-raised text-text-muted hover:text-primary transition-colors"
                  title="Pin as featured"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                    <path d="M10.868 2.884c-.321-.772-1.415-.772-1.736 0l-1.83 4.401-4.753.381c-.833.067-1.171 1.107-.536 1.651l3.62 3.102-1.106 4.637c-.194.813.691 1.456 1.405 1.02L10 15.591l4.069 2.485c.713.436 1.598-.207 1.404-1.02l-1.106-4.637 3.62-3.102c.635-.544.297-1.584-.536-1.65l-4.752-.382-1.831-4.401z" />
                  </svg>
                </button>
              )}
              <button
                onClick={() => setEditModal({ folder: event.folder, name: event.name || event.folder, rating: event.rating || 1, event_date: event.event_date || '', tag: event.tag || '', attendance: event.attendance ?? '' })}
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
    )
  }

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      {/* Hero */}
      <section className="text-center mb-6">
        <h1 className="text-2xl font-display text-secondary mb-2">Event Results</h1>
        {/* Announces the newly selected event to assistive tech (preview renders elsewhere) */}
        <p className="sr-only" aria-live="polite" aria-atomic="true">{announcement}</p>
        <p className="text-text-muted text-sm">Browse winning decks from competitive Sorcery events</p>
        <p className="text-text-muted/50 text-xs mt-1">
          Want to see your event here?{' '}
          <button type="button" className="text-secondary hover:underline" onClick={() => setSubmitModal('submit')}>
            Send in your sorcerytcg.com event
          </button>{' '}
          and we&apos;ll add it once it&apos;s checked.
        </p>
      </section>

      {/* Split View */}
      <div className="flex flex-col lg:flex-row gap-4">
        {/* Left Panel — Featured/Selected Event Preview */}
        <div className="hidden lg:block lg:w-5/12 xl:w-5/12 shrink-0">
          {selected ? (
            <div className="sticky top-20 max-h-[calc(100vh-6rem)] overflow-y-auto">
              {renderHeroCard(selected)}
              {/* Event Details Card (desktop only — mobile uses accordion in event list) */}
              {(selectedTop8.length > 0 || selectedEventData) && (
                <div className="mt-3 bg-bg-surface border border-border rounded-lg divide-y divide-border hidden lg:block">
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
                                  <div className="h-4 bg-white/5 rounded overflow-hidden">
                                    <div
                                      className={`h-full rounded ${colors.bar || 'bg-gray-500'} transition-all duration-500`}
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
                                  <span className="text-white text-[11px]">
                                    ({elems.join('/')})
                                  </span>
                                )}
                              </span>
                            </>
                          )
                          return deck.deck_id ? (
                            <li key={deck.deck_id}>
                              <Link
                                to={`/deck-rec/${deck.deck_id}`}
                                className={`flex items-center text-sm gap-2 hover:bg-white/5 rounded px-1 -mx-1 py-0.5 transition-colors ${selectedMatchIds.has(deck.deck_id) ? 'bg-primary/10 ring-1 ring-primary/40' : ''}`}
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
          <div className="mb-4 p-3 bg-bg-surface rounded-lg border border-border space-y-3">
            {/* Find decks: search, avatar, card */}
            <div className="flex flex-wrap items-end gap-3">
              <div className="flex-1 min-w-[12rem]">
                <label htmlFor="top8-search" className="text-xs text-text-muted block mb-1">Search player or event</label>
                <input
                  id="top8-search"
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="e.g. Ambrai or Gen Con"
                  className="w-full bg-bg-raised border border-border rounded px-3 py-1.5 text-sm placeholder:text-text-muted/50"
                />
              </div>
              <div className="w-[calc(50%-0.375rem)] sm:w-auto">
                <label htmlFor="top8-avatar" className="text-xs text-text-muted block mb-1">Avatar</label>
                <select
                  id="top8-avatar"
                  className="w-full bg-bg-raised border border-border rounded px-3 py-1.5 text-sm"
                  value={avatarFilter}
                  onChange={(e) => setAvatarFilter(e.target.value)}
                >
                  <option value="">All Avatars</option>
                  {(deckIndex?.avatars || (avatarFilter ? [avatarFilter] : [])).map((a) => <option key={a} value={a}>{a}</option>)}
                </select>
              </div>
              <div className="w-[calc(50%-0.375rem)] sm:w-auto">
                <label htmlFor="top8-placement" className="text-xs text-text-muted block mb-1">Finish</label>
                <select
                  id="top8-placement"
                  className="w-full bg-bg-raised border border-border rounded px-3 py-1.5 text-sm"
                  value={placeFilter}
                  onChange={(e) => setPlaceFilter(e.target.value)}
                >
                  {PLACE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
              <div className="flex-1 min-w-[12rem] sm:max-w-[16rem]">
                <label htmlFor="top8-card" className="text-xs text-text-muted block mb-1">Deck runs card</label>
                <input
                  id="top8-card"
                  type="search"
                  list="top8-card-names"
                  value={cardInput}
                  onChange={(e) => setCardInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') setCardFilter(cardInput.trim()) }}
                  placeholder="Type a card name"
                  className="w-full bg-bg-raised border border-border rounded px-3 py-1.5 text-sm placeholder:text-text-muted/50"
                />
                <datalist id="top8-card-names">
                  {cardInput.trim().length >= 2 && (deckIndex?.cards || [])
                    .filter((c) => c.toLowerCase().includes(cardInput.trim().toLowerCase()))
                    .slice(0, 30)
                    .map((c) => <option key={c} value={c} />)}
                </datalist>
              </div>
            </div>
            {/* Elements + event filters (folded away on phones until asked for) */}
            <div id="top8-more-filters" className={`${showMoreFilters ? 'flex' : 'hidden'} lg:flex flex-wrap items-end gap-3`}>
              <div>
                <span className="text-xs text-text-muted block mb-1" id="top8-elements-label">Elements</span>
                <div className="flex gap-1" role="group" aria-labelledby="top8-elements-label">
                  {ELEMENTS.map((el) => {
                    const on = elementFilter.includes(el)
                    return (
                      <button
                        key={el}
                        type="button"
                        aria-pressed={on}
                        onClick={() => toggleElement(el)}
                        className={`px-2.5 py-1.5 rounded text-xs font-semibold border transition-colors ${
                          on
                            ? `${ELEMENT_COLORS[el].bar} text-black border-transparent`
                            : `bg-bg-raised border-border ${ELEMENT_COLORS[el].label} hover:border-white/30`
                        }`}
                      >
                        {el}
                      </button>
                    )
                  })}
                </div>
              </div>
              <div>
                <label className="text-xs text-text-muted block mb-1" htmlFor="top8-sort">Sort</label>
                <select
                  id="top8-sort"
                  className="bg-bg-raised border border-border rounded px-3 py-1.5 text-sm"
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                >
                  {SORT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-text-muted block mb-1" htmlFor="top8-year">Year</label>
                <select
                  id="top8-year"
                  className="bg-bg-raised border border-border rounded px-3 py-1.5 text-sm"
                  value={yearFilter}
                  onChange={(e) => setYearFilter(e.target.value)}
                >
                  <option value="">All Years</option>
                  {YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="event-type-filter" className="text-xs text-text-muted block mb-1">Type</label>
                <select
                  id="event-type-filter"
                  className="bg-bg-raised border border-border rounded px-3 py-1.5 text-sm"
                  value={tagFilter}
                  onChange={(e) => setTagFilter(e.target.value)}
                >
                  <option value="">All Types</option>
                  {eventTags.map((t) => <option key={t} value={t}>{t}</option>)}
                  {isAdmin && <option value={UNTAGGED}>Untagged</option>}
                </select>
              </div>
              <div>
                <label htmlFor="top8-stars" className="text-xs text-text-muted block mb-1">Stars</label>
                <select
                  id="top8-stars"
                  className="bg-bg-raised border border-border rounded px-3 py-1.5 text-sm"
                  value={starFilter}
                  onChange={(e) => setStarFilter(e.target.value)}
                >
                  {STAR_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
            </div>
            {/* Result count + actions */}
            <div className="flex flex-wrap items-center gap-3">
            <span className="text-text-muted text-xs mr-auto" aria-live="polite">
              {deckDataPending || cardPending
                ? 'Finding decks…'
                : <>
                    {visibleEvents.length} event{visibleEvents.length !== 1 ? 's' : ''}
                    {deckMatches && matchedDeckCount > 0 && <> · {matchedDeckCount} matching deck{matchedDeckCount !== 1 ? 's' : ''}</>}
                  </>}
              {deckIndexError && (deckFiltersOn || query.trim()) && <span className="text-accent-red"> · Deck filters could not load</span>}
            </span>
            <button
              type="button"
              className="lg:hidden text-xs px-3 py-1.5 rounded font-semibold bg-bg-raised border border-border text-text-muted hover:text-text"
              aria-expanded={showMoreFilters}
              aria-controls="top8-more-filters"
              onClick={() => setMoreFiltersOpen(!showMoreFilters)}
            >
              {showMoreFilters ? 'Fewer filters' : `More filters${secondaryCount ? ` (${secondaryCount})` : ''}`}
            </button>
            {anyFilterOn && (
              <button
                type="button"
                onClick={clearFilters}
                className="text-xs px-3 py-1.5 rounded font-semibold bg-bg-raised border border-border text-text-muted hover:text-text hover:border-primary/50"
              >
                Clear filters
              </button>
            )}
            <button
              className={`text-xs px-3 py-1.5 rounded font-semibold transition-colors ${
                compareMode
                  ? 'bg-secondary text-black'
                  : 'bg-bg-raised border border-border text-text-muted hover:text-text hover:border-secondary/50'
              }`}
              onClick={() => {
                setCompareMode((m) => !m)
                if (compareMode) setCompareSelection(new Set())
              }}
            >
              {compareMode ? 'Cancel Compare' : 'Compare Events'}
            </button>
            {isAdmin && (
              <button
                className={`text-xs px-3 py-1.5 rounded font-semibold transition-colors ${
                  pendingSubmissions > 0
                    ? 'bg-yellow-500/20 border border-yellow-500/50 text-yellow-200 hover:bg-yellow-500/30'
                    : 'bg-bg-raised border border-border text-text-muted hover:text-text'
                }`}
                onClick={() => setReviewModal(true)}
              >
                Submissions{pendingSubmissions > 0 ? ` (${pendingSubmissions})` : ''}
              </button>
            )}
            <button
              className="text-xs bg-primary text-black px-3 py-1.5 rounded font-semibold"
              onClick={isAdmin ? openCreateModal : () => setSubmitModal('submit')}
            >
              + Add Event
            </button>
            </div>
          </div>

          {/* Event List grouped by year */}
          <div className="space-y-4">
            {yearGroups.length === 0 && (
              <p className="text-center text-text-muted py-8">
                {deckDataPending || cardPending ? 'Finding decks…' : 'No events match your filters.'}
              </p>
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
                    const isCompareChecked = compareSelection.has(event.folder)
                    const hasMatches = !compareMode && Boolean(deckMatches?.get(event.folder)?.length)
                    return (
                      <div key={event.folder} className={compareMode ? 'flex items-stretch gap-0' : ''}>
                        {compareMode && (
                          <button
                            onClick={() => toggleCompareEvent(event.folder)}
                            className={`flex items-center justify-center w-10 shrink-0 rounded-l-lg border border-r-0 transition-colors ${
                              isCompareChecked
                                ? 'bg-secondary/20 border-secondary/40'
                                : 'bg-bg-surface border-border hover:bg-bg-elevated/50'
                            }`}
                          >
                            <div className={`w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${
                              isCompareChecked ? 'bg-secondary border-secondary' : 'border-border'
                            }`}>
                              {isCompareChecked && (
                                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5 text-black">
                                  <path fillRule="evenodd" d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z" clipRule="evenodd" />
                                </svg>
                              )}
                            </div>
                          </button>
                        )}
                        <button
                          id={`event-row-${event.folder}`}
                          ref={(el) => { rowRefs.current[event.folder] = el }}
                          aria-expanded={compareMode || isDesktop ? undefined : isSelected}
                          aria-controls={compareMode || isDesktop ? undefined : `event-panel-${event.folder}`}
                          aria-current={!compareMode && isSelected ? 'true' : undefined}
                          aria-pressed={compareMode ? isCompareChecked : undefined}
                          onClick={() => {
                            if (compareMode) {
                              toggleCompareEvent(event.folder)
                              return
                            }
                            // On mobile: toggle accordion. On desktop: always select.
                            userPickedRef.current = true
                            setSelectedFolder(isSelected && !isDesktop ? null : event.folder)
                          }}
                          className={`w-full text-left p-3 transition-all group scroll-mt-20 ${
                            compareMode
                              ? `rounded-r-lg border border-l-0 ${isCompareChecked ? 'bg-secondary/10 border-secondary/40' : 'bg-bg-surface border-border hover:bg-bg-elevated/50'}`
                              : `rounded-lg ${isSelected
                                ? 'bg-primary/10 border border-primary/40 rounded-t-lg rounded-b-none lg:rounded-lg'
                                : 'bg-bg-surface border border-border hover:border-primary/30 hover:bg-bg-elevated/50'} ${hasMatches ? 'lg:rounded-b-none' : ''} ${hasMatches && !isSelected ? 'rounded-b-none' : ''}`
                          }`}
                        >
                          <div className="flex items-center gap-3">
                            {/* Selection indicator */}
                            {!compareMode && (
                              <div className={`w-2 h-2 rounded-full shrink-0 ${isSelected ? 'bg-primary' : 'bg-border'}`} aria-hidden="true" />
                            )}
                            {!compareMode && isSelected && <span className="sr-only">Selected event: </span>}

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
                                <EventTagBadge tag={event.tag} />
                              </div>
                              <div className="flex items-center gap-3 text-xs text-text-muted">
                                {event.event_date_display && <span>{event.event_date_display}</span>}
                                {event.winner_username && <span className="truncate">Winner: {event.winner_username}</span>}
                                {event.attendance > 0 && <span className="shrink-0">{event.attendance} players</span>}
                                <span className="shrink-0">{event.player_count || 0} decks</span>
                              </div>
                            </div>

                            {/* View link (desktop) / chevron (mobile) */}
                            <Link
                              to={`/top-8/${event.folder}`}
                              onClick={(e) => e.stopPropagation()}
                              className="shrink-0 text-xs text-text-muted hover:text-primary transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100 hidden lg:block"
                            >
                              View →
                            </Link>
                            <svg
                              xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"
                              className={`w-4 h-4 shrink-0 text-text-muted transition-transform lg:hidden ${isSelected ? 'rotate-180' : ''}`}
                            >
                              <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd" />
                            </svg>
                          </div>
                        </button>
                        {/* Matching decks (desktop always; mobile while the row is closed) */}
                        {hasMatches && (isDesktop || !isSelected) && renderDeckMatches(event)}
                        {/* Mobile accordion */}
                        {isSelected && !compareMode && !isDesktop && (
                          <div
                            id={`event-panel-${event.folder}`}
                            role="region"
                            aria-labelledby={`event-row-${event.folder}`}
                            className="lg:hidden border border-t-0 border-primary/40 rounded-b-lg bg-bg-surface overflow-hidden"
                          >
                            {/* Event preview tile — same card as the desktop left panel, with View Decks */}
                            {renderHeroCard(event, { inAccordion: true })}
                            {hasMatches && renderDeckMatches(event, { inPanel: true })}
                            {/* Stats + Placements */}
                            {selectedEventData && (
                              <div className="grid grid-cols-2 divide-x divide-border border-b border-border">
                                {selectedEventData.element_stats?.dominant_element?.length > 0 && (
                                  <div className="p-3">
                                    <h3 className="text-[11px] font-semibold text-text-muted uppercase tracking-widest mb-2">Elements</h3>
                                    <div className="space-y-1.5">
                                      {[...selectedEventData.element_stats.dominant_element].sort((a, b) => b.percent - a.percent).map((el) => {
                                        const colors = ELEMENT_COLORS[el.name] || {}
                                        return (
                                          <div key={el.name}>
                                            <div className="flex items-baseline justify-between mb-0.5">
                                              <span className={`text-[11px] font-medium ${colors.label || 'text-text-muted'}`}>{el.name}</span>
                                              <span className="text-[10px] text-text-muted/60 tabular-nums">{el.percent}%</span>
                                            </div>
                                            <div className="h-3 bg-white/5 rounded overflow-hidden">
                                              <div
                                                className={`h-full rounded ${colors.bar || 'bg-gray-500'}`}
                                                style={{ width: `${Math.max(el.percent, 3)}%` }}
                                              />
                                            </div>
                                          </div>
                                        )
                                      })}
                                    </div>
                                  </div>
                                )}
                                {selectedEventData.all_decks?.length > 0 && (() => {
                                  const counts = {}
                                  for (const d of selectedEventData.all_decks) {
                                    const av = d.avatar || 'Unknown'
                                    counts[av] = (counts[av] || 0) + 1
                                  }
                                  const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1])
                                  return (
                                    <div className="p-3">
                                      <div className="flex items-baseline justify-between mb-2">
                                        <h3 className="text-[11px] font-semibold text-text-muted uppercase tracking-widest">Avatars</h3>
                                        <span className="text-[10px] text-text-muted/50">{sorted.length} unique</span>
                                      </div>
                                      <div className="space-y-1">
                                        {sorted.slice(0, 6).map(([avatar, count]) => (
                                          <div key={avatar} className="flex items-center gap-2 text-[11px]">
                                            <span className="text-text/90 truncate flex-1">{avatar}</span>
                                            <span className="text-text-muted/60 tabular-nums shrink-0">{count}</span>
                                          </div>
                                        ))}
                                        {sorted.length > 6 && (
                                          <p className="text-[10px] text-text-muted/40">+{sorted.length - 6} more</p>
                                        )}
                                      </div>
                                    </div>
                                  )
                                })()}
                              </div>
                            )}
                            {selectedTop8.length > 0 && (
                              <div className="p-3">
                                <h3 className="text-[11px] font-semibold text-text-muted uppercase tracking-widest mb-2">Placements</h3>
                                <ol className="space-y-1">
                                  {selectedTop8.slice(0, 8).map((deck, i) => {
                                    const elems = deck.elements || []
                                    return (
                                      <li key={deck.deck_id || i}>
                                        {deck.deck_id ? (
                                          <Link
                                            to={`/deck-rec/${deck.deck_id}`}
                                            className={`flex items-center text-[13px] gap-1.5 hover:bg-white/5 rounded px-1 -mx-1 py-0.5 transition-colors ${selectedMatchIds.has(deck.deck_id) ? 'bg-primary/10 ring-1 ring-primary/40' : ''}`}
                                          >
                                            <span className={`w-5 text-[11px] font-bold shrink-0 tabular-nums ${
                                              i === 0 ? 'text-yellow-400' : i === 1 ? 'text-gray-300' : i === 2 ? 'text-amber-600' : 'text-text-muted/60'
                                            }`}>{i + 1}.</span>
                                            <span className={`truncate ${i < 3 ? 'text-text font-medium' : 'text-text/80'}`}>{deck.player}</span>
                                            <span className="ml-auto flex items-center gap-1 shrink-0">
                                              <span className="text-secondary text-[11px]">{deck.avatar}</span>
                                              {elems.length > 0 && <span className="text-white text-[10px]">({elems.join('/')})</span>}
                                            </span>
                                          </Link>
                                        ) : (
                                          <div className="flex items-center text-[13px] gap-1.5 px-1 -mx-1 py-0.5">
                                            <span className={`w-5 text-[11px] font-bold shrink-0 tabular-nums ${
                                              i === 0 ? 'text-yellow-400' : i === 1 ? 'text-gray-300' : i === 2 ? 'text-amber-600' : 'text-text-muted/60'
                                            }`}>{i + 1}.</span>
                                            <span className={`truncate ${i < 3 ? 'text-text font-medium' : 'text-text/80'}`}>{deck.player}</span>
                                            <span className="ml-auto flex items-center gap-1 shrink-0">
                                              <span className="text-secondary text-[11px]">{deck.avatar}</span>
                                              {elems.length > 0 && <span className="text-white text-[10px]">({elems.join('/')})</span>}
                                            </span>
                                          </div>
                                        )}
                                      </li>
                                    )
                                  })}
                                </ol>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {submitModal && (
        <SubmitEventModal
          loggedIn={loggedIn}
          startOnMine={submitModal === 'mine'}
          threshold={localThreshold}
          onClose={() => setSubmitModal(null)}
        />
      )}

      {reviewModal && isAdmin && (
        <ReviewSubmissionsModal
          onClose={() => setReviewModal(false)}
          onChanged={() => {
            getEventsWithAdmin()
              .then((data) => {
                setEvents(data.events || [])
                setPendingSubmissions(data.pending_submissions || 0)
              })
              .catch(() => {})
          }}
        />
      )}

      {/* Create Event Modal */}
      {createModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setCreateModal(false)}>
          <div className="bg-bg-surface border border-border rounded-lg p-6 w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-display text-secondary mb-4">Add New Event</h3>

            {/* Mode tabs */}
            <div className="flex gap-1 mb-4 bg-bg-raised rounded p-0.5">
              <button
                className={`flex-1 text-xs py-1.5 rounded font-semibold transition-colors ${createMode === 'import' ? 'bg-primary text-black' : 'text-text-muted hover:text-text'}`}
                onClick={() => setCreateMode('import')}
              >
                Import from Event URL
              </button>
              <button
                className={`flex-1 text-xs py-1.5 rounded font-semibold transition-colors ${createMode === 'manual' ? 'bg-primary text-black' : 'text-text-muted hover:text-text'}`}
                onClick={() => setCreateMode('manual')}
              >
                Manual URLs
              </button>
            </div>

            {createMode === 'import' ? (
              <>
                <label className="text-xs text-text-muted block mb-1">sorcerytcg.com Event URL</label>
                <input
                  type="text"
                  className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-3"
                  placeholder="https://sorcerytcg.com/events/..."
                  value={importUrl}
                  onChange={(e) => setImportUrl(e.target.value)}
                />
                <label className="text-xs text-text-muted block mb-1">Custom Title (optional, auto-detected from event)</label>
                <input
                  type="text"
                  className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-4"
                  placeholder="Leave blank to use event name"
                  value={importTitle}
                  onChange={(e) => setImportTitle(e.target.value)}
                />
                <p className="text-xs text-text-muted/60 mb-4">
                  Automatically discovers all player decks registered for this event.
                </p>
              </>
            ) : (
              <>
                <label className="text-xs text-text-muted block mb-1">Event Title</label>
                <input
                  type="text"
                  className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-4"
                  placeholder="e.g. SCG Con Dallas 2026"
                  value={createForm.title}
                  onChange={(e) => setCreateForm((f) => ({ ...f, title: e.target.value }))}
                />

                <label htmlFor="manual-event-url" className="text-xs text-text-muted block mb-1">sorcerytcg.com Event URL</label>
                <input
                  id="manual-event-url"
                  type="text"
                  className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-1"
                  placeholder="https://sorcerytcg.com/events/..."
                  value={createForm.eventUrl}
                  onChange={(e) => setCreateForm((f) => ({ ...f, eventUrl: e.target.value }))}
                />
                <p className="text-xs text-text-muted/60 mb-4">
                  Required. Use this tab when the event page has no deck lists (for example only the top 4 were collected): the decks come from the links below, and the player count, date and standings come from the event page. Under 16 players is tagged Local.
                </p>

                <p className="text-xs text-text-muted mb-2">Curiosa Deck URLs by Placement (all optional)</p>
                <div className="space-y-2 mb-4">
                  {createForm.ranked.map((url, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <span className="text-xs text-text-muted w-8 text-right shrink-0">{i === 0 ? '1st' : i === 1 ? '2nd' : i === 2 ? '3rd' : `${i + 1}th`}</span>
                      <input
                        type="text"
                        className="flex-1 bg-bg-raised border border-border rounded px-3 py-1.5 text-sm"
                        placeholder="https://sorcerytcg.com/decks/..."
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
                  placeholder={"https://sorcerytcg.com/decks/...\nhttps://sorcerytcg.com/decks/..."}
                  value={createForm.bulk}
                  onChange={(e) => setCreateForm((f) => ({ ...f, bulk: e.target.value }))}
                />
              </>
            )}

            {createError && (
              <p className="text-accent-red text-xs mb-3">{createError}</p>
            )}

            {createResult && (
              <div className="mb-3 p-3 bg-bg-raised rounded border border-border">
                <p className="text-xs text-green-400 mb-1">
                  Event created: {createResult.top8_added} top 8 deck{createResult.top8_added !== 1 ? 's' : ''}, {createResult.bulk_added} other deck{createResult.bulk_added !== 1 ? 's' : ''} added.
                  {createResult.attendance > 0 && ` ${createResult.attendance} players${createResult.local ? ', tagged Local' : ''}.`}
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
                  disabled={creating || (createMode === 'import' ? !importUrl.trim() : !createForm.title.trim() || !createForm.eventUrl.trim())}
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
            <label htmlFor="edit-event-players" className="text-xs text-text-muted block mb-1">Players at the event (optional)</label>
            <input
              id="edit-event-players"
              type="number"
              min="0"
              inputMode="numeric"
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-4"
              placeholder="e.g. 30"
              value={editModal.attendance ?? ''}
              onChange={(e) => setEditModal((m) => ({ ...m, attendance: e.target.value.replace(/[^0-9]/g, '') }))}
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
            <label className="text-xs text-text-muted block mb-1">Event Type</label>
            <div className="flex flex-wrap gap-1 mb-4" role="radiogroup" aria-label="Event type">
              {[{ value: '', label: 'None' }, ...eventTags.map((t) => ({ value: t, label: t }))].map((opt) => {
                const active = (editModal.tag || '') === opt.value
                return (
                  <button
                    key={opt.value || 'none'}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    onClick={() => setEditModal((m) => ({ ...m, tag: opt.value }))}
                    className={`text-xs px-2.5 py-1 rounded border transition-colors ${
                      active
                        ? 'bg-secondary text-black border-secondary font-semibold'
                        : 'bg-bg-raised border-border text-text-muted hover:text-text'
                    }`}
                  >
                    {opt.label}
                  </button>
                )
              })}
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

      {/* Compare floating bar */}
      {compareMode && compareSelection.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 bg-bg-surface border border-secondary/50 rounded-xl shadow-2xl px-5 py-3 flex items-center gap-4">
          <span className="text-sm text-text">
            <span className="font-semibold text-secondary">{compareSelection.size}</span> event{compareSelection.size !== 1 ? 's' : ''} selected
          </span>
          <button
            onClick={handleCompare}
            disabled={compareSelection.size < 2}
            className="bg-secondary text-black px-4 py-2 rounded-lg font-semibold text-sm disabled:opacity-40 hover:bg-secondary/80 transition-colors"
          >
            Compare
          </button>
          <button
            onClick={() => setCompareSelection(new Set())}
            className="text-xs text-text-muted hover:text-accent-red transition-colors"
          >
            Clear
          </button>
        </div>
      )}
    </div>
  )
}
