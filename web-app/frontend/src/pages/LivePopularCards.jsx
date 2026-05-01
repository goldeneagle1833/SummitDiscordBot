import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { get } from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

export default function LivePopularCards() {
  usePageTitle('Live Popular Cards')
  const [cards, setCards] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    get('/api/live-popular-cards')
      .then(setCards)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      <h1 className="text-2xl font-display text-secondary mb-4">Popular Cards</h1>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
        {cards.map((card) => (
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
            {card.play_count != null && (
              <p className="text-xs text-text-muted mt-1">{card.play_count} plays</p>
            )}
            {card.win_rate != null && (
              <p className="text-xs text-text-muted">{(card.win_rate * 100).toFixed(1)}% WR</p>
            )}
          </Link>
        ))}
      </div>
      {cards.length === 0 && (
        <p className="text-center text-text-muted py-8">No popular card data available.</p>
      )}
    </div>
  )
}
