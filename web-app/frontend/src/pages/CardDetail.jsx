import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getCard } from '@/api/cards'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

function Stat({ label, value }) {
  if (value == null || value === '' || value === 'None') return null
  return (
    <div className="flex gap-2 text-sm">
      <span className="text-text-muted min-w-[90px]">{label}</span>
      <span className="text-text">{value}</span>
    </div>
  )
}

export default function CardDetail() {
  const { name } = useParams()
  const [card, setCard] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  usePageTitle(card ? card.name : 'Card')

  useEffect(() => {
    setLoading(true)
    setError(null)
    getCard(name)
      .then(setCard)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [name])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>
  if (!card) return null

  const imageUrl = card.image ? `/card-images/${card.image}` : null

  return (
    <div className="space-y-6">
      <Link to="/cards" className="text-primary hover:text-primary-light text-sm">&larr; All Cards</Link>

      <div className="bg-bg-surface border border-border rounded-soft p-6 flex flex-col sm:flex-row gap-6">
        {imageUrl && (
          <img
            src={imageUrl}
            alt={card.name}
            className="w-48 rounded flex-shrink-0 object-cover self-start"
          />
        )}
        <div className="flex-1 space-y-2">
          <h1 className="text-2xl font-display text-secondary mb-4">{card.name}</h1>
          <Stat label="Element" value={card.element} />
          <Stat label="Type" value={card.type} />
          <Stat label="Rarity" value={card.rarity} />
          <Stat label="Set" value={card.set} />
          <Stat label="Threshold" value={card.threshold} />
          <Stat label="Cost" value={card.cost} />
          {(card.power != null || card.defense != null) && (
            <div className="flex gap-2 text-sm">
              <span className="text-text-muted min-w-[90px]">Power / Def</span>
              <span className="text-text">{card.power ?? '—'} / {card.defense ?? '—'}</span>
            </div>
          )}
          {card.text && (
            <p className="text-sm text-text-muted italic mt-4 border-t border-border pt-4">{card.text}</p>
          )}
        </div>
      </div>

      {card.total_matches != null && (
        <div className="bg-bg-surface border border-border rounded-soft p-5">
          <h2 className="text-base font-semibold text-text-primary mb-3">Match Stats</h2>
          <div className="flex flex-wrap gap-6 text-sm">
            <div>
              <p className="text-text-muted">Win Rate</p>
              <p className="text-2xl font-mono font-bold text-secondary">{card.win_rate}%</p>
            </div>
            <div>
              <p className="text-text-muted">Record</p>
              <p className="text-lg font-mono">
                <span className="text-accent-green">{card.wins}W</span>
                {' / '}
                <span className="text-accent-red">{card.losses}L</span>
              </p>
            </div>
            <div>
              <p className="text-text-muted">Total Matches</p>
              <p className="text-lg font-mono">{card.total_matches}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
