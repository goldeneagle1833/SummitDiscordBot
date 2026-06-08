import { useState, useEffect, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import { get } from '@/api/client'
import { getCreatorAccess, addCreatorAccess, removeCreatorAccess, searchUsers } from '@/api/admin'
import { useAuth } from '@/context/AuthContext'
import Spinner from '@/components/ui/Spinner'
import CardImagePopup from '@/components/deck/CardImagePopup'
import usePageTitle from '@/hooks/usePageTitle'

export default function Creator() {
  usePageTitle('Creator Stats')
  const { user } = useAuth()
  const isAdmin = user?.is_admin

  const [cards, setCards] = useState([])
  const [filters, setFilters] = useState({ events: [] })
  const [eventFilter, setEventFilter] = useState('all')
  const [sourceFilter, setSourceFilter] = useState('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')
  const [elementFilter, setElementFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [collectionOnly, setCollectionOnly] = useState(false)
  const [sortKey, setSortKey] = useState('percent_of_decks')
  const [sortDir, setSortDir] = useState('desc')
  const [expandedCard, setExpandedCard] = useState(null)
  const [hoverCard, setHoverCard] = useState({ image: null, rect: null })

  // Admin: creator access management
  const [accessList, setAccessList] = useState([])
  const [accessLoading, setAccessLoading] = useState(false)
  const [userQuery, setUserQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [actionMsg, setActionMsg] = useState(null)
  const searchTimeout = useRef(null)

  useEffect(() => {
    if (!isAdmin) return
    setAccessLoading(true)
    getCreatorAccess()
      .then((d) => setAccessList(d.users || []))
      .catch(() => {})
      .finally(() => setAccessLoading(false))
  }, [isAdmin])

  const handleUserSearch = (q) => {
    setUserQuery(q)
    setSearchResults([])
    clearTimeout(searchTimeout.current)
    if (q.length < 2) return
    searchTimeout.current = setTimeout(() => {
      setSearching(true)
      searchUsers(q)
        .then((d) => setSearchResults(d.users || []))
        .catch(() => {})
        .finally(() => setSearching(false))
    }, 300)
  }

  const handleAdd = async (u) => {
    setActionMsg(null)
    try {
      await addCreatorAccess(u.user_id, u.display_name)
      setAccessList((prev) => [...prev, { user_id: u.user_id, display_name: u.display_name }].sort((a, b) => a.display_name.localeCompare(b.display_name)))
      setUserQuery('')
      setSearchResults([])
      setActionMsg({ type: 'ok', text: `Added ${u.display_name}` })
    } catch {
      setActionMsg({ type: 'err', text: 'Failed to add user' })
    }
  }

  const handleRemove = async (userId, displayName) => {
    setActionMsg(null)
    try {
      await removeCreatorAccess(userId)
      setAccessList((prev) => prev.filter((u) => u.user_id !== userId))
      setActionMsg({ type: 'ok', text: `Removed ${displayName}` })
    } catch {
      setActionMsg({ type: 'err', text: 'Failed to remove user' })
    }
  }

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

  const handleSort = (key) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir(key === 'name' ? 'asc' : 'desc')
    }
  }

  const filtered = cards.filter((card) => {
    if (search && !card.name.toLowerCase().includes(search.toLowerCase())) return false
    if (elementFilter && card.element !== elementFilter) return false
    if (typeFilter && card.type !== typeFilter) return false
    if (collectionOnly && !card.sideboard_count) return false
    return true
  })

  const sorted = [...filtered].sort((a, b) => {
    let aVal = a[sortKey]
    let bVal = b[sortKey]
    if (typeof aVal === 'string') {
      aVal = (aVal || '').toLowerCase()
      bVal = (bVal || '').toLowerCase()
      return sortDir === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal)
    }
    return sortDir === 'asc' ? (aVal || 0) - (bVal || 0) : (bVal || 0) - (aVal || 0)
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
        <div className="flex items-center gap-2">
          <button
            className={`px-3 py-1 text-xs font-medium rounded-lg border transition-colors ${collectionOnly ? 'bg-primary text-bg border-primary' : 'bg-bg-surface text-text-muted border-border hover:text-text'}`}
            onClick={() => setCollectionOnly((v) => !v)}
          >
            Collection Only
          </button>
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
                  {[
                    { key: 'name', label: 'Card' },
                    { key: 'element', label: 'Element' },
                    { key: 'type', label: 'Type' },
                    { key: 'rarity', label: 'Rarity' },
                    { key: 'percent_of_decks', label: '% of Decks', right: true },
                    { key: 'average_played', label: 'Avg Copies', right: true },
                    { key: 'count', label: 'Total Copies', right: true },
                    { key: 'sideboard_count', label: 'Collection', right: true },
                    { key: 'decks_with_card', label: 'Decks With', right: true },
                  ].map((col) => (
                    <th
                      key={col.key}
                      className={`py-2 px-3 cursor-pointer select-none hover:text-text ${col.right ? 'text-right' : ''}`}
                      onClick={() => handleSort(col.key)}
                    >
                      {col.label}
                      {sortKey === col.key && (
                        <span className="ml-1">{sortDir === 'asc' ? '▲' : '▼'}</span>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sorted.map((card) => (
                  <CardRow
                    key={card.name}
                    card={card}
                    expanded={expandedCard === card.name}
                    onToggle={() => setExpandedCard(expandedCard === card.name ? null : card.name)}
                    sourceFilter={sourceFilter}
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

      {isAdmin && (
        <div className="mt-10 border border-border rounded-lg p-5 bg-bg-raised">
          <h2 className="text-base font-semibold text-text-primary mb-1">Creator Access</h2>
          <p className="text-xs text-text-muted mb-4">
            Grant or revoke creator page access for specific users.
          </p>

          {actionMsg && (
            <p className={`text-xs mb-3 ${actionMsg.type === 'ok' ? 'text-accent-green' : 'text-accent-red'}`}>
              {actionMsg.text}
            </p>
          )}

          {/* User search */}
          <div className="mb-4 relative">
            <input
              type="text"
              value={userQuery}
              onChange={(e) => handleUserSearch(e.target.value)}
              placeholder="Search users to add..."
              className="w-full bg-bg-surface border border-border rounded px-3 py-2 text-sm"
            />
            {(searching || searchResults.length > 0) && userQuery.length >= 2 && (
              <div className="absolute z-10 top-full left-0 right-0 mt-1 bg-bg-surface border border-border rounded shadow-lg">
                {searching && <p className="text-xs text-text-muted px-3 py-2">Searching...</p>}
                {!searching && searchResults.length === 0 && (
                  <p className="text-xs text-text-muted px-3 py-2">No users found</p>
                )}
                {searchResults.map((u) => {
                  const alreadyAdded = accessList.some((a) => a.user_id === u.user_id)
                  return (
                    <div key={u.user_id} className="flex items-center justify-between px-3 py-2 hover:bg-bg-raised border-b border-border/50 last:border-0">
                      <span className="text-sm">{u.display_name}</span>
                      <button
                        onClick={() => !alreadyAdded && handleAdd(u)}
                        disabled={alreadyAdded}
                        className="text-xs px-2 py-1 rounded bg-primary text-bg disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90"
                      >
                        {alreadyAdded ? 'Already added' : 'Add'}
                      </button>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* Current access list */}
          {accessLoading && <p className="text-xs text-text-muted">Loading...</p>}
          {!accessLoading && accessList.length === 0 && (
            <p className="text-xs text-text-muted">No users have been manually granted access.</p>
          )}
          {!accessLoading && accessList.length > 0 && (
            <ul className="space-y-1">
              {accessList.map((u) => (
                <li key={u.user_id} className="flex items-center justify-between text-sm py-1.5 border-b border-border/30 last:border-0">
                  <span>{u.display_name}</span>
                  <button
                    onClick={() => handleRemove(u.user_id, u.display_name)}
                    className="text-xs text-accent-red hover:opacity-80"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

function CardRow({ card, expanded, onToggle, sourceFilter, onHover, onLeave }) {
  const [history, setHistory] = useState(null)
  const [histLoading, setHistLoading] = useState(false)

  useEffect(() => {
    if (!expanded) return
    setHistLoading(true)
    const params = new URLSearchParams({ card: card.name, source: sourceFilter })
    get(`/api/creator/card-history?${params}`)
      .then(setHistory)
      .catch(() => setHistory([]))
      .finally(() => setHistLoading(false))
  }, [expanded, card.name, sourceFilter])

  const handleMouseEnter = (e) => {
    if (card.image) {
      onHover(card.image, e.currentTarget.getBoundingClientRect())
    }
  }

  return (
    <>
      <tr
        className="border-b border-border/50 hover:bg-bg-surface/50 cursor-pointer"
        onMouseEnter={handleMouseEnter}
        onMouseLeave={onLeave}
        onClick={onToggle}
      >
        <td className="py-2 px-3">
          <span className="text-primary hover:text-primary-light transition-colors font-medium">
            {expanded ? '▾' : '▸'} {card.name}
          </span>
        </td>
        <td className="py-2 px-3">{card.element}</td>
        <td className="py-2 px-3">{card.type}</td>
        <td className="py-2 px-3">{card.rarity}</td>
        <td className="py-2 px-3 text-right font-mono">{card.percent_of_decks}%</td>
        <td className="py-2 px-3 text-right font-mono">{card.average_played}</td>
        <td className="py-2 px-3 text-right font-mono">{card.count}</td>
        <td className="py-2 px-3 text-right font-mono">{card.sideboard_count || 0}</td>
        <td className="py-2 px-3 text-right font-mono">{card.decks_with_card}</td>
      </tr>
      {expanded && (
        <tr className="border-b border-border/50">
          <td colSpan={9} className="py-4 px-3">
            <div className="flex items-center gap-3 mb-2">
              <span className="text-sm font-medium text-text-primary">{card.name} — Popularity Over Time</span>
              <Link
                to={`/card/${encodeURIComponent(card.name)}`}
                className="text-xs text-primary hover:text-primary-light"
              >
                View card page →
              </Link>
            </div>
            {histLoading && <p className="text-xs text-text-muted">Loading chart...</p>}
            {!histLoading && history && history.length === 0 && (
              <p className="text-xs text-text-muted">No monthly data available.</p>
            )}
            {!histLoading && history && history.length > 0 && (
              <div style={{ height: 200 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={history} margin={{ top: 8, right: 10, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id={`popGrad-${card.name}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="rgba(77,184,255,0.4)" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="rgba(77,184,255,0.4)" stopOpacity={0.02} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                    <XAxis
                      dataKey="month"
                      tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 10 }}
                      tickLine={false}
                      axisLine={false}
                    />
                    <YAxis
                      tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 10 }}
                      tickLine={false}
                      axisLine={false}
                      width={40}
                      tickFormatter={(v) => `${v}%`}
                    />
                    <Tooltip
                      contentStyle={{
                        background: '#1a1a2e',
                        border: '1px solid rgba(255,255,255,0.1)',
                        borderRadius: 4,
                        fontSize: 11,
                      }}
                      formatter={(value, _name, props) => {
                        const p = props.payload
                        return [`${value}% (${p.decks_with_card}/${p.total_decks} decks)`, '% of Decks']
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="percent_of_decks"
                      stroke="rgba(77,184,255,0.85)"
                      fill={`url(#popGrad-${card.name})`}
                      strokeWidth={2}
                      dot={{ fill: 'rgba(77,184,255,0.95)', r: 3 }}
                      activeDot={{ r: 5 }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  )
}
