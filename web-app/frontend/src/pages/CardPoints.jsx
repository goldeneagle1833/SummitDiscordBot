import { useState, useEffect } from 'react'
import { get } from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

export default function CardPoints() {
  usePageTitle('Card Points')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')

  useEffect(() => {
    get('/api/card-points/public')
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>
  if (!data?.success) return <p className="text-center text-text-muted py-8">Points system is not currently active.</p>

  const { cards, max_budget } = data

  const filtered = cards.filter((c) =>
    c.card_name.toLowerCase().includes(search.toLowerCase())
  )

  const sorted = [...filtered].sort((a, b) => b.point_value - a.point_value)

  return (
    <div>
      <h1 className="text-2xl font-display text-secondary mb-2">Ranked w/ Points</h1>
      <p className="text-sm text-text-muted mb-6">
        Decks in the Ranked w/ Points queue must stay within the point budget.
        Each copy of a pointed card counts toward your total.
      </p>

      <div className="bg-bg-surface border border-border rounded-lg p-4 mb-6 inline-block">
        <span className="text-text-muted text-sm">Max Deck Budget:</span>
        <span className="text-2xl font-bold text-secondary ml-2">{max_budget}</span>
        <span className="text-text-muted text-sm ml-1">points</span>
      </div>

      {cards.length === 0 ? (
        <p className="text-text-muted text-sm">No cards have point values assigned yet. All decks are currently allowed.</p>
      ) : (
        <>
          <input
            type="text"
            placeholder="Search cards..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full sm:w-80 mb-4 px-3 py-2 bg-bg-surface border border-border rounded-soft text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary"
          />
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
    </div>
  )
}
