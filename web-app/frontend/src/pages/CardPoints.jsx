import { useState, useEffect } from 'react'
import { get, post } from '@/api/client'
import { useAuth } from '@/context/AuthContext'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'
import CardPointsSection from '@/components/admin/CardPointsSection'
import CardPointsAdminPanel from '@/components/card-points/CardPointsAdminPanel'

const CARD_TYPES = ['Avatar', 'Minion', 'Magic', 'Artifact', 'Aura', 'Site']
const ELEMENTS = ['Air', 'Earth', 'Fire', 'Water']

function getCardType(card) {
  const type = (card.type || '').toLowerCase()
  if (type.includes('avatar')) return 'Avatar'
  if (type.includes('minion')) return 'Minion'
  if (type.includes('magic')) return 'Magic'
  if (type.includes('artifact')) return 'Artifact'
  if (type.includes('aura')) return 'Aura'
  if (type.includes('site')) return 'Site'
  return 'Other'
}

function getCardElements(card) {
  if (!card.element) return []
  return card.element.split(',').map((e) => e.trim()).filter(Boolean)
}

export default function CardPoints() {
  const { user } = useAuth()
  const isCardPointsAdmin = user?.is_card_points_admin || user?.is_admin
  const isGlobalAdmin = user?.is_admin

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [elementFilter, setElementFilter] = useState('')
  const [showAdmin, setShowAdmin] = useState(false)

  // Deck checker state
  usePageTitle(data ? `${data.max_budget} Omens` : 'Omens')

  const [deckUrl, setDeckUrl] = useState('')
  const [deckResult, setDeckResult] = useState(null)
  const [deckChecking, setDeckChecking] = useState(false)
  const [history, setHistory] = useState(null)

  useEffect(() => {
    get('/api/card-points/public')
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
    get('/api/card-points/history')
      .then((res) => res.success ? setHistory(res.history) : null)
      .catch(() => {})
  }, [])

  const checkDeck = () => {
    if (!deckUrl.trim()) return
    setDeckChecking(true)
    setDeckResult(null)
    post('/api/card-points/check-deck', { deck_url: deckUrl.trim() })
      .then(setDeckResult)
      .catch((err) => setDeckResult({ success: false, error: err.message }))
      .finally(() => setDeckChecking(false))
  }

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>
  if (!data?.success) return <p className="text-center text-text-muted py-8">Failed to load card points.</p>

  const { cards, max_budget } = data

  const filtered = cards.filter((c) => {
    if (search && !c.card_name.toLowerCase().includes(search.toLowerCase())) return false
    if (typeFilter && getCardType(c) !== typeFilter) return false
    if (elementFilter && !getCardElements(c).includes(elementFilter)) return false
    return true
  })

  const sorted = [...filtered].sort((a, b) => b.point_value - a.point_value)

  return (
    <div>
      <h1 className="text-2xl font-display text-secondary mb-2">{max_budget} Omens</h1>
      <p className="text-sm text-text-muted mb-6">
        Decks in the {max_budget} Omens queue must stay within the point budget.
        Each copy of a pointed card counts toward your total.
      </p>

      {/* Admin toggle */}
      {isCardPointsAdmin && (
        <button
          onClick={() => setShowAdmin(!showAdmin)}
          className="mb-4 px-3 py-1.5 text-sm bg-secondary/20 text-secondary rounded hover:bg-secondary/30 transition-colors"
        >
          {showAdmin ? 'Hide Admin Panel' : 'Show Admin Panel'}
        </button>
      )}

      {/* Admin sections */}
      {showAdmin && isCardPointsAdmin && (
        <div className="space-y-4 mb-6">
          {isGlobalAdmin && <CardPointsAdminPanel />}
          <div className="bg-bg-surface border border-border rounded-lg p-4">
            <h3 className="text-base font-semibold text-text-primary mb-3">Edit Card Points</h3>
            <CardPointsSection />
          </div>
        </div>
      )}

      <div className="bg-bg-surface border border-border rounded-lg p-4 mb-6 inline-block">
        <span className="text-text-muted text-sm">Max Deck Budget:</span>
        <span className="text-2xl font-bold text-secondary ml-2">{max_budget}</span>
        <span className="text-text-muted text-sm ml-1">points</span>
      </div>

      {/* Deck Checker */}
      <div className="bg-bg-surface border border-border rounded-lg p-4 mb-6">
        <h2 className="text-sm font-semibold text-text mb-2">Check Your Deck</h2>
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            type="text"
            placeholder="Paste a Curiosa deck URL..."
            value={deckUrl}
            onChange={(e) => setDeckUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && checkDeck()}
            className="flex-1 px-3 py-2 bg-bg-raised border border-border rounded-soft text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary"
          />
          <button
            onClick={checkDeck}
            disabled={deckChecking || !deckUrl.trim()}
            className="px-4 py-2 bg-primary text-white text-sm font-medium rounded-soft hover:bg-primary/80 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {deckChecking ? 'Checking...' : 'Check Deck'}
          </button>
        </div>
        {deckResult && (
          <div className={`mt-3 p-3 rounded-soft text-sm ${
            deckResult.success && deckResult.is_valid
              ? 'bg-green-500/10 border border-green-500/30 text-green-400'
              : 'bg-red-500/10 border border-red-500/30 text-red-400'
          }`}>
            {!deckResult.success ? (
              <p>{deckResult.error}</p>
            ) : deckResult.is_valid ? (
              <p>Deck is valid: {deckResult.total_points}/{deckResult.max_budget} points used.</p>
            ) : (
              <p>Deck exceeds budget: {deckResult.total_points}/{deckResult.max_budget} points used.</p>
            )}
            {deckResult.success && deckResult.costed_cards?.length > 0 && (
              <ul className="mt-2 space-y-0.5 text-xs opacity-80">
                {deckResult.costed_cards.map((c) => (
                  <li key={c.name}>{c.name} &mdash; {c.points_each} x{c.quantity} = {c.points_total} pts</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      {cards.length === 0 ? (
        <p className="text-text-muted text-sm">No cards have point values assigned yet. All decks are currently allowed.</p>
      ) : (
        <>
          {/* Filters */}
          <div className="flex flex-wrap gap-2 mb-4">
            <input
              type="text"
              placeholder="Search cards..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full sm:w-64 px-3 py-2 bg-bg-surface border border-border rounded-soft text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary"
            />
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="px-3 py-2 bg-bg-surface border border-border rounded-soft text-sm text-text focus:outline-none focus:border-primary"
            >
              <option value="">All Types</option>
              {CARD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <select
              value={elementFilter}
              onChange={(e) => setElementFilter(e.target.value)}
              className="px-3 py-2 bg-bg-surface border border-border rounded-soft text-sm text-text focus:outline-none focus:border-primary"
            >
              <option value="">All Elements</option>
              {ELEMENTS.map((e) => <option key={e} value={e}>{e}</option>)}
            </select>
          </div>

          <p className="text-xs text-text-muted mb-4">{sorted.length} card{sorted.length !== 1 ? 's' : ''} with point values</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
            {sorted.map((card) => (
              <div
                key={card.card_name}
                className="bg-bg-surface border border-border rounded-soft p-3 text-center relative"
              >
                <div className="absolute top-2 right-2 bg-purple-600 text-white text-xs font-bold px-2 py-0.5 rounded-full z-10">
                  {card.point_value} pt{card.point_value !== 1 ? 's' : ''}
                </div>
                {card.image ? (
                  <img
                    src={`/card-images/${card.image}`}
                    alt={card.card_name}
                    className="w-full aspect-[2.5/3.5] object-cover rounded mb-2"
                    loading="lazy"
                  />
                ) : (
                  <div className="w-full aspect-[2.5/3.5] bg-bg-raised rounded mb-2 flex items-center justify-center">
                    <span className="text-text-muted text-xs">No image</span>
                  </div>
                )}
                <h3 className="text-sm font-semibold truncate">{card.card_name}</h3>
              </div>
            ))}
          </div>
          {filtered.length === 0 && (
            <p className="text-center text-text-muted py-8">No matching cards found.</p>
          )}
        </>
      )}

      {/* History */}
      {history && history.length > 0 && (
        <div className="mt-10">
          <h2 className="text-xl font-display text-secondary mb-4">Change History</h2>
          <div className="bg-bg-surface border border-border rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-text-muted">
                  <th className="px-4 py-2">Date</th>
                  <th className="px-4 py-2">Change</th>
                </tr>
              </thead>
              <tbody>
                {history.map((entry) => (
                  <tr key={entry.id} className="border-b border-border/50 last:border-0">
                    <td className="px-4 py-2 text-text-muted whitespace-nowrap">
                      {new Date(entry.changed_at + 'Z').toLocaleDateString()}
                    </td>
                    <td className="px-4 py-2">
                      {entry.action === 'added' && (
                        <span>
                          <span className="text-green-400">Added</span>{' '}
                          <span className="font-semibold text-text">{entry.card_name}</span>{' '}
                          at <span className="text-secondary">{entry.new_value} pt{entry.new_value !== '1' ? 's' : ''}</span>
                        </span>
                      )}
                      {entry.action === 'removed' && (
                        <span>
                          <span className="text-red-400">Removed</span>{' '}
                          <span className="font-semibold text-text">{entry.card_name}</span>{' '}
                          <span className="text-text-muted">(was {entry.old_value} pt{entry.old_value !== '1' ? 's' : ''})</span>
                        </span>
                      )}
                      {entry.action === 'changed' && (
                        <span>
                          <span className="font-semibold text-text">{entry.card_name}</span>{' '}
                          <span className="text-text-muted">{entry.old_value}</span>{' '}
                          <span className="text-text-muted">&rarr;</span>{' '}
                          <span className="text-secondary">{entry.new_value} pt{entry.new_value !== '1' ? 's' : ''}</span>
                        </span>
                      )}
                      {entry.action === 'budget_changed' && (
                        <span>
                          <span className="text-yellow-400">Budget changed</span>{' '}
                          <span className="text-text-muted">{entry.old_value}</span>{' '}
                          <span className="text-text-muted">&rarr;</span>{' '}
                          <span className="text-secondary">{entry.new_value}</span>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
