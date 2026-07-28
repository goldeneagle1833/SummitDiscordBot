import { useState, useEffect, useRef, useCallback } from 'react'
import { get, post, del } from '@/api/client'

export default function CardPointsSection() {
  const [cards, setCards] = useState([])
  const [maxBudget, setMaxBudget] = useState(50)
  const [budgetInput, setBudgetInput] = useState('50')
  const [loading, setLoading] = useState(true)

  // Search state
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [searchOpen, setSearchOpen] = useState(false)
  const [activeIdx, setActiveIdx] = useState(-1)
  const [pointInput, setPointInput] = useState('1')
  const timerRef = useRef(null)
  const containerRef = useRef(null)

  // Edit state
  const [editingId, setEditingId] = useState(null)
  const [editValue, setEditValue] = useState('')

  const loadCards = useCallback(() => {
    setLoading(true)
    get('/api/card-points')
      .then(d => {
        if (d.success) {
          setCards(d.cards)
          setMaxBudget(d.max_budget)
          setBudgetInput(String(d.max_budget))
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { loadCards() }, [loadCards])

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) setSearchOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const searchCards = useCallback((q) => {
    if (q.length < 2) { setSearchOpen(false); return }
    get(`/api/card-points/search-cards?q=${encodeURIComponent(q)}`)
      .then(d => {
        setResults(d.cards || [])
        setActiveIdx(-1)
        setSearchOpen(true)
      })
      .catch(() => setSearchOpen(false))
  }, [])

  const handleInput = (e) => {
    const val = e.target.value
    setQuery(val)
    clearTimeout(timerRef.current)
    if (val.trim().length < 2) { setSearchOpen(false); return }
    timerRef.current = setTimeout(() => searchCards(val.trim()), 200)
  }

  const assignCard = async (cardName) => {
    const pts = parseInt(pointInput, 10)
    if (isNaN(pts) || pts < 0) { alert('Enter a valid point value.'); return }
    try {
      const d = await post('/api/card-points', { card_name: cardName, point_value: pts })
      if (d.success) {
        setQuery('')
        setSearchOpen(false)
        loadCards()
      } else {
        alert('Error: ' + d.error)
      }
    } catch {
      alert('Failed to assign points')
    }
  }

  const handleKeyDown = (e) => {
    if (!searchOpen) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIdx(i => Math.min(i + 1, results.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIdx(i => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      if (activeIdx >= 0 && results[activeIdx]) assignCard(results[activeIdx])
      else if (results.length === 1) assignCard(results[0])
    } else if (e.key === 'Escape') {
      setSearchOpen(false)
    }
  }

  const handleDelete = async (cardName) => {
    if (!confirm(`Remove points for "${cardName}"?`)) return
    try {
      const d = await del(`/api/card-points/${encodeURIComponent(cardName)}`)
      if (d.success) loadCards()
      else alert('Error: ' + d.error)
    } catch {
      alert('Failed to remove')
    }
  }

  const handleEditSave = async (cardName) => {
    const pts = parseInt(editValue, 10)
    if (isNaN(pts) || pts < 0) { alert('Enter a valid point value.'); return }
    try {
      const d = await post('/api/card-points', { card_name: cardName, point_value: pts })
      if (d.success) {
        setEditingId(null)
        loadCards()
      } else {
        alert('Error: ' + d.error)
      }
    } catch {
      alert('Failed to update')
    }
  }

  const handleBudgetSave = async () => {
    const val = parseInt(budgetInput, 10)
    if (isNaN(val) || val < 0) { alert('Enter a valid budget.'); return }
    try {
      const d = await post('/api/card-points/config', { max_budget: val })
      if (d.success) {
        setMaxBudget(d.max_budget)
        setBudgetInput(String(d.max_budget))
      } else {
        alert('Error: ' + d.error)
      }
    } catch {
      alert('Failed to update budget')
    }
  }

  const totalPoints = cards.reduce((sum, c) => sum + c.point_value, 0)

  return (
    <section className="space-y-4">
      {/* Budget config */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <label className="text-sm text-text-muted">Max Deck Budget:</label>
          <input
            type="number"
            value={budgetInput}
            onChange={e => setBudgetInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleBudgetSave()}
            className="w-20 bg-bg-surface border border-border rounded px-2 py-1 text-sm"
            min={0}
          />
          <button
            onClick={handleBudgetSave}
            className="px-3 py-1 text-xs bg-secondary text-black rounded hover:opacity-90"
          >
            Save
          </button>
        </div>
        <div className="text-xs text-text-muted">
          {cards.length} card{cards.length !== 1 ? 's' : ''} assigned
          {' · '}Total points in pool: {totalPoints}
        </div>
      </div>

      {/* Search + assign */}
      <div ref={containerRef} className="relative">
        <div className="flex gap-2 items-end">
          <div className="flex-1 relative">
            <label className="text-xs text-text-muted">Search card to assign points</label>
            <input
              type="text"
              value={query}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              placeholder="Type a card name..."
              autoComplete="off"
              spellCheck={false}
              className="w-full mt-1 bg-bg-surface border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-primary/60 placeholder:text-text-muted"
            />
            {searchOpen && (
              <div className="absolute z-50 w-full mt-1 bg-bg-surface border border-border rounded shadow-lg overflow-hidden max-h-60 overflow-y-auto">
                {results.length === 0 ? (
                  <div className="px-4 py-2 text-sm text-text-muted">No cards found</div>
                ) : (
                  results.map((name, i) => {
                    const existing = cards.find(c => c.card_name.toLowerCase() === name.toLowerCase())
                    return (
                      <button
                        key={name}
                        onClick={() => assignCard(name)}
                        className={`w-full flex items-center justify-between px-3 py-2 text-sm text-left hover:bg-bg-elevated transition-colors ${i === activeIdx ? 'bg-bg-elevated' : ''}`}
                      >
                        <span>{name}</span>
                        {existing && (
                          <span className="text-xs text-secondary ml-2">{existing.point_value}pts</span>
                        )}
                      </button>
                    )
                  })
                )}
              </div>
            )}
          </div>
          <div>
            <label className="text-xs text-text-muted">Points</label>
            <input
              type="number"
              value={pointInput}
              onChange={e => setPointInput(e.target.value)}
              className="w-16 mt-1 bg-bg-surface border border-border rounded px-2 py-2 text-sm"
              min={0}
            />
          </div>
        </div>
      </div>

      {/* Card points table */}
      {loading ? (
        <p className="text-sm text-text-muted py-4 text-center">Loading...</p>
      ) : cards.length === 0 ? (
        <p className="text-sm text-text-muted py-4 text-center">No cards have points assigned yet. Search above to add some.</p>
      ) : (
        <div className="bg-bg-raised border border-border rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-text-muted border-b border-border">
                  <th className="px-4 py-2 font-medium">Card Name</th>
                  <th className="px-4 py-2 font-medium text-center">Points</th>
                  <th className="px-4 py-2 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {cards.map(c => (
                  <tr key={c.id} className="border-b border-border/50 last:border-b-0 hover:bg-bg-elevated/50">
                    <td className="px-4 py-2">{c.card_name}</td>
                    <td className="px-4 py-2 text-center">
                      {editingId === c.id ? (
                        <input
                          type="number"
                          value={editValue}
                          onChange={e => setEditValue(e.target.value)}
                          onKeyDown={e => {
                            if (e.key === 'Enter') handleEditSave(c.card_name)
                            if (e.key === 'Escape') setEditingId(null)
                          }}
                          autoFocus
                          className="w-16 bg-bg-surface border border-border rounded px-2 py-0.5 text-sm text-center"
                          min={0}
                        />
                      ) : (
                        <span
                          className="font-bold text-secondary cursor-pointer hover:underline"
                          onClick={() => { setEditingId(c.id); setEditValue(String(c.point_value)) }}
                          title="Click to edit"
                        >
                          {c.point_value}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <div className="flex gap-1 justify-end">
                        {editingId === c.id ? (
                          <>
                            <button
                              onClick={() => handleEditSave(c.card_name)}
                              className="px-2 py-0.5 text-xs bg-accent-green/20 text-accent-green rounded hover:bg-accent-green/30"
                            >
                              Save
                            </button>
                            <button
                              onClick={() => setEditingId(null)}
                              className="px-2 py-0.5 text-xs bg-bg-surface border border-border rounded hover:bg-bg-elevated"
                            >
                              Cancel
                            </button>
                          </>
                        ) : (
                          <button
                            onClick={() => handleDelete(c.card_name)}
                            className="px-2 py-0.5 text-xs bg-accent-red/20 text-accent-red rounded hover:bg-accent-red/30"
                          >
                            Remove
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  )
}
