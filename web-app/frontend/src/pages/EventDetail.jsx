import { useState, useEffect, useMemo, useCallback } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { getEvent, updateEventMetadata, updateEventDecks, refreshEvent, deleteEvent } from '@/api/events'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

const ELEMENT_COLORS = {
  Fire: { label: 'text-red-400', bar: 'from-red-500 to-red-700' },
  Water: { label: 'text-blue-400', bar: 'from-blue-400 to-blue-600' },
  Earth: { label: 'text-amber-700', bar: 'from-amber-700 to-amber-900' },
  Air: { label: 'text-sky-300', bar: 'from-sky-300 to-sky-500' },
}

const RARITY_CLASSES = {
  unique: 'bg-yellow-500/20 text-yellow-400',
  elite: 'bg-purple-500/20 text-purple-400',
  exceptional: 'bg-blue-500/20 text-blue-400',
  ordinary: 'bg-gray-500/20 text-gray-400',
}

const PLACE_CLASSES = [
  'bg-gradient-to-r from-yellow-400 to-yellow-300 text-black',
  'bg-gradient-to-r from-gray-300 to-gray-200 text-black',
  'bg-gradient-to-r from-amber-600 to-amber-500 text-white',
]

/* ---- Element Bar Chart ---- */
function ElementChart({ title, subtitle, data, totalDecks }) {
  if (!data?.length) return null
  const sorted = [...data].sort((a, b) => b.percent - a.percent)
  return (
    <div className="bg-bg-surface border border-border rounded-lg p-4 flex-1">
      <h3 className="text-center font-semibold text-text-primary mb-0.5">{title}</h3>
      <p className="text-center text-xs text-text-muted mb-4">{subtitle}</p>
      <div className="space-y-3">
        {sorted.map((el) => {
          const colors = ELEMENT_COLORS[el.name] || {}
          return (
            <div key={el.name} className="flex items-center gap-3">
              <span className={`w-14 font-bold text-sm ${colors.label || ''}`}>{el.name}</span>
              <div className="flex-1 h-7 bg-white/10 rounded overflow-hidden relative">
                <div
                  className={`h-full rounded bg-gradient-to-r ${colors.bar || 'from-gray-500 to-gray-600'} flex items-center justify-end pr-2 transition-all duration-700`}
                  style={{ width: `${Math.max(el.percent, 5)}%` }}
                >
                  <span className="text-xs font-bold text-white drop-shadow">{el.percent}%</span>
                </div>
              </div>
              <span className="w-24 text-right text-xs text-text-muted">{el.count} / {totalDecks} decks</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ---- Comparison Bar Chart (Top 8 vs All Participants) ---- */
function ComparisonChart({ title, subtitle, top8Data, allData, top8Total, allTotal }) {
  if (!top8Data?.length || !allData?.length) return null
  const elements = ["Fire", "Water", "Earth", "Air"]
  const top8Map = Object.fromEntries(top8Data.map((d) => [d.name, d]))
  const allMap = Object.fromEntries(allData.map((d) => [d.name, d]))

  // Sort by top8 percent descending
  const sorted = [...elements].sort((a, b) => (top8Map[b]?.percent || 0) - (top8Map[a]?.percent || 0))

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-4 flex-1">
      <h3 className="text-center font-semibold text-text-primary mb-0.5">{title}</h3>
      <p className="text-center text-xs text-text-muted mb-4">{subtitle}</p>
      <div className="space-y-4">
        {sorted.map((el) => {
          const colors = ELEMENT_COLORS[el] || {}
          const t8 = top8Map[el] || { percent: 0, count: 0 }
          const all = allMap[el] || { percent: 0, count: 0 }
          return (
            <div key={el} className="space-y-1">
              <span className={`font-bold text-sm ${colors.label || ''}`}>{el}</span>
              <div className="flex items-center gap-2">
                <span className="w-20 text-xs text-yellow-400 font-semibold">Top 8</span>
                <div className="flex-1 h-5 bg-white/10 rounded overflow-hidden">
                  <div
                    className={`h-full rounded bg-gradient-to-r ${colors.bar || 'from-gray-500 to-gray-600'} flex items-center justify-end pr-2 transition-all duration-700`}
                    style={{ width: `${Math.max(t8.percent, 3)}%` }}
                  >
                    <span className="text-[10px] font-bold text-white drop-shadow">{t8.percent}%</span>
                  </div>
                </div>
                <span className="w-20 text-right text-[10px] text-text-muted">{t8.count}/{top8Total}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-20 text-xs text-text-muted">All</span>
                <div className="flex-1 h-5 bg-white/10 rounded overflow-hidden">
                  <div
                    className={`h-full rounded bg-gradient-to-r ${colors.bar || 'from-gray-500 to-gray-600'} opacity-50 flex items-center justify-end pr-2 transition-all duration-700`}
                    style={{ width: `${Math.max(all.percent, 3)}%` }}
                  >
                    <span className="text-[10px] font-bold text-white drop-shadow">{all.percent}%</span>
                  </div>
                </div>
                <span className="w-20 text-right text-[10px] text-text-muted">{all.count}/{allTotal}</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ---- Deck Table ---- */
function DeckTable({ decks, isAdmin, tableType, eventFolder, onReorder }) {
  const [dragIdx, setDragIdx] = useState(null)

  if (!decks?.length) return null

  const handleDragStart = (idx) => setDragIdx(idx)
  const handleDragOver = (e) => e.preventDefault()
  const handleDrop = (targetIdx) => {
    if (dragIdx === null || dragIdx === targetIdx) return
    const reordered = [...decks]
    const [moved] = reordered.splice(dragIdx, 1)
    reordered.splice(targetIdx, 0, moved)
    onReorder(tableType, reordered)
    setDragIdx(null)
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-white/10">
            {isAdmin && <th className="py-3 px-4 text-left w-10"></th>}
            <th className="py-3 px-4 text-left font-semibold">Player</th>
            <th className="py-3 px-4 text-left font-semibold">Avatar</th>
            <th className="py-3 px-4 text-left font-semibold">Deck</th>
            <th className="py-3 px-4 text-left font-semibold w-36">Deck List</th>
          </tr>
        </thead>
        <tbody>
          {decks.map((deck, idx) => {
            const placeClass = tableType === 'top8' && idx < 3 ? PLACE_CLASSES[idx] : ''
            return (
              <tr
                key={idx}
                className="border-t border-border/30 hover:bg-white/5"
                draggable={isAdmin}
                onDragStart={() => handleDragStart(idx)}
                onDragOver={handleDragOver}
                onDrop={() => handleDrop(idx)}
              >
                {isAdmin && (
                  <td className="py-3 px-4 cursor-grab text-text-muted text-center select-none">⠁⠁</td>
                )}
                <td className="py-3 px-4">{deck.player}</td>
                <td className="py-3 px-4">{deck.avatar}</td>
                <td className="py-3 px-4">{deck.deck_name}</td>
                <td className="py-3 px-4">
                  {deck.deck_id ? (
                    <Link
                      to={`/deck-rec/${deck.deck_id}`}
                      className="text-secondary border border-secondary rounded px-3 py-1 text-xs hover:bg-secondary hover:text-black transition-colors"
                    >
                      Deck List
                    </Link>
                  ) : null}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/* ---- Card Stats Table ---- */
function CardStatsTable({ cardData, top8CardData }) {
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [elementFilter, setElementFilter] = useState('')
  const [sortCol, setSortCol] = useState(null)
  const [sortDir, setSortDir] = useState('asc')

  const hasComparison = top8CardData?.length > 0 && cardData?.length > 0

  // Build lookup of top8 card stats by name
  const top8Map = useMemo(() => {
    if (!hasComparison) return {}
    return Object.fromEntries(top8CardData.map((c) => [c.name, c]))
  }, [top8CardData, hasComparison])

  // Merge top8 data into card data for display
  const mergedData = useMemo(() => {
    if (!hasComparison) return cardData
    return cardData.map((c) => ({
      ...c,
      top8_deck_percent: top8Map[c.name]?.deck_percent || '0',
    }))
  }, [cardData, top8Map, hasComparison])

  const types = useMemo(() => [...new Set(mergedData.map((c) => c.type))].sort(), [mergedData])
  const elements = useMemo(() => [...new Set(mergedData.map((c) => c.element))].sort(), [mergedData])

  const filtered = useMemo(() => {
    let result = mergedData
    if (search) {
      const q = search.toLowerCase()
      result = result.filter((c) => c.name.toLowerCase().includes(q))
    }
    if (typeFilter) result = result.filter((c) => c.type === typeFilter)
    if (elementFilter) result = result.filter((c) => c.element === elementFilter)

    if (sortCol) {
      result = [...result].sort((a, b) => {
        let av = a[sortCol], bv = b[sortCol]
        if (typeof av === 'string') {
          av = av.toLowerCase(); bv = bv.toLowerCase()
        } else {
          av = parseFloat(av) || 0; bv = parseFloat(bv) || 0
        }
        if (av < bv) return sortDir === 'asc' ? -1 : 1
        if (av > bv) return sortDir === 'asc' ? 1 : -1
        return 0
      })
    }
    return result
  }, [mergedData, search, typeFilter, elementFilter, sortCol, sortDir])

  const handleSort = (col) => {
    if (sortCol === col) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortCol(col)
      setSortDir('asc')
    }
  }

  const sortIcon = (col) => {
    if (sortCol !== col) return <span className="text-text-muted/40 ml-1">⇅</span>
    return <span className="text-secondary ml-1">{sortDir === 'asc' ? '▲' : '▼'}</span>
  }

  const colSpan = hasComparison ? 9 : 7

  return (
    <div>
      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-3">
        <input
          type="text"
          placeholder="Search cards..."
          className="flex-1 min-w-[200px] bg-bg-raised border border-border rounded-lg px-3 py-2 text-sm"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="bg-bg-raised border border-border rounded-lg px-3 py-2 text-sm"
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
        >
          <option value="">All Types</option>
          {types.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select
          className="bg-bg-raised border border-border rounded-lg px-3 py-2 text-sm"
          value={elementFilter}
          onChange={(e) => setElementFilter(e.target.value)}
        >
          <option value="">All Elements</option>
          {elements.map((e) => <option key={e} value={e}>{e}</option>)}
        </select>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-white/10">
              <th className="py-3 px-3 text-left font-semibold cursor-pointer select-none" onClick={() => handleSort('name')}>
                Card Name{sortIcon('name')}
              </th>
              <th className="py-3 px-3 text-left font-semibold cursor-pointer select-none" onClick={() => handleSort('type')}>
                Type{sortIcon('type')}
              </th>
              <th className="py-3 px-3 text-left font-semibold cursor-pointer select-none" onClick={() => handleSort('element')}>
                Element{sortIcon('element')}
              </th>
              <th className="py-3 px-3 text-left font-semibold cursor-pointer select-none" onClick={() => handleSort('rarity')}>
                Rarity{sortIcon('rarity')}
              </th>
              <th className="py-3 px-3 text-left font-semibold cursor-pointer select-none w-24" onClick={() => handleSort('count')}>
                Total{sortIcon('count')}
              </th>
              <th className="py-3 px-3 text-left font-semibold cursor-pointer select-none w-24 hidden sm:table-cell" onClick={() => handleSort('avg_played')}>
                Avg{sortIcon('avg_played')}
              </th>
              <th className="py-3 px-3 text-left font-semibold cursor-pointer select-none w-24 hidden sm:table-cell" onClick={() => handleSort('deck_percent')}>
                {hasComparison ? 'All %' : '% Decks'}{sortIcon('deck_percent')}
              </th>
              {hasComparison && (
                <>
                  <th className="py-3 px-3 text-left font-semibold cursor-pointer select-none w-28 hidden sm:table-cell" onClick={() => handleSort('top8_deck_percent')}>
                    <span className="text-yellow-400">Top 8 %</span>{sortIcon('top8_deck_percent')}
                  </th>
                  <th className="py-3 px-3 text-left font-semibold w-16 hidden sm:table-cell">
                    <span className="text-text-muted">Diff</span>
                  </th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {filtered.map((card) => {
              const rarityClass = RARITY_CLASSES[card.rarity?.toLowerCase()] || 'bg-gray-500/20 text-gray-400'
              const allPct = parseFloat(card.deck_percent) || 0
              const top8Pct = parseFloat(card.top8_deck_percent) || 0
              const diff = hasComparison ? top8Pct - allPct : 0
              return (
                <tr key={card.name} className="border-t border-border/30 hover:bg-white/5">
                  <td className="py-2.5 px-3">{card.name}</td>
                  <td className="py-2.5 px-3">{card.type}</td>
                  <td className="py-2.5 px-3">{card.element}</td>
                  <td className="py-2.5 px-3">
                    <span className={`text-xs px-2 py-0.5 rounded ${rarityClass}`}>{card.rarity}</span>
                  </td>
                  <td className="py-2.5 px-3">
                    <span className="bg-yellow-500/20 text-yellow-400 px-2 py-0.5 rounded font-semibold text-xs">{card.count}</span>
                  </td>
                  <td className="py-2.5 px-3 font-semibold text-secondary hidden sm:table-cell">{card.avg_played}</td>
                  <td className="py-2.5 px-3 font-semibold text-secondary hidden sm:table-cell">{card.deck_percent}%</td>
                  {hasComparison && (
                    <>
                      <td className="py-2.5 px-3 font-semibold text-yellow-400 hidden sm:table-cell">{top8Pct}%</td>
                      <td className="py-2.5 px-3 font-semibold hidden sm:table-cell">
                        {diff !== 0 && (
                          <span className={diff > 0 ? 'text-green-400' : 'text-red-400'}>
                            {diff > 0 ? '+' : ''}{diff}
                          </span>
                        )}
                      </td>
                    </>
                  )}
                </tr>
              )
            })}
            {filtered.length === 0 && (
              <tr><td colSpan={colSpan} className="py-6 text-center text-text-muted">No cards match your filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/* ---- Main Page ---- */
export default function EventDetail() {
  const { folder } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [reorderDirty, setReorderDirty] = useState({})
  const [originalOrder, setOriginalOrder] = useState({}) // { top8: [...originalDecks], all: [...originalDecks] }
  const [saving, setSaving] = useState(null)
  const [editingDesc, setEditingDesc] = useState(false)
  const [descDraft, setDescDraft] = useState('')
  const [savingDesc, setSavingDesc] = useState(false)
  const [deckModal, setDeckModal] = useState(null) // { table: 'top8'|'all', mode: 'replace'|'append' }
  const [deckUrls, setDeckUrls] = useState('')
  const [deckSaving, setDeckSaving] = useState(false)
  const [deckError, setDeckError] = useState(null)
  const [deckResult, setDeckResult] = useState(null) // { decks_added, warnings }
  const [refreshing, setRefreshing] = useState(false)
  const [refreshResult, setRefreshResult] = useState(null)
  const [deleteConfirm, setDeleteConfirm] = useState(false)
  const [deleting, setDeleting] = useState(false)

  usePageTitle(data?.event_name || 'Event Detail')

  useEffect(() => {
    setLoading(true)
    getEvent(folder)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [folder])

  const handleReorder = useCallback((tableType, newOrder) => {
    const key = tableType === 'top8' ? 'top8_decks' : 'all_decks'
    setOriginalOrder((prev) => {
      // Snapshot the original order before the first drag
      if (!prev[tableType]) return { ...prev, [tableType]: data[key] }
      return prev
    })
    setData((prev) => ({
      ...prev,
      [key]: newOrder,
    }))
    setReorderDirty((prev) => ({ ...prev, [tableType]: true }))
  }, [data])

  const saveOrder = useCallback(async (tableType) => {
    const key = tableType === 'top8' ? 'top8_decks' : 'all_decks'
    const currentDecks = data[key]
    const original = originalOrder[tableType] || currentDecks
    // Build order: for each position in the new list, find where that deck was in the original
    const order = currentDecks.map((deck) => original.indexOf(deck))
    setSaving(tableType)
    try {
      const res = await fetch(`/api/events/${encodeURIComponent(folder)}/reorder`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ table: tableType, order }),
      })
      const result = await res.json()
      if (result.success) {
        setReorderDirty((prev) => ({ ...prev, [tableType]: false }))
        setOriginalOrder((prev) => ({ ...prev, [tableType]: null }))
      }
    } catch { /* ignore */ }
    finally { setSaving(null) }
  }, [data, folder, originalOrder])

  const openDeckModal = (table, mode) => {
    setDeckModal({ table, mode })
    setDeckUrls('')
    setDeckError(null)
    setDeckResult(null)
  }

  const handleDeckSubmit = useCallback(async () => {
    if (!deckModal) return
    const urls = deckUrls.split('\n').map((u) => u.trim()).filter(Boolean)
    if (!urls.length) return
    setDeckSaving(true)
    setDeckError(null)
    setDeckResult(null)
    try {
      const result = await updateEventDecks(folder, {
        table: deckModal.table,
        mode: deckModal.mode,
        urls,
      })
      if (result.success) {
        // Reload event data
        const fresh = await getEvent(folder)
        setData(fresh)
        // Show result summary (warnings or counts) before closing
        if (result.warnings?.length) {
          setDeckResult(result)
          setDeckUrls('')
        } else {
          setDeckModal(null)
        }
      } else {
        setDeckError(result.error || 'Failed to update decks')
      }
    } catch (err) {
      setDeckError(err.message || 'Failed to update decks')
    } finally {
      setDeckSaving(false)
    }
  }, [deckModal, deckUrls, folder])

  const handleRefresh = useCallback(async () => {
    setRefreshing(true)
    setRefreshResult(null)
    try {
      const result = await refreshEvent(folder)
      if (result.success) {
        const fresh = await getEvent(folder)
        setData(fresh)
        setRefreshResult(result)
      }
    } catch { /* ignore */ }
    finally { setRefreshing(false) }
  }, [folder])

  const handleDelete = useCallback(async () => {
    setDeleting(true)
    try {
      const result = await deleteEvent(folder)
      if (result.success) {
        navigate('/top-8')
      }
    } catch { /* ignore */ }
    finally { setDeleting(false) }
  }, [folder, navigate])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>
  if (!data) return null

  const { event_name, top8_decks, all_decks, card_data, top8_card_data, element_stats, element_stats_by_group, is_admin, description } = data
  const hasComparison = element_stats_by_group?.top8 && element_stats_by_group?.all

  const saveDescription = async () => {
    setSavingDesc(true)
    try {
      const result = await updateEventMetadata(folder, { description: descDraft })
      if (result.success) {
        setData((prev) => ({ ...prev, description: descDraft }))
        setEditingDesc(false)
      }
    } catch { /* ignore */ }
    finally { setSavingDesc(false) }
  }

  // Convert URLs in description text to clickable links
  const renderDescription = (text) => {
    if (!text) return null
    const urlRegex = /(https?:\/\/[^\s]+)/g
    const parts = text.split(urlRegex)
    return parts.map((part, i) =>
      urlRegex.test(part) ? (
        <a key={i} href={part} target="_blank" rel="noopener noreferrer" className="text-secondary hover:underline break-all">{part}</a>
      ) : (
        <span key={i}>{part}</span>
      )
    )
  }

  return (
    <div className="space-y-6">
      <Link to="/top-8" className="text-sm text-secondary hover:underline">&larr; Back to Events</Link>

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-display text-text-primary">{event_name}</h1>
        {is_admin && (
          <div className="flex gap-2">
            <button
              className="text-xs bg-bg-raised text-text-muted px-3 py-1.5 rounded border border-border hover:text-text disabled:opacity-50"
              onClick={handleRefresh}
              disabled={refreshing}
            >
              {refreshing ? 'Refreshing...' : 'Refresh from Curiosa'}
            </button>
            <button
              className="text-xs bg-accent-red/20 text-accent-red px-3 py-1.5 rounded border border-accent-red/30 hover:bg-accent-red/30 disabled:opacity-50"
              onClick={() => setDeleteConfirm(true)}
            >
              Delete Event
            </button>
          </div>
        )}
      </div>

      {refreshResult && (
        <div className="p-3 bg-bg-surface rounded-lg border border-border">
          <p className="text-xs text-green-400">
            {refreshResult.refreshed} deck{refreshResult.refreshed !== 1 ? 's' : ''} refreshed from Curiosa.
          </p>
          {refreshResult.warnings?.length > 0 && (
            <div className="mt-1">
              <p className="text-xs text-yellow-400">{refreshResult.warnings.length} warning{refreshResult.warnings.length !== 1 ? 's' : ''}:</p>
              <ul className="text-xs text-text-muted space-y-0.5 mt-0.5">
                {refreshResult.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Description */}
      {(description || is_admin) && (
        <div className="bg-bg-surface border border-border rounded-lg p-4">
          {description && !editingDesc && (
            <p className="text-text-secondary text-sm whitespace-pre-wrap">{renderDescription(description)}</p>
          )}
          {is_admin && !editingDesc && (
            <button
              className="text-xs text-secondary hover:underline mt-2"
              onClick={() => { setDescDraft(description || ''); setEditingDesc(true) }}
            >
              {description ? 'Edit Description' : 'Add Description'}
            </button>
          )}
          {editingDesc && (
            <div className="space-y-2">
              <textarea
                className="w-full bg-bg-raised border border-border rounded-lg px-3 py-2 text-sm text-text-primary min-h-[80px]"
                value={descDraft}
                onChange={(e) => setDescDraft(e.target.value)}
                placeholder="Event description (URLs will become clickable links)..."
              />
              <div className="flex gap-2">
                <button
                  className="text-xs bg-secondary text-black px-3 py-1 rounded font-semibold disabled:opacity-50"
                  onClick={saveDescription}
                  disabled={savingDesc}
                >
                  {savingDesc ? 'Saving...' : 'Save'}
                </button>
                <button
                  className="text-xs bg-bg-raised text-text-muted px-3 py-1 rounded border border-border"
                  onClick={() => setEditingDesc(false)}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Element Charts */}
      {element_stats && (
        <div className="flex flex-col md:flex-row gap-4">
          <ElementChart
            title="Dominant Element"
            subtitle="Element with the most cards in each deck's spellbook"
            data={element_stats.dominant_element}
            totalDecks={element_stats.total_decks}
          />
          <ElementChart
            title="Element Presence"
            subtitle="% of decks containing at least one card of each element"
            data={element_stats.element_presence}
            totalDecks={element_stats.total_decks}
          />
        </div>
      )}

      {/* Top 8 vs All Participants Comparison Charts */}
      {hasComparison && (
        <section>
          <h2 className="text-lg font-semibold text-text-primary border-b-2 border-border pb-1 mb-3">Top 8 vs All Participants</h2>
          <div className="flex flex-col md:flex-row gap-4">
            <ComparisonChart
              title="Dominant Element Comparison"
              subtitle="Top 8 vs All Participants — element with most cards per deck"
              top8Data={element_stats_by_group.top8.dominant_element}
              allData={element_stats_by_group.all.dominant_element}
              top8Total={element_stats_by_group.top8.total_decks}
              allTotal={element_stats_by_group.all.total_decks}
            />
            <ComparisonChart
              title="Element Presence Comparison"
              subtitle="Top 8 vs All Participants — % of decks with at least one card"
              top8Data={element_stats_by_group.top8.element_presence}
              allData={element_stats_by_group.all.element_presence}
              top8Total={element_stats_by_group.top8.total_decks}
              allTotal={element_stats_by_group.all.total_decks}
            />
          </div>
        </section>
      )}

      {/* Top 8 */}
      {(top8_decks?.length > 0 || is_admin) && (
        <section>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-lg font-semibold text-text-primary border-b-2 border-border pb-1">Top 8</h2>
            <div className="flex gap-2">
              {is_admin && (
                <>
                  <button
                    className="text-xs bg-primary text-black px-2 py-1 rounded font-semibold"
                    onClick={() => openDeckModal('top8', top8_decks?.length ? 'append' : 'replace')}
                  >
                    + Add Decks
                  </button>
                  {top8_decks?.length > 0 && (
                    <button
                      className="text-xs bg-bg-raised text-text-muted px-2 py-1 rounded border border-border hover:text-text"
                      onClick={() => openDeckModal('top8', 'replace')}
                    >
                      Replace List
                    </button>
                  )}
                </>
              )}
              {is_admin && reorderDirty.top8 && (
                <button
                  className="text-xs bg-secondary text-black px-3 py-1 rounded font-semibold disabled:opacity-50"
                  onClick={() => saveOrder('top8')}
                  disabled={saving === 'top8'}
                >
                  {saving === 'top8' ? 'Saving...' : 'Save Order'}
                </button>
              )}
            </div>
          </div>
          {top8_decks?.length > 0 && (
            <div className="bg-bg-surface border border-border rounded-lg overflow-hidden">
              <DeckTable
                decks={top8_decks}
                isAdmin={is_admin}
                tableType="top8"
                eventFolder={folder}
                onReorder={handleReorder}
              />
            </div>
          )}
        </section>
      )}

      {/* All Participants */}
      {(all_decks?.length > 0 || is_admin) && (
        <section>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-lg font-semibold text-text-primary border-b-2 border-border pb-1">All Participants</h2>
            <div className="flex gap-2">
              {is_admin && (
                <>
                  <button
                    className="text-xs bg-primary text-black px-2 py-1 rounded font-semibold"
                    onClick={() => openDeckModal('all', all_decks?.length ? 'append' : 'replace')}
                  >
                    + Add Decks
                  </button>
                  {all_decks?.length > 0 && (
                    <button
                      className="text-xs bg-bg-raised text-text-muted px-2 py-1 rounded border border-border hover:text-text"
                      onClick={() => openDeckModal('all', 'replace')}
                    >
                      Replace List
                    </button>
                  )}
                </>
              )}
              {is_admin && reorderDirty.all && (
                <button
                  className="text-xs bg-secondary text-black px-3 py-1 rounded font-semibold disabled:opacity-50"
                  onClick={() => saveOrder('all')}
                  disabled={saving === 'all'}
                >
                  {saving === 'all' ? 'Saving...' : 'Save Order'}
                </button>
              )}
            </div>
          </div>
          {all_decks?.length > 0 && (
            <div className="bg-bg-surface border border-border rounded-lg overflow-hidden">
              <DeckTable
                decks={all_decks}
                isAdmin={is_admin}
                tableType="all"
                eventFolder={folder}
                onReorder={handleReorder}
              />
            </div>
          )}
        </section>
      )}

      {/* Card Usage Statistics */}
      {card_data?.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-text-primary border-b-2 border-border pb-1 mb-3">Card Usage Statistics</h2>
          <div className="bg-bg-surface border border-border rounded-lg p-4">
            <CardStatsTable cardData={card_data} top8CardData={top8_card_data} />
          </div>
        </section>
      )}

      {/* No data at all */}
      {!top8_decks?.length && !all_decks?.length && !card_data?.length && !is_admin && (
        <p className="text-center text-text-muted py-8">No data available for this event.</p>
      )}

      {/* Deck Management Modal */}
      {deckModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setDeckModal(null)}>
          <div className="bg-bg-surface border border-border rounded-lg p-6 w-full max-w-lg mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-display text-secondary mb-1">
              {deckModal.mode === 'replace' ? 'Replace' : 'Add to'} {deckModal.table === 'top8' ? 'Top 8' : 'All Participants'}
            </h3>
            <p className="text-xs text-text-muted mb-4">
              {deckModal.mode === 'replace'
                ? 'This will replace all existing decks in this list.'
                : 'New decks will be appended to the existing list.'}
            </p>

            <label className="text-xs text-text-muted block mb-1">Curiosa Deck URLs (one per line)</label>
            <textarea
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-4 min-h-[120px]"
              placeholder={"https://curiosa.io/decks/...\nhttps://curiosa.io/decks/..."}
              value={deckUrls}
              onChange={(e) => setDeckUrls(e.target.value)}
            />

            {deckError && (
              <p className="text-accent-red text-xs mb-3">{deckError}</p>
            )}

            {deckResult && (
              <div className="mb-3 p-3 bg-bg-raised rounded border border-border">
                <p className="text-xs text-green-400 mb-1">{deckResult.decks_added} deck{deckResult.decks_added !== 1 ? 's' : ''} added successfully.</p>
                {deckResult.warnings?.length > 0 && (
                  <div className="mt-1">
                    <p className="text-xs text-yellow-400 mb-1">Failed to fetch {deckResult.warnings.length} URL{deckResult.warnings.length !== 1 ? 's' : ''}:</p>
                    <ul className="text-xs text-text-muted space-y-0.5">
                      {deckResult.warnings.map((w, i) => <li key={i} className="truncate">{w}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button
                className="text-xs px-3 py-1.5 rounded border border-border text-text-muted hover:text-text"
                onClick={() => setDeckModal(null)}
              >
                {deckResult ? 'Done' : 'Cancel'}
              </button>
              {!deckResult && (
              <button
                className={`text-xs px-3 py-1.5 rounded font-semibold disabled:opacity-50 ${
                  deckModal.mode === 'replace' ? 'bg-accent-red text-white' : 'bg-secondary text-black'
                }`}
                onClick={handleDeckSubmit}
                disabled={deckSaving || !deckUrls.trim()}
              >
                {deckSaving ? 'Saving...' : deckModal.mode === 'replace' ? 'Replace Decks' : 'Add Decks'}
              </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setDeleteConfirm(false)}>
          <div className="bg-bg-surface border border-border rounded-lg p-6 w-full max-w-sm mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-display text-accent-red mb-2">Delete Event</h3>
            <p className="text-sm text-text-muted mb-4">
              Are you sure you want to delete <span className="font-semibold text-text-primary">{event_name}</span>? This will permanently remove all deck data, statistics, and metadata for this event.
            </p>
            <div className="flex justify-end gap-2">
              <button
                className="text-xs px-3 py-1.5 rounded border border-border text-text-muted hover:text-text"
                onClick={() => setDeleteConfirm(false)}
              >
                Cancel
              </button>
              <button
                className="text-xs bg-accent-red text-white px-3 py-1.5 rounded font-semibold disabled:opacity-50"
                onClick={handleDelete}
                disabled={deleting}
              >
                {deleting ? 'Deleting...' : 'Delete Permanently'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
