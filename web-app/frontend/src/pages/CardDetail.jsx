import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getCard } from '@/api/cards'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

export default function CardDetail() {
  usePageTitle('Card Detail')
  const { name } = useParams()
  const [card, setCard] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    getCard(name)
      .then((data) => {
        setCard(data)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [name])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>
  if (!card) return null

  return (
    <div className="space-y-6">
      <Link to="/cards" className="text-primary hover:text-primary-light text-sm">&larr; All Cards</Link>

      <div className="bg-bg-surface border border-border rounded-soft p-6 flex flex-col sm:flex-row gap-6">
        {card.image_url && (
          <img
            src={card.image_url}
            alt={card.name}
            className="w-64 aspect-[2.5/3.5] object-cover rounded flex-shrink-0"
          />
        )}
        <div className="flex-1 space-y-3">
          <h1 className="text-2xl font-display text-secondary">{card.name}</h1>
          {card.element && (
            <p className="text-sm text-text-muted">Element: <span className="text-text">{card.element}</span></p>
          )}
          {card.type && (
            <p className="text-sm text-text-muted">Type: <span className="text-text">{card.type}</span></p>
          )}
          {card.threshold && (
            <p className="text-sm text-text-muted">Threshold: <span className="text-text">{card.threshold}</span></p>
          )}
          {card.cost != null && (
            <p className="text-sm text-text-muted">Cost: <span className="text-text">{card.cost}</span></p>
          )}
          {card.attack != null && card.defense != null && (
            <p className="text-sm text-text-muted">
              Stats: <span className="text-text">{card.attack} / {card.defense}</span>
            </p>
          )}
          {card.win_rate != null && (
            <p className="text-sm text-text-muted">
              Win Rate: <span className="text-text">{(card.win_rate * 100).toFixed(1)}%</span>
            </p>
          )}
          {card.play_rate != null && (
            <p className="text-sm text-text-muted">
              Play Rate: <span className="text-text">{(card.play_rate * 100).toFixed(1)}%</span>
            </p>
          )}
          {card.text && (
            <p className="text-sm text-text-muted mt-4 italic">{card.text}</p>
          )}
        </div>
      </div>
    </div>
  )
}
