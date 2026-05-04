import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { get } from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import CardImagePopup from '@/components/deck/CardImagePopup'
import usePageTitle from '@/hooks/usePageTitle'

export default function Creator() {
  usePageTitle('Creator Stats')
  const [cards, setCards] = useState([])
  const [filters, setFilters] = useState({ events: [] })
  const [eventFilter, setEventFilter] = useState('all')
  const [sourceFilter, setSourceFilter] = useState('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')
  const [elementFilter, setElementFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [hoverCard, setHoverCard] = useState({ image: null, rect: null })

  const handleHover = useCallback((image, rect) => setHoverCard({ image, rect }), [])
  const handleLeave = useCallback(() => setHoverCard({ image: null, rect: null }), [])

  useEffect(() => {
    get('/api/creator/filters')
      .then(setFilters)
      .catch(() => {})
  }, [])

  useEffect(() => {
    setLoading(true)
    setError(null)
    const params = new URLSearchParams({ source: sourceFilter })
    if (eventFilter !== 'all') params.set('event', eventFilter)
    get(`/api/creator/popular-cards?${params}`)
      .then(setCards)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [eventFilter, sourceFilter])

  const elements = [...new Set(cards.map((c) => c.element).filter((e) => e && e !== 'None'))].sort()
  const types = [...new Set(cards.map((c) => c.type).filter((t) => t && t !== 'Unknown'))].sort()

  const filtered = cards.filter((card) => {
    if (search && !card.name.toLowerCase().includes(search.toLowerCase())) return false
    if (elementFilter && card.element !== elementFilter) return false
    if (typeFilter && card.type !== typeFilter) return false
    return true
  })

  return (
    <div>
      <h1 className="text-2xl font-display text-secondary mb-2">Creator Stats</h1>
      <p className="text-text-muted text-sm mb-6">
        Card popularity data from reported matches. This data is exclusive to creators.
      </p>

      {/* Filters - same layout as Avatar Winrates */}
      <div className="flex flex-wrap justify-center gap-4 mb-6">
        <div className="flex items-center gap-2">
          <label className="text-sm text-text-muted">Event:</label>
          <select
            value={eventFilter}
            onChange={(e) => setEventFilter(e.target.value)}
            className="bg-bg-surface border border-border rounded px-2 py-1 text-sm"
          >
            <option value="all">All Events</option>
            {(filters.events || []).map((ev) => (
              <option key={ev.event_id} value={String(ev.event_id)}>
                {ev.event_name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-text-muted">Source:</label>
          <div className="inline-flex bg-bg-surface border border-border rounded-lg overflow-hidden">
            {[['discord', 'Online'], ['web', 'Paper']].map(([val, label]) => (
              <button
                key={val}
                className={`px-3 py-1 text-xs font-medium transition-colors ${sourceFilter === val ? 'bg-primary text-bg' : 'text-text-muted hover:text-text'}`}
                onClick={() => setSourceFilter(val)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Card-specific filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        <input
          type="text"
          placeholder="Search cards..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="bg-bg-surface border border-border rounded px-3 py-2 text-sm flex-1 min-w-[180px]"
        />
        <select
          value={elementFilter}
          onChange={(e) => setElementFilter(e.target.value)}
          className="bg-bg-surface border border-border rounded px-3 py-2 text-sm"
        >
          <option value="">All Elements</option>
          {elements.map((el) => (
            <option key={el} value={el}>{el}</option>
          ))}
        </select>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="bg-bg-surface border border-border rounded px-3 py-2 text-sm"
        >
          <option value="">All Types</option>
          {types.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>

      {loading && <Spinner className="py-20" />}
      {error && <p className="text-center text-accent-red py-8">{error}</p>}

      {!loading && !error && (
        <>
          <p className="text-xs text-text-muted mb-4">
            {filtered.length} cards from {cards.length > 0 ? cards[0].total_decks : 0} decks
          </p>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-text-muted">
                  <th className="py-2 px-3">Card</th>
                  <th className="py-2 px-3">Element</th>
                  <th className="py-2 px-3">Type</th>
                  <th className="py-2 px-3">Rarity</th>
                  <th className="py-2 px-3 text-right">% of Decks</th>
                  <th className="py-2 px-3 text-right">Avg Copies</th>
                  <th className="py-2 px-3 text-right">Total Copies</th>
                  <th className="py-2 px-3 text-right">Decks With</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((card) => (
                  <CardRow
                    key={card.name}
                    card={card}
                    onHover={handleHover}
                    onLeave={handleLeave}
                  />
                ))}
              </tbody>
            </table>
          </div>

          {filtered.length === 0 && (
            <p className="text-center text-text-muted py-8">
              {cards.length === 0 ? 'No card data available for this selection.' : 'No cards match your filters.'}
            </p>
          )}
        </>
      )}

      <CardImagePopup imageFile={hoverCard.image} anchorRect={hoverCard.rect} />
    </div>
  )
}

function CardRow({ card, onHover, onLeave }) {
  const handleMouseEnter = (e) => {
    if (card.image) {
      onHover(card.image, e.currentTarget.getBoundingClientRect())
    }
  }

  return (
    <tr
      className="border-b border-border/50 hover:bg-bg-surface/50"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={onLeave}
    >
      <td className="py-2 px-3">
        <Link
          to={`/card/${encodeURIComponent(card.name)}`}
          className="text-primary hover:text-primary-light transition-colors font-medium"
        >
          {card.name}
        </Link>
      </td>
      <td className="py-2 px-3">{card.element}</td>
      <td className="py-2 px-3">{card.type}</td>
      <td className="py-2 px-3">{card.rarity}</td>
      <td className="py-2 px-3 text-right font-mono">{card.percent_of_decks}%</td>
      <td className="py-2 px-3 text-right font-mono">{card.average_played}</td>
      <td className="py-2 px-3 text-right font-mono">{card.count}</td>
      <td className="py-2 px-3 text-right font-mono">{card.decks_with_card}</td>
    </tr>
  )
}
