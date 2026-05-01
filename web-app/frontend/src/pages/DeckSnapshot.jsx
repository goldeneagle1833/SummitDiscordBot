import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import Spinner from '@/components/ui/Spinner'
import CardImagePopup from '@/components/deck/CardImagePopup'
import DeckVisualizer from '@/components/deck/DeckVisualizer'
import { get } from '@/api/client'
import usePageTitle from '@/hooks/usePageTitle'

const TCGPLAYER_IMPACT_LINK = 'https://partner.tcgplayer.com/c/5746741/1780961/21018'
const CARD_TYPE_ORDER = ['Minion', 'Magic', 'Artifact', 'Aura', 'Site', 'Other']

function getManaCost(card) {
  return card.threshold || card.cost || card.mana || card.mana_cost || 0
}

function getCardType(card) {
  const type = (card.type || '').toLowerCase()
  if (type.includes('minion')) return 'Minion'
  if (type.includes('magic')) return 'Magic'
  if (type.includes('artifact')) return 'Artifact'
  if (type.includes('aura')) return 'Aura'
  if (type.includes('site')) return 'Site'
  return 'Other'
}

function buildTcgPlayerUrl(cards) {
  if (!cards?.length) return null
  const cardList = cards.map((c) => `${c.quantity || 1} ${c.name}`).join('||')
  const massEntryUrl =
    'https://www.tcgplayer.com/massentry?productline=Sorcery+Contested+Realm&c=' +
    encodeURIComponent(cardList)
  return TCGPLAYER_IMPACT_LINK + '?u=' + encodeURIComponent(massEntryUrl)
}

function collectAllCards(deck) {
  const all = []
  for (const section of ['spellbook', 'atlas', 'sideboard']) {
    if (deck[section]) all.push(...deck[section])
  }
  return all
}

function groupByType(cards) {
  const groups = {}
  CARD_TYPE_ORDER.forEach((t) => { groups[t] = [] })
  cards.forEach((card) => {
    const type = getCardType(card)
    if (!groups[type]) groups[type] = []
    groups[type].push(card)
  })
  for (const type of Object.keys(groups)) {
    groups[type].sort((a, b) => getManaCost(a) - getManaCost(b))
  }
  return groups
}

/* ---- Card Row with hover ---- */
function CardItem({ card, onHover, onLeave }) {
  const ref = useRef(null)
  const qty = card.quantity || 1
  const cost = getManaCost(card)
  return (
    <li
      ref={ref}
      className="flex items-center gap-2 text-sm hover:bg-bg-raised rounded px-2 py-1.5 transition-colors"
      style={{ cursor: card.image ? 'pointer' : 'default' }}
      onMouseEnter={() => {
        if (card.image && ref.current) onHover(card.image, ref.current.getBoundingClientRect())
      }}
      onMouseLeave={onLeave}
    >
      <span className="text-text-muted w-5 text-right">{qty}x</span>
      <span className="text-text-primary flex-1">{card.name}</span>
      {cost > 0 && <span className="text-xs text-text-muted bg-bg-raised px-1.5 py-0.5 rounded">{cost}</span>}
    </li>
  )
}

/* ---- Card Section ---- */
function CardSection({ title, cards, onHover, onLeave }) {
  if (!cards?.length) return null
  const totalQty = cards.reduce((sum, c) => sum + (c.quantity || 1), 0)
  return (
    <div className="bg-bg-surface border border-border rounded-lg p-4">
      <h3 className="text-sm font-semibold text-text-muted mb-2 uppercase tracking-wider">
        {title} ({totalQty})
      </h3>
      <ul className="space-y-0.5">
        {cards.map((card, i) => (
          <CardItem key={`${card.name}-${i}`} card={card} onHover={onHover} onLeave={onLeave} />
        ))}
      </ul>
    </div>
  )
}

export default function DeckSnapshot() {
  const { matchId, playerId } = useParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [viewMode, setViewMode] = useState('visual')
  const [hoverCard, setHoverCard] = useState({ image: null, rect: null })

  usePageTitle(data ? `${data.deck?.name || 'Deck'} - Snapshot` : 'Deck Snapshot')

  useEffect(() => {
    setLoading(true)
    get(`/api/deck-snapshot/${matchId}/${playerId}`)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [matchId, playerId])

  const handleHover = useCallback((image, rect) => setHoverCard({ image, rect }), [])
  const handleLeave = useCallback(() => setHoverCard({ image: null, rect: null }), [])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>
  if (!data) return null

  const deck = data.deck || {}
  const spellbook = deck.spellbook || []
  const deckName = deck.name || 'Unnamed Deck'
  const avatarName = deck.avatar?.[0]?.name || ''
  const date = data.date ? new Date(data.date).toLocaleDateString() : ''
  const allCards = collectAllCards(deck)
  const tcgUrl = buildTcgPlayerUrl(allCards)
  const spellbookGroups = groupByType(spellbook)

  return (
    <div className="space-y-6">
      <Link to={`/player/${playerId}`} className="text-sm text-secondary hover:underline">&larr; Back to Profile</Link>

      {/* Header */}
      <div className="bg-bg-surface border border-border rounded-lg p-5">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-display text-text-primary">{deckName}</h1>
            {avatarName && <p className="text-sm text-text-muted mt-1">{avatarName}</p>}
            <p className="text-sm mt-1">
              <span className={data.result === 'Win' ? 'text-accent-green' : 'text-accent-red'}>{data.result}</span>
              {' vs '}
              <span className="text-text-primary">{data.opponent_name}</span>
              {date && <span className="text-text-muted"> on {date}</span>}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {tcgUrl && (
              <a
                href={tcgUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 bg-green-600 hover:bg-green-700 text-white text-sm px-4 py-2 rounded transition-colors whitespace-nowrap"
              >
                Buy on TCGPlayer &#8599;
              </a>
            )}
          </div>
        </div>
      </div>

      {/* View Mode Toggle */}
      <div className="flex items-center gap-2">
        <span className="text-sm text-text-muted">View:</span>
        <div className="inline-flex bg-bg-raised border border-border rounded-lg overflow-hidden">
          <button
            onClick={() => setViewMode('list')}
            className={`px-3 py-1.5 text-xs font-medium transition-colors ${
              viewMode === 'list' ? 'bg-secondary text-black' : 'text-text-muted hover:text-text-primary'
            }`}
          >
            List
          </button>
          <button
            onClick={() => setViewMode('visual')}
            className={`px-3 py-1.5 text-xs font-medium transition-colors ${
              viewMode === 'visual' ? 'bg-secondary text-black' : 'text-text-muted hover:text-text-primary'
            }`}
          >
            Visual
          </button>
        </div>
      </div>

      {/* List View */}
      {viewMode === 'list' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {CARD_TYPE_ORDER.filter((t) => t !== 'Site').map((type) => (
            <CardSection
              key={type}
              title={type + 's'}
              cards={spellbookGroups[type]}
              onHover={handleHover}
              onLeave={handleLeave}
            />
          ))}
          <CardSection title="Atlas" cards={[...(spellbookGroups.Site || []), ...(deck.atlas || [])]} onHover={handleHover} onLeave={handleLeave} />
          <CardSection title="Collection" cards={deck.sideboard} onHover={handleHover} onLeave={handleLeave} />
        </div>
      )}

      {/* Visual View (Deck Visualizer) */}
      {viewMode === 'visual' && (
        <DeckVisualizer spellbook={deck.spellbook} atlas={deck.atlas} sideboard={deck.sideboard} />
      )}

      {/* Card Image Popup */}
      <CardImagePopup imageFile={hoverCard.image} anchorRect={hoverCard.rect} />
    </div>
  )
}
