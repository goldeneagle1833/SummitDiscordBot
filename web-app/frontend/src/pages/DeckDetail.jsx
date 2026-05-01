import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getDeckRecommendations } from '@/api/decks'
import { getAvatarImageFiles } from '@/api/cards'
import Spinner from '@/components/ui/Spinner'
import CardImagePopup from '@/components/deck/CardImagePopup'
import DeckVisualizer from '@/components/deck/DeckVisualizer'
import usePageTitle from '@/hooks/usePageTitle'

const TCGPLAYER_IMPACT_LINK = 'https://partner.tcgplayer.com/c/5746741/1780961/21018'
const CARD_TYPE_ORDER = ['Minion', 'Magic', 'Artifact', 'Aura', 'Site', 'Other']

function normalize(str) {
  return str.toLowerCase().replace(/[^a-z0-9]/g, '')
}

function getAvatarImagePath(name, files) {
  if (!name || !files?.length) return null
  const norm = normalize(name)
  for (const img of files) {
    if (normalize(img.replace(/\.(png|jpg|jpeg|webp)$/i, '')) === norm) return img
  }
  for (const img of files) {
    if (normalize(img.replace(/\.(png|jpg|jpeg|webp)$/i, '')).includes(norm)) return img
  }
  return null
}

function buildTcgPlayerUrl(seedCards) {
  if (!seedCards?.length) return null
  const cardList = seedCards.map((c) => `${c.qty} ${c.name}`).join('||')
  const massEntryUrl =
    'https://www.tcgplayer.com/massentry?productline=Sorcery+Contested+Realm&c=' +
    encodeURIComponent(cardList)
  return TCGPLAYER_IMPACT_LINK + '?u=' + encodeURIComponent(massEntryUrl)
}

function getSeedCardType(typeStr) {
  const t = (typeStr || '').toLowerCase()
  if (t.includes('minion')) return 'Minion'
  if (t.includes('magic')) return 'Magic'
  if (t.includes('artifact')) return 'Artifact'
  if (t.includes('aura')) return 'Aura'
  if (t.includes('site')) return 'Site'
  return 'Other'
}

/* ---- Card Row ---- */
function CardRow({ card, onHover, onLeave }) {
  const ref = useRef(null)
  return (
    <li
      ref={ref}
      className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-bg-raised transition-colors"
      style={{ cursor: card.image ? 'pointer' : 'default' }}
      onMouseEnter={() => {
        if (card.image && ref.current) onHover(card.image, ref.current.getBoundingClientRect())
      }}
      onMouseLeave={onLeave}
    >
      <span className="text-sm text-text-primary">{card.card_name}</span>
      <span className="flex items-center gap-2 text-sm">
        {card.avg_copies != null && (
          <span className="text-text-muted" title="avg copies per deck">x{card.avg_copies.toFixed(2)}</span>
        )}
        <span className="text-secondary font-medium">{card.inclusion_pct}</span>
      </span>
    </li>
  )
}

/* ---- Tier Section ---- */
function TierSection({ title, badge, badgeColor, cards, onHover, onLeave }) {
  if (!cards?.length) return null
  return (
    <div className="mb-6">
      <div className="flex items-center gap-2 mb-2">
        <h3 className="font-display text-text-primary">{title}</h3>
        <span className={`text-xs px-2 py-0.5 rounded ${badgeColor}`}>{badge}</span>
      </div>
      <ul className="divide-y divide-border">
        {cards.map((card) => (
          <CardRow key={card.card_name} card={card} onHover={onHover} onLeave={onLeave} />
        ))}
      </ul>
    </div>
  )
}

/* ---- Seed Card Item ---- */
function SeedCardItem({ card, onHover, onLeave }) {
  const ref = useRef(null)
  return (
    <li
      ref={ref}
      className="flex items-center gap-2 text-sm hover:bg-bg-raised rounded px-1 py-0.5 transition-colors"
      style={{ cursor: card.image ? 'pointer' : 'default' }}
      onMouseEnter={() => {
        if (card.image && ref.current) onHover(card.image, ref.current.getBoundingClientRect())
      }}
      onMouseLeave={onLeave}
    >
      <span className="text-text-muted w-5 text-right">{card.qty}x</span>
      <span className="text-text-primary flex-1">{card.name}</span>
      {card.threshold > 0 && <span className="text-text-muted text-xs">{card.threshold}</span>}
    </li>
  )
}

/* ---- Seed Deck Contents ---- */
function SeedDeckContents({ cards, onHover, onLeave }) {
  if (!cards?.length) return null

  const groups = {}
  CARD_TYPE_ORDER.forEach((t) => { groups[t] = [] })
  cards.forEach((card) => {
    const type = getSeedCardType(card.type)
    groups[type].push(card)
  })
  Object.values(groups).forEach((group) => {
    group.sort((a, b) => (a.threshold || 0) - (b.threshold || 0) || a.name.localeCompare(b.name))
  })

  return (
    <div className="mb-8">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {CARD_TYPE_ORDER.map((type) => {
          const group = groups[type]
          if (!group.length) return null
          const heading = type === 'Site' ? 'Atlas' : type + 's'
          return (
            <div key={type} className="bg-bg-surface rounded-lg p-3 border border-border">
              <h4 className="text-xs text-secondary font-semibold mb-2 uppercase tracking-wide">{heading}</h4>
              <ul className="space-y-1">
                {group.map((card) => (
                  <SeedCardItem key={card.name} card={card} onHover={onHover} onLeave={onLeave} />
                ))}
              </ul>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ---- Similar Seeds ---- */
function SimilarSeeds({ seeds, imageFiles }) {
  if (!seeds) return null
  return (
    <div className="mt-8">
      <h3 className="font-display text-text-primary mb-3">Similar Tournament Decks</h3>
      {seeds.length === 0 ? (
        <p className="text-text-muted text-sm">No similar tournament decks found.</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {seeds.map((seed) => {
            const pct = Math.round(seed.similarity * 100)
            const imgFile = getAvatarImagePath(seed.avatar_name, imageFiles)
            return (
              <Link
                key={seed.deck_id}
                to={`/deck-rec/${encodeURIComponent(seed.deck_id)}`}
                className="flex items-center gap-3 bg-bg-surface rounded-lg p-3 border border-border hover:bg-bg-raised transition-colors"
              >
                <div className="w-8 h-8 rounded-full bg-bg-raised flex items-center justify-center overflow-hidden flex-shrink-0">
                  {imgFile ? (
                    <img src={`/avatar-images/${imgFile}`} alt={seed.avatar_name} className="w-full h-full object-cover" loading="lazy" />
                  ) : (
                    <span className="text-xs text-text-muted">{(seed.avatar_name || '?')[0]}</span>
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-secondary font-display truncate">{seed.deck_name}</div>
                  <div className="text-xs text-text-muted">{seed.avatar_name} &bull; {seed.event_name}</div>
                </div>
                <div className="text-xs text-text-muted whitespace-nowrap">{pct}% match</div>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}

/* ---- Main Page ---- */
export default function DeckDetail() {
  const { deckId } = useParams()
  const [data, setData] = useState(null)
  const [imageFiles, setImageFiles] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showFringe, setShowFringe] = useState(false)
  const [viewMode, setViewMode] = useState('visual')
  const [popup, setPopup] = useState({ image: null, rect: null })

  usePageTitle(data?.seed?.deck_name || 'Deck Archetype')

  useEffect(() => {
    setLoading(true)
    setData(null)
    setError(null)
    setShowFringe(false)
    Promise.all([getDeckRecommendations(deckId), getAvatarImageFiles()])
      .then(([recData, imgs]) => {
        setData(recData)
        setImageFiles(imgs || [])
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [deckId])

  const handleHover = useCallback((image, rect) => setPopup({ image, rect }), [])
  const handleLeave = useCallback(() => setPopup({ image: null, rect: null }), [])

  if (loading) return <Spinner className="py-20" />
  if (error) {
    return (
      <div className="text-center py-8">
        <p className="text-accent-red mb-4">{error}</p>
        <Link to="/deck-rec" className="text-secondary hover:underline">&larr; Back to Deck Rec</Link>
      </div>
    )
  }
  if (!data) return null

  const { seed } = data
  const avatarImg = getAvatarImagePath(seed.avatar_name, imageFiles)
  const tcgUrl = buildTcgPlayerUrl(data.seed_cards)
  const winRatePct = data.win_rate != null ? `${Math.round(data.win_rate * 100)}%` : null

  return (
    <div>
      <Link to="/deck-rec" className="text-sm text-text-muted hover:text-secondary mb-4 inline-block">
        &larr; Back to Sorcery Deck Recs
      </Link>

      {/* Header */}
      <div className="bg-bg-surface rounded-lg p-5 border border-border mb-6">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-display text-secondary mb-2">{seed.deck_name || 'Unnamed Deck'}</h1>
            <div className="flex items-center gap-2 text-sm text-text-muted mb-1">
              Avatar:
              <span className="inline-flex items-center gap-1.5 font-semibold text-text-primary">
                {avatarImg && (
                  <img src={`/avatar-images/${avatarImg}`} alt={seed.avatar_name} className="w-5 h-5 rounded-full object-cover" loading="lazy" />
                )}
                {seed.avatar_name}
              </span>
            </div>
            <div className="text-sm text-text-muted mb-1">Event: <span className="text-text-primary">{seed.event_name}</span></div>
            <div className="text-sm text-text-muted mb-2">Player: <span className="text-text-primary">{seed.player_name}</span></div>
            {seed.curiosa_url && (
              <a
                href={seed.curiosa_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-secondary hover:underline"
              >
                View on Curiosa ↗
              </a>
            )}
          </div>
          {tcgUrl && (
            <a
              href={tcgUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 bg-green-600 hover:bg-green-700 text-white text-sm px-4 py-2 rounded transition-colors whitespace-nowrap"
            >
              Buy on TCGPlayer ↗
            </a>
          )}
        </div>
        {seed.primer && (
          <div className="mt-3 text-sm text-text-muted italic border-t border-border pt-3">{seed.primer}</div>
        )}
      </div>

      {/* Cluster Stats */}
      <div className="flex flex-wrap gap-6 mb-6 text-sm">
        <div className="text-text-muted">
          Community builds matched: <strong className="text-text-primary">{data.cluster_size}</strong>
        </div>
        {winRatePct && (
          <div className="text-text-muted">
            Summit win rate: <strong className="text-text-primary">{winRatePct}</strong>
            <span className="text-text-muted/50 ml-1">({data.wins}W / {data.losses}L)</span>
          </div>
        )}
      </div>

      {/* Empty cluster message */}
      {data.cluster_size === 0 && (
        <div className="bg-bg-surface rounded-lg p-4 border border-border mb-6 text-sm text-text-muted">
          No community builds found matching this archetype at the current threshold.<br />
          This seed deck may be highly unique or the archive may not yet have similar builds.
        </div>
      )}

      {/* Seed Deck Contents */}
      {data.seed_spellbook?.length > 0 && (
        <>
          <div className="flex items-center gap-3 mb-3">
            <h3 className="font-display text-text-primary">Deck Contents</h3>
            <div className="inline-flex bg-bg-raised border border-border rounded-lg overflow-hidden">
              <button
                onClick={() => setViewMode('list')}
                className={`px-3 py-1 text-xs font-medium transition-colors ${
                  viewMode === 'list' ? 'bg-secondary text-black' : 'text-text-muted hover:text-text-primary'
                }`}
              >
                List
              </button>
              <button
                onClick={() => setViewMode('visual')}
                className={`px-3 py-1 text-xs font-medium transition-colors ${
                  viewMode === 'visual' ? 'bg-secondary text-black' : 'text-text-muted hover:text-text-primary'
                }`}
              >
                Visual
              </button>
            </div>
          </div>
          {viewMode === 'list' ? (
            <SeedDeckContents cards={data.seed_spellbook} onHover={handleHover} onLeave={handleLeave} />
          ) : (
            <DeckVisualizer cards={data.seed_spellbook} />
          )}
        </>
      )}

      {/* Card Tiers */}
      {data.cluster_size > 0 && (
        <>
          <TierSection
            title="Core Cards"
            badge="≥ 80%"
            badgeColor="bg-green-500/20 text-green-400"
            cards={data.core_cards}
            onHover={handleHover}
            onLeave={handleLeave}
          />
          <TierSection
            title="Common Cards"
            badge="50-79%"
            badgeColor="bg-blue-500/20 text-blue-400"
            cards={data.common_cards}
            onHover={handleHover}
            onLeave={handleLeave}
          />
          <TierSection
            title="Tech Choices"
            badge="20-49%"
            badgeColor="bg-yellow-500/20 text-yellow-400"
            cards={data.tech_cards}
            onHover={handleHover}
            onLeave={handleLeave}
          />

          {/* Fringe toggle */}
          {data.fringe_cards?.length > 0 && (
            <>
              <div className="text-center mb-4">
                <button
                  className="text-sm text-text-muted hover:text-secondary border border-border rounded px-4 py-1.5 transition-colors"
                  onClick={() => setShowFringe((v) => !v)}
                >
                  {showFringe ? 'Hide Fringe Cards' : 'Show Fringe Cards'}
                </button>
              </div>
              {showFringe && (
                <TierSection
                  title="Fringe Cards"
                  badge="< 20%"
                  badgeColor="bg-red-500/20 text-red-400"
                  cards={data.fringe_cards}
                  onHover={handleHover}
                  onLeave={handleLeave}
                />
              )}
            </>
          )}
        </>
      )}

      {/* Similar Seeds */}
      <SimilarSeeds seeds={data.similar_seeds} imageFiles={imageFiles} />

      {/* Card Image Popup */}
      <CardImagePopup imageFile={popup.image} anchorRect={popup.rect} />
    </div>
  )
}
