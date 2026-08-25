import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { Link, useSearchParams, useNavigate } from 'react-router-dom'
import AvatarImageAdmin from '@/components/ui/AvatarImageAdmin'
import { getDeckRecList, adminAddDeck, adminUpdateDeck, adminRemoveDeck, adminHideDeck, adminUnhideDeck } from '@/api/decks'
import { getAvatarImageFiles } from '@/api/cards'
import { getAvatarImageSettings } from '@/api/admin'
import { useAuth } from '@/context/AuthContext'
import usePageTitle from '@/hooks/usePageTitle'

const ELEMENT_ICONS = { Fire: 'fire.png', Water: 'water.png', Earth: 'earth.png', Air: 'wind.png' }
const PAGE_SIZE = 24

function normalize(str) {
  return str.toLowerCase().replace(/[^a-z0-9]/g, '')
}

function getAvatarImagePath(name, files) {
  if (!name || !files?.length) return null
  const norm = normalize(name)
  for (const img of files) {
    if (normalize(img.replace(/\.(png|jpg|jpeg|webp)$/i, '')) === norm) return img
  }
  for (const img of files) {
    if (normalize(img.replace(/\.(png|jpg|jpeg|webp)$/i, '')).includes(norm)) return img
  }
  return null
}

function ElementIcons({ elements }) {
  if (!elements?.length) return null
  return (
    <span className="inline-flex gap-1 items-center">
      {elements.filter((el) => ELEMENT_ICONS[el]).map((el) => (
        <img key={el} src={`/avatar-images/${ELEMENT_ICONS[el]}`} alt={el} title={el} width={22} height={22} className="drop-shadow" />
      ))}
    </span>
  )
}

/* ---- Deck Card Skeleton ---- */
function DeckCardSkeleton() {
  return (
    <div className="relative rounded-lg overflow-hidden bg-bg-surface border border-border animate-pulse" style={{ minHeight: '160px' }}>
      <div className="p-4 flex flex-col gap-2">
        <div className="h-4 bg-bg-raised rounded w-3/4" />
        <div className="h-3 bg-bg-raised rounded w-1/2" />
        <div className="h-3 bg-bg-raised rounded w-2/3" />
        <div className="h-3 bg-bg-raised rounded w-1/3 mt-auto" />
      </div>
    </div>
  )
}

/* ---- Deck Card ---- */
function DeckCard({ deck, imageFiles, imageSettings, isAdmin, onEdit, onRemove, onHide, onUnhide, isAdminRec, onImageSettingsSaved }) {
  const navigate = useNavigate()
  const imgFile = getAvatarImagePath(deck.avatar_name, imageFiles)
  const imgSrc = imgFile ? `/avatar-images/${imgFile}` : null
  const settings = imageSettings?.[deck.avatar_name] || {}
  const bgPos = `${settings.position_x ?? 50}% ${settings.position_y ?? 25}%`
  const bgBrightness = settings.brightness ?? 1.0
  const bgOpacity = settings.opacity ?? 0.5
  const clusterLabel = deck.cluster_size === 1 ? '1 similar build' : `${deck.cluster_size} similar builds`
  const starsStr = deck.stars ? '\u2605'.repeat(deck.stars) + '\u2606'.repeat(3 - deck.stars) : ''

  return (
    <div
      onClick={() => navigate(`/deck-rec/${encodeURIComponent(deck.deck_id)}`)}
      className={`relative block rounded-lg overflow-hidden transition-all group cursor-pointer hover:-translate-y-0.5 ${deck.is_hidden ? 'opacity-50' : ''} ${isAdminRec ? 'border border-secondary/40 bg-bg-surface hover:border-secondary/70' : 'bg-bg-surface border border-border hover:border-border/80'}`}
      style={{ minHeight: '160px' }}
    >
      {imgSrc && (
        <>
          <div
            className="absolute inset-0 bg-cover bg-center transition-opacity"
            style={{
              backgroundImage: `url('${imgSrc}')`,
              backgroundPosition: bgPos,
              filter: `brightness(${bgBrightness})`,
              opacity: bgOpacity,
            }}
          />
          <div className="absolute inset-0 bg-gradient-to-t from-bg-base/95 via-bg-base/60 to-bg-base/10 pointer-events-none" />
        </>
      )}
      {isAdminRec && !deck.is_hidden && (
        <div className="absolute top-2 right-2 z-10 text-[10px] font-semibold uppercase tracking-wider bg-bg-base/80 text-secondary border border-secondary/50 px-1.5 py-0.5 rounded">
          Staff Pick
        </div>
      )}
      {deck.is_hidden && (
        <div className="absolute top-2 right-2 z-10 text-[10px] font-semibold uppercase tracking-wider bg-bg-base/80 text-accent-red border border-accent-red/50 px-1.5 py-0.5 rounded">
          Hidden
        </div>
      )}
      <div className="relative p-4 flex flex-col h-full" style={{ textShadow: imgSrc ? '0 1px 3px rgba(0,0,0,0.8)' : 'none' }}>
        <h3 className="text-base font-semibold leading-tight truncate mb-2 text-text-primary" title={deck.deck_name}>
          {deck.deck_name}
        </h3>
        <div className="text-sm text-text-primary/90 mb-1">{deck.avatar_name}</div>
        {!isAdminRec && <div className="text-xs text-text-muted mb-1">{deck.event_name}</div>}
        {starsStr && <div className="text-sm text-yellow-400 mb-1 drop-shadow">{starsStr}</div>}
        <ElementIcons elements={deck.elements} />
        {deck.primer && <div className="text-xs text-text-primary/80 mt-1 line-clamp-2 italic">{deck.primer}</div>}
        <div className="text-xs text-text-primary/70 mt-auto pt-2">
          Community: <span className="text-text-primary font-medium">{clusterLabel}</span>
        </div>
        {isAdmin && (
          <div className="flex justify-end gap-2 mt-2 flex-wrap" onClick={(e) => e.stopPropagation()}>
            {imgSrc && (
              <AvatarImageAdmin
                avatarName={deck.avatar_name}
                imgSrc={imgSrc}
                currentSettings={settings}
                onSaved={onImageSettingsSaved}
              />
            )}
            {isAdminRec && (
              <>
                <button
                  className="text-xs text-text-muted hover:text-secondary"
                  onClick={(e) => { e.stopPropagation(); onEdit(deck) }}
                >
                  Edit
                </button>
                <button
                  className="text-xs text-text-muted hover:text-accent-red"
                  onClick={(e) => { e.stopPropagation(); onRemove(deck) }}
                >
                  Remove
                </button>
              </>
            )}
            {deck.is_hidden ? (
              <button
                className="text-xs text-text-muted hover:text-green-400"
                onClick={(e) => { e.stopPropagation(); onUnhide(deck) }}
              >
                Unhide
              </button>
            ) : (
              <button
                className="text-xs text-text-muted hover:text-accent-red"
                onClick={(e) => { e.stopPropagation(); onHide(deck) }}
              >
                Hide
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

/* ---- Avatar Search Autocomplete ---- */
function AvatarSearch({ avatars, value, onChange }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [hlIdx, setHlIdx] = useState(-1)
  const ref = useRef(null)

  const matches = useMemo(() => {
    if (!query) return avatars
    const q = query.toLowerCase()
    return avatars.filter((a) => a.toLowerCase().includes(q))
  }, [query, avatars])

  const select = useCallback((a) => {
    onChange(a)
    setQuery('')
    setOpen(false)
  }, [onChange])

  const clear = useCallback(() => {
    onChange('all')
    setQuery('')
    setOpen(false)
  }, [onChange])

  useEffect(() => { setHlIdx(-1) }, [matches])

  return (
    <div className="relative" ref={ref}>
      <label className="text-xs text-text-muted block mb-1">Avatar:</label>
      {value !== 'all' ? (
        <span className="inline-flex items-center gap-1 bg-bg-raised rounded px-2 py-1 text-sm text-secondary">
          {value}
          <button onClick={clear} className="text-text-muted hover:text-text-primary ml-1">x</button>
        </span>
      ) : (
        <div className="relative">
          <input
            type="text"
            placeholder="Search avatars..."
            className="bg-bg-raised border border-border rounded px-2 py-1 text-sm w-44"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setOpen(true) }}
            onFocus={() => setOpen(true)}
            onBlur={() => setTimeout(() => setOpen(false), 150)}
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown') { e.preventDefault(); setHlIdx((i) => Math.min(i + 1, matches.length - 1)) }
              else if (e.key === 'ArrowUp') { e.preventDefault(); setHlIdx((i) => Math.max(i - 1, 0)) }
              else if (e.key === 'Enter' && hlIdx >= 0 && matches[hlIdx]) select(matches[hlIdx])
              else if (e.key === 'Escape') setOpen(false)
            }}
          />
          {open && matches.length > 0 && (
            <div className="absolute z-20 mt-1 bg-bg-surface border border-border rounded shadow-lg max-h-48 overflow-y-auto w-full">
              {matches.map((a, i) => (
                <div
                  key={a}
                  className={`px-3 py-1.5 text-sm cursor-pointer ${i === hlIdx ? 'bg-bg-raised text-secondary' : 'text-text-primary hover:bg-bg-raised'}`}
                  onMouseDown={(e) => { e.preventDefault(); select(a) }}
                >
                  {a}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/* ---- Admin Add/Edit Modal ---- */
function AdminModal({ isOpen, onClose, onSubmit, editDeck }) {
  const [url, setUrl] = useState('')
  const [primer, setPrimer] = useState('')
  const [stars, setStars] = useState(null)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const isEdit = !!editDeck

  useEffect(() => {
    if (isOpen) {
      setUrl('')
      setPrimer(editDeck?.primer || '')
      setStars(editDeck?.stars || null)
      setError('')
    }
  }, [isOpen, editDeck])

  const handleSubmit = async () => {
    setError('')
    if (!isEdit && !url.trim()) { setError('Please enter a Curiosa deck URL.'); return }
    setSubmitting(true)
    try {
      if (isEdit) {
        await adminUpdateDeck(editDeck.deck_id, { primer: primer.trim(), stars })
      } else {
        await adminAddDeck({ curiosa_url: url.trim(), primer: primer.trim(), stars })
      }
      onSubmit()
      onClose()
    } catch (err) {
      setError(err.message || 'Failed. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-bg-surface border border-border rounded-lg p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <h3 className="font-display text-secondary text-lg mb-4">
          {isEdit ? `Edit — ${editDeck.deck_name || editDeck.deck_id}` : 'Add Admin Recommendation'}
        </h3>
        {!isEdit && (
          <div className="mb-3">
            <label className="text-sm text-text-primary font-medium block mb-1">Curiosa Deck URL</label>
            <input
              type="text"
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm"
              placeholder="https://curiosa.io/decks/..."
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
              autoFocus
            />
          </div>
        )}
        <div className="mb-3">
          <label className="text-sm text-text-primary font-medium block mb-1">Short Description / Primer (optional)</label>
          <textarea
            className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm"
            placeholder="Why you should try this deck..."
            rows={3}
            value={primer}
            onChange={(e) => setPrimer(e.target.value)}
          />
        </div>
        <div className="mb-4">
          <label className="text-sm text-text-primary font-medium block mb-1">Star Rating (optional)</label>
          <div className="flex gap-1">
            {[1, 2, 3].map((s) => (
              <button
                key={s}
                className={`text-xl ${stars >= s ? 'text-yellow-400' : 'text-text-muted'}`}
                onClick={() => setStars(stars === s ? null : s)}
              >
                {'\u2605'}
              </button>
            ))}
          </div>
        </div>
        {error && <p className="text-accent-red text-sm mb-3">{error}</p>}
        <div className="flex justify-end gap-3">
          <button className="text-sm text-text-muted hover:text-text-primary" onClick={onClose}>Cancel</button>
          <button
            className="text-sm bg-secondary text-bg-base px-4 py-1.5 rounded hover:opacity-90 disabled:opacity-50"
            onClick={handleSubmit}
            disabled={submitting}
          >
            {submitting ? (isEdit ? 'Saving...' : 'Adding...') : (isEdit ? 'Save Changes' : 'Add Deck')}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ---- Main Page ---- */
export default function DeckRecommendations() {
  usePageTitle('Sorcery Deck Rec')
  const { user } = useAuth()
  const isAdmin = user?.is_admin === true

  const [searchParams, setSearchParams] = useSearchParams()
  const [allDecks, setAllDecks] = useState([])
  const [imageFiles, setImageFiles] = useState([])
  const [imageSettings, setImageSettings] = useState({})
  const [decksLoading, setDecksLoading] = useState(true)
  const [imagesReady, setImagesReady] = useState(false)
  const [error, setError] = useState(null)
  const [page, setPage] = useState(1)

  // Filter state from URL params
  const activeAvatar = searchParams.get('avatar') || 'all'
  const activeElements = useMemo(() => {
    const raw = searchParams.get('element')
    return raw ? new Set(raw.split(',').filter((e) => ELEMENT_ICONS[e])) : new Set()
  }, [searchParams])
  const activeYear = searchParams.get('year') || ''
  const activeSort = searchParams.get('sort') || 'popular'

  // Modal
  const [modalOpen, setModalOpen] = useState(false)
  const [editDeck, setEditDeck] = useState(null)
  const [staffPicksOpen, setStaffPicksOpen] = useState(true)
  const [showHidden, setShowHidden] = useState(false)
  const [hiddenCount, setHiddenCount] = useState(0)

  // Load images first (fast), decks separately (slow)
  useEffect(() => {
    getAvatarImageFiles()
      .then((imgs) => setImageFiles(imgs || []))
      .finally(() => setImagesReady(true))
  }, [])

  // Load image settings only for admins
  useEffect(() => {
    if (!isAdmin) return
    getAvatarImageSettings()
      .then((data) => setImageSettings(data.settings || {}))
      .catch(() => {})
  }, [isAdmin])

  const handleImageSettingsSaved = useCallback((avatarName, newSettings) => {
    setImageSettings((prev) => {
      const next = { ...prev }
      if (newSettings) next[avatarName] = newSettings
      else delete next[avatarName]
      return next
    })
  }, [])

  const fetchData = useCallback(() => {
    setDecksLoading(true)
    getDeckRecList({ showHidden })
      .then((data) => {
        setAllDecks(data.decks || [])
        setHiddenCount(data.hidden_count || 0)
      })
      .catch((err) => setError(err.message))
      .finally(() => setDecksLoading(false))
  }, [showHidden])

  useEffect(() => { fetchData() }, [fetchData])

  const loading = decksLoading && !allDecks.length

  // Separate admin vs tournament
  const adminDecks = useMemo(() => allDecks.filter((d) => d.is_admin_rec), [allDecks])
  const tournamentDecks = useMemo(() => allDecks.filter((d) => !d.is_admin_rec), [allDecks])

  // Unique avatars and years for filters
  const avatarNames = useMemo(
    () => [...new Set(tournamentDecks.map((d) => d.avatar_name).filter(Boolean))].sort(),
    [tournamentDecks]
  )
  const years = useMemo(
    () => [...new Set(tournamentDecks.map((d) => d.event_year).filter(Boolean))].sort((a, b) => b - a),
    [tournamentDecks]
  )

  // Filtered and sorted
  const filtered = useMemo(() => {
    let result = tournamentDecks
    if (activeAvatar !== 'all') result = result.filter((d) => d.avatar_name === activeAvatar)
    if (activeElements.size > 0) result = result.filter((d) => d.elements && [...activeElements].every((el) => d.elements.includes(el)))
    if (activeYear) result = result.filter((d) => String(d.event_year) === activeYear)

    const sorted = [...result]
    switch (activeSort) {
      case 'newest': sorted.sort((a, b) => (b.event_year || 0) - (a.event_year || 0) || b.cluster_size - a.cluster_size); break
      case 'oldest': sorted.sort((a, b) => (a.event_year || 9999) - (b.event_year || 9999) || b.cluster_size - a.cluster_size); break
      case 'alpha': sorted.sort((a, b) => (a.deck_name || '').localeCompare(b.deck_name || '')); break
      default: sorted.sort((a, b) => b.cluster_size - a.cluster_size || (a.deck_name || '').localeCompare(b.deck_name || ''))
    }
    return sorted
  }, [tournamentDecks, activeAvatar, activeElements, activeYear, activeSort])

  const filtersActive = activeAvatar !== 'all' || activeElements.size > 0 || !!activeYear

  // Auto-collapse staff picks when filters become active; reopen when cleared.
  useEffect(() => { setStaffPicksOpen(!filtersActive) }, [filtersActive])

  // Pagination
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const pagedDecks = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  // Reset page when filters change
  useEffect(() => { setPage(1) }, [activeAvatar, activeElements, activeYear, activeSort])

  const setFilter = useCallback((key, val) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (!val || val === 'all' || val === 'popular') next.delete(key)
      else next.set(key, val)
      return next
    }, { replace: true })
  }, [setSearchParams])

  const toggleElement = useCallback((el) => {
    const next = new Set(activeElements)
    if (next.has(el)) next.delete(el); else next.add(el)
    setFilter('element', next.size > 0 ? [...next].sort().join(',') : '')
  }, [activeElements, setFilter])

  const handleRemove = async (deck) => {
    if (!confirm(`Remove "${deck.deck_name}" from admin recommendations?`)) return
    try {
      await adminRemoveDeck(deck.deck_id)
      fetchData()
    } catch { alert('Failed to remove deck') }
  }

  const handleHide = async (deck) => {
    if (!confirm(`Hide "${deck.deck_name}" from public listing?`)) return
    try {
      await adminHideDeck(deck.deck_id)
      fetchData()
    } catch { alert('Failed to hide deck') }
  }

  const handleUnhide = async (deck) => {
    try {
      await adminUnhideDeck(deck.deck_id)
      fetchData()
    } catch { alert('Failed to unhide deck') }
  }

  if (error && !allDecks.length) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      {/* Hero */}
      <section className="text-center mb-6">
        <h1 className="text-4xl font-display text-secondary mb-2">Sorcery Deck Rec</h1>
        <p className="text-text-primary/80 text-sm max-w-xl mx-auto">
          Community-aggregated archetypes from tournament builds.<br />
          Click an archetype to see what cards players commonly run in that style.
        </p>
      </section>

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-4 mb-6 p-4 bg-bg-elevated rounded-lg border border-border">
        <AvatarSearch
          avatars={avatarNames}
          value={activeAvatar}
          onChange={(v) => setFilter('avatar', v)}
        />

        <div>
          <label className="text-sm text-text-primary font-medium block mb-1">Elements:</label>
          <div className="flex gap-1">
            {Object.entries(ELEMENT_ICONS).map(([el, icon]) => (
              <button
                key={el}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-sm border-2 transition-colors ${
                  activeElements.has(el) ? 'border-secondary/70 bg-bg-raised text-text-primary' : 'border-border text-text-primary hover:border-border/80 hover:bg-bg-raised'
                }`}
                onClick={() => toggleElement(el)}
              >
                <img src={`/avatar-images/${icon}`} alt={el} width={18} height={18} /> {el}
              </button>
            ))}
          </div>
        </div>

        {years.length > 0 && (
          <div>
            <label className="text-sm text-text-primary font-medium block mb-1">Year:</label>
            <select
              className="bg-bg-raised border border-border rounded px-2 py-1 text-sm"
              value={activeYear}
              onChange={(e) => setFilter('year', e.target.value)}
            >
              <option value="">All years</option>
              {years.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
        )}

        <div>
          <label className="text-sm text-text-primary font-medium block mb-1">Sort:</label>
          <select
            className="bg-bg-raised border border-border rounded px-2 py-1 text-sm"
            value={activeSort}
            onChange={(e) => setFilter('sort', e.target.value)}
          >
            <option value="popular">Most Popular</option>
            <option value="newest">Newest First</option>
            <option value="oldest">Oldest First</option>
            <option value="alpha">A - Z</option>
          </select>
        </div>

        {isAdmin && hiddenCount > 0 && (
          <div className="ml-auto">
            <label className="flex items-center gap-2 text-sm text-text-muted cursor-pointer select-none">
              <input
                type="checkbox"
                checked={showHidden}
                onChange={(e) => setShowHidden(e.target.checked)}
                className="accent-accent-red"
              />
              Show hidden ({hiddenCount})
            </label>
          </div>
        )}
      </div>

      {/* Admin Recommendations Accordion */}
      {(adminDecks.length > 0 || isAdmin) && (
        <section className="mb-6">
          <div className="rounded-lg border border-border bg-bg-elevated overflow-hidden">
            <button
              type="button"
              onClick={() => setStaffPicksOpen((v) => !v)}
              aria-expanded={staffPicksOpen}
              className="w-full flex items-center gap-3 px-4 py-3 hover:bg-bg-raised transition-colors"
            >
              <span className={`text-text-muted text-lg transition-transform ${staffPicksOpen ? 'rotate-90' : ''}`}>&#9656;</span>
              <h2 className="font-display text-text-primary text-xl">Summit Admin Recommendations</h2>
              <span className="text-xs font-semibold uppercase tracking-wider text-secondary border border-secondary/50 px-2 py-0.5 rounded">Staff Pick</span>
              <span className="text-sm text-text-muted">({adminDecks.length})</span>
              {isAdmin && (
                <span
                  role="button"
                  tabIndex={0}
                  className="ml-auto text-xs bg-secondary text-bg-base px-3 py-1 rounded hover:opacity-90 cursor-pointer"
                  onClick={(e) => { e.stopPropagation(); setEditDeck(null); setModalOpen(true) }}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); setEditDeck(null); setModalOpen(true) } }}
                >
                  + Add Deck
                </span>
              )}
            </button>
            {staffPicksOpen && (
              <div className="px-4 pb-4 pt-2 border-t border-border">
                {adminDecks.length > 0 ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                    {adminDecks.map((deck) => (
                      <DeckCard
                        key={deck.deck_id}
                        deck={deck}
                        imageFiles={imageFiles}
                        imageSettings={imageSettings}
                        isAdmin={isAdmin}
                        isAdminRec
                        onEdit={(d) => { setEditDeck(d); setModalOpen(true) }}
                        onRemove={handleRemove}
                        onHide={handleHide}
                        onUnhide={handleUnhide}
                        onImageSettingsSaved={handleImageSettingsSaved}
                      />
                    ))}
                  </div>
                ) : (
                  <p className="text-text-muted text-sm">No admin recommendations yet.</p>
                )}
              </div>
            )}
          </div>
        </section>
      )}

      {/* Tournament Archetypes */}
      <section>
        <h2 className="font-display text-text-primary text-2xl mb-4">Tournament Archetypes</h2>
        {decksLoading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {Array.from({ length: 8 }).map((_, i) => <DeckCardSkeleton key={i} />)}
          </div>
        ) : pagedDecks.length === 0 ? (
          <p className="text-text-muted text-sm py-8 text-center">No decks found for the selected filters.</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {pagedDecks.map((deck) => (
              <DeckCard
                key={deck.deck_id}
                deck={deck}
                imageFiles={imageFiles}
                imageSettings={imageSettings}
                isAdmin={isAdmin}
                onHide={handleHide}
                onUnhide={handleUnhide}
                onImageSettingsSaved={handleImageSettingsSaved}
              />
            ))}
          </div>
        )}

        {/* Pagination */}
        {!decksLoading && totalPages > 1 && (
          <div className="flex items-center justify-center gap-4 mt-6">
            <button
              className="text-sm text-text-primary hover:text-secondary disabled:opacity-30 disabled:hover:text-text-primary"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              &larr; Prev
            </button>
            <span className="text-sm text-text-primary">
              Page {page} of {totalPages} <span className="text-text-muted">({filtered.length} decks)</span>
            </span>
            <button
              className="text-sm text-text-primary hover:text-secondary disabled:opacity-30 disabled:hover:text-text-primary"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next &rarr;
            </button>
          </div>
        )}
      </section>

      {/* Admin Modal */}
      {isAdmin && (
        <AdminModal
          isOpen={modalOpen}
          onClose={() => setModalOpen(false)}
          onSubmit={fetchData}
          editDeck={editDeck}
        />
      )}
    </div>
  )
}
