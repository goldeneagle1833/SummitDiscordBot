import { useState, useEffect, lazy, Suspense } from 'react'
import { useParams } from 'react-router-dom'
import { getDeck } from '@/api/decks'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

const DeckViewer = lazy(() => import('@/components/deck/DeckViewer'))

export default function DeckDetail() {
  usePageTitle('Deck Detail')
  const { deckId } = useParams()
  const [deck, setDeck] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    getDeck(deckId)
      .then(setDeck)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [deckId])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <Suspense fallback={<Spinner className="py-20" />}>
      <DeckViewer deck={deck} />
    </Suspense>
  )
}
