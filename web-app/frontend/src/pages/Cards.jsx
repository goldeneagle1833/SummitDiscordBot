import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getCards } from '@/api/cards'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

export default function Cards() {
  usePageTitle('Cards')
  const [cards, setCards] = useState([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getCards()
      .then(setCards)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  const filtered = cards.filter((card) =>
    card.name.toLowerCase().includes(search.toLowerCase())
  )

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      <h1 className="text-2xl font-display text-secondary mb-4">Cards</h1>
      <input
        type="text"
        placeholder="Search cards..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="w-full sm:w-80 mb-4 px-3 py-2 bg-bg-surface border border-border rounded-soft text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary"
      />
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
        {filtered.map((card) => (
          <Link
            key={card.name}
            to={`/card/${encodeURIComponent(card.name)}`}
            className="bg-bg-surface border border-border rounded-soft p-3 hover:border-primary/50 transition-colors text-center"
          >
            {card.image_url && (
              <img
                src={card.image_url}
                alt={card.name}
                className="w-full aspect-[2.5/3.5] object-cover rounded mb-2"
              />
            )}
            <h3 className="text-sm font-semibold truncate">{card.name}</h3>
          </Link>
        ))}
      </div>
      {filtered.length === 0 && (
        <p className="text-center text-text-muted py-8">No cards found.</p>
      )}
    </div>
  )
}
