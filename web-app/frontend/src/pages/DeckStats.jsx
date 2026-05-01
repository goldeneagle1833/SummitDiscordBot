import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useSearchParams, Link } from 'react-router-dom'
import Spinner from '@/components/ui/Spinner'
import CardImagePopup from '@/components/deck/CardImagePopup'
import DeckVisualizer from '@/components/deck/DeckVisualizer'
import StatCard from '@/components/player/StatCard'
import CollapsibleSection from '@/components/player/CollapsibleSection'
import { get } from '@/api/client'
import usePageTitle from '@/hooks/usePageTitle'

const TCGPLAYER_IMPACT_LINK = 'https://partner.tcgplayer.com/c/5746741/1780961/21018'
const CARD_TYPE_ORDER = ['Minion', 'Magic', 'Artifact', 'Aura', 'Site', 'Other']

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

export default function DeckStats() {
  const { playerId } = useParams()
  const [searchParams] = useSearchParams()
  const deckUrl = searchParams.get('url')

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [viewMode, setViewMode] = useState('list')
  const [matchupsOpen, setMatchupsOpen] = useState(true)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [hoverCard, setHoverCard] = useState({ image: null, rect: null })

  usePageTitle(data ? `${data.deck_name || 'Deck'} - Stats` : 'Deck Stats')

  useEffect(() => {
    if (!deckUrl) {
      setError('No deck URL provided')
      setLoading(false)
      return
    }
    setLoading(true)
    get(`/api/players/${playerId}/deck-stats?url=${encodeURIComponent(deckUrl)}`)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [playerId, deckUrl])

  const handleHover = useCallback((image, rect) => setHoverCard({ image, rect }), [])
  const handleLeave = useCallback(() => setHoverCard({ image: null, rect: null }), [])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>
  if (!data) return null

  const deck = data.deck || {}
  const spellbook = deck.spellbook || []
  const spellbookGroups = groupByType(spellbook)
  const avatarName = data.avatar !== 'Unknown' ? data.avatar : (deck.avatar?.[0]?.name || '')
  const onPlay = data.on_play || {}
  const onDraw = data.on_draw || {}
  const allCards = collectAllCards(deck)
  const tcgUrl = buildTcgPlayerUrl(allCards)

  return (
    <div className="space-y-6">
      <Link to={`/player/${playerId}`} className="text-sm text-secondary hover:underline">
        &larr; Back to Profile
      </Link>

      {/* Header */}
      <div className="bg-bg-surface border border-border rounded-lg p-5">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-display text-text-primary">{data.deck_name}</h1>
            {avatarName && <p className="text-sm text-text-muted mt-1">{avatarName}</p>}
            <a
              href={data.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-secondary hover:underline mt-1 inline-block"
            >
              View on Curiosa &rarr;
            </a>
          </div>
          {tcgUrl && (
            <a
              href={tcgUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 bg-green-600 hover:bg-green-700 text-white text-sm px-4 py-2 rounded transition-colors whitespace-nowrap self-start"
            >
              Buy on TCGPlayer &#8599;
            </a>
          )}
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Wins" value={<span className="text-accent-green">{data.wins}</span>} />
        <StatCard label="Losses" value={<span className="text-accent-red">{data.losses}</span>} />
        <StatCard label="Win Rate" value={`${data.win_rate}%`} />
        <StatCard label="Total Games" value={data.total} />
        {onPlay.total > 0 && (
          <StatCard
            label="On the Play"
            value={`${onPlay.win_rate}% (${onPlay.wins}/${onPlay.total})`}
          />
        )}
        {onDraw.total > 0 && (
          <StatCard
            label="On the Draw"
            value={`${onDraw.win_rate}% (${onDraw.wins}/${onDraw.total})`}
          />
        )}
      </div>

      {/* Matchups vs Avatars */}
      {data.matchups?.length > 0 && (
        <CollapsibleSection
          title="Matchups vs Avatars"
          open={matchupsOpen}
          onToggle={() => setMatchupsOpen((o) => !o)}
        >
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {data.matchups.map((m) => (
              <div
                key={m.opponent_avatar}
                className="bg-bg-raised border border-border rounded-lg p-3 text-center"
              >
                <p className="font-medium text-text-primary text-sm mb-1">{m.opponent_avatar}</p>
                <p className="text-sm">
                  <span className="text-accent-green">{m.wins}</span>
                  {' - '}
                  <span className="text-accent-red">{m.losses}</span>
                </p>
                <p className="text-xs text-text-muted">{m.win_rate}% ({m.total} games)</p>
              </div>
            ))}
          </div>
        </CollapsibleSection>
      )}

      {/* Deck Contents */}
      {(spellbook.length > 0 || deck.atlas?.length > 0) && (
        <section>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-lg font-semibold text-text-primary">Deck Contents</h3>
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
              <CardSection
                title="Atlas"
                cards={[...(spellbookGroups.Site || []), ...(deck.atlas || [])]}
                onHover={handleHover}
                onLeave={handleLeave}
              />
              <CardSection
                title="Collection"
                cards={deck.sideboard}
                onHover={handleHover}
                onLeave={handleLeave}
              />
            </div>
          )}

          {viewMode === 'visual' && (
            <DeckVisualizer spellbook={deck.spellbook} atlas={deck.atlas} sideboard={deck.sideboard} />
          )}
        </section>
      )}

      {/* Match History */}
      {data.matches?.length > 0 && (
        <CollapsibleSection
          title={`Match History (${data.matches.length})`}
          open={historyOpen}
          onToggle={() => setHistoryOpen((o) => !o)}
        >
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-text-muted border-b border-border">
                  <th className="pb-2 pr-4">Date</th>
                  <th className="pb-2 pr-4">Result</th>
                  <th className="pb-2 pr-4">Opponent</th>
                  <th className="pb-2 pr-4">Opp. Avatar</th>
                  <th className="pb-2 pr-4">ELO</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.matches.map((m) => (
                  <tr key={m.match_id} className="hover:bg-bg-raised transition-colors">
                    <td className="py-2 pr-4 text-text-muted whitespace-nowrap">
                      {m.date ? new Date(m.date).toLocaleDateString() : '-'}
                    </td>
                    <td className={`py-2 pr-4 font-medium ${m.result === 'Win' ? 'text-accent-green' : 'text-accent-red'}`}>
                      {m.result}
                    </td>
                    <td className="py-2 pr-4">
                      <Link to={`/player/${m.opponent_id}`} className="text-secondary hover:underline">
                        {m.opponent}
                      </Link>
                    </td>
                    <td className="py-2 pr-4 text-text-muted">{m.opponent_avatar}</td>
                    <td className="py-2 pr-4 text-text-muted">
                      {m.elo_change > 0
                        ? <span className="text-accent-green">+{m.elo_change}</span>
                        : m.elo_change < 0
                          ? <span className="text-accent-red">{m.elo_change}</span>
                          : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CollapsibleSection>
      )}

      <CardImagePopup imageFile={hoverCard.image} anchorRect={hoverCard.rect} />
    </div>
  )
}
