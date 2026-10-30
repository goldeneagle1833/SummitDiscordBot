import { useEffect, useState } from 'react'
import DeckVisualizer from '@/components/deck/DeckVisualizer'
import AvatarArtCard from './AvatarArtCard'
import { getFeaturedDeck } from '@/api/players'
import { getAvatarImageFiles } from '@/api/cards'
import { getDeckSourceLabel } from '@/utils/deckLinks'
import { getWinRateColor } from '@/utils/winRateColor'

// Sizes the tile as one item of the header's wrapping row
const SLOT = 'w-full sm:flex-[1_1_300px] sm:max-w-md'

/** The full list, opened from the tile. */
function DeckListModal({ deck, onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[1100] bg-black/70 overflow-y-auto" onClick={onClose}>
      <div
        role="dialog"
        aria-label={deck.name}
        className="bg-bg-surface border border-border rounded-xl max-w-5xl mx-4 sm:mx-auto my-6 sm:my-10 p-5 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-xs font-bold uppercase tracking-wider text-text-muted">Featured Deck</h2>
            <p className="text-xl font-display text-text-primary break-words">{deck.name}</p>
            {deck.avatar && <p className="text-sm text-text-muted">{deck.avatar}</p>}
          </div>
          <div className="flex items-center gap-4">
            <a href={deck.url} target="_blank" rel="noopener noreferrer" className="text-sm text-secondary hover:underline">
              View on {getDeckSourceLabel(deck.url)} &rarr;
            </a>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="h-9 w-9 rounded-lg border border-border text-text-muted hover:text-text-primary hover:border-secondary"
            >
              &times;
            </button>
          </div>
        </div>
        <DeckVisualizer spellbook={deck.spellbook} atlas={deck.atlas} sideboard={deck.sideboard} />
      </div>
    </div>
  )
}

/**
 * The featured deck as a tile in the profile header, styled like the avatar
 * tiles: the avatar's art behind the deck name and its record. Tapping it
 * opens the full list. The deck is one the player pasted, or by default their
 * most-played deck that is public on sorcerytcg.com or Sorcery Online.
 * Visitors see nothing when there is none; the owner gets a small prompt.
 */
export default function FeaturedDeck({ playerId, isOwner, onEdit, recentDecks = [], refreshKey = 0, onLoaded }) {
  const [deck, setDeck] = useState(undefined)
  const [mode, setMode] = useState('auto')
  const [imageFiles, setImageFiles] = useState([])
  const [open, setOpen] = useState(false)

  useEffect(() => {
    let active = true
    getFeaturedDeck(playerId)
      .then((res) => {
        if (!active) return
        setDeck(res?.deck || null)
        setMode(res?.mode || 'auto')
        onLoaded?.(res || null)
      })
      .catch(() => active && setDeck(null))
    return () => {
      active = false
    }
  }, [playerId, refreshKey]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!deck?.avatar) return undefined
    let active = true
    getAvatarImageFiles().then((files) => active && setImageFiles(files || [])).catch(() => {})
    return () => {
      active = false
    }
  }, [deck?.avatar])

  if (deck === undefined) return null

  if (!deck) {
    if (!isOwner) return null
    return (
      <section
        aria-label="Featured deck"
        className={`${SLOT} rounded-xl border border-dashed border-border bg-bg-raised p-4 flex flex-col gap-3`}
      >
        <div>
          <h2 className="text-xs font-bold uppercase tracking-wider text-text-muted">Featured Deck</h2>
          <p className="text-sm text-text-muted mt-1">
            {mode === 'off'
              ? 'Turned off. Nobody sees a featured deck on your profile.'
              : 'Your most-played deck shows here once it is public on sorcerytcg.com or Sorcery Online.'}
          </p>
        </div>
        <button
          type="button"
          onClick={onEdit}
          className="self-start h-9 px-3 text-sm font-semibold rounded-lg bg-secondary text-black hover:opacity-90"
        >
          {mode === 'off' ? 'Turn on' : 'Choose a deck'}
        </button>
      </section>
    )
  }

  // Its record, when the deck is one the profile already lists under Recent Decks
  const record = recentDecks.find((d) => d.url === deck.url)

  return (
    <section aria-label="Featured deck" className={`${SLOT} relative`}>
      {isOwner && (
        <button
          type="button"
          onClick={onEdit}
          className="absolute top-3 right-3 z-10 h-8 px-3 rounded-lg border border-white/20 bg-black/60 text-xs text-gray-200 hover:border-secondary hover:text-secondary"
        >
          Edit
        </button>
      )}
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={`Show the cards in ${deck.name}`}
        className="block w-full text-left"
      >
        <AvatarArtCard name={deck.avatar || ''} imageFiles={imageFiles} className="min-h-[170px] hover:border-secondary/60 transition-colors">
          <div className="text-xs font-bold uppercase tracking-wider text-gray-300 pr-14">
            Featured Deck
            {deck.picked === 'auto' && <span className="normal-case tracking-normal text-secondary"> · Most played</span>}
          </div>
          <h3 className="text-xl font-bold text-white leading-tight mt-1 break-words">{deck.name}</h3>
          {deck.avatar && <div className="text-sm text-gray-300 mt-0.5">{deck.avatar}</div>}
          <div className="mt-auto pt-4 flex items-end justify-between gap-3">
            {record && record.total_games > 0 ? (
              <div>
                <div className="text-3xl font-extrabold tabular-nums leading-none" style={{ color: getWinRateColor(record.win_rate) }}>
                  {record.win_rate}%
                </div>
                <div className="text-sm text-gray-200 mt-1 tabular-nums">{record.wins}W · {record.losses}L</div>
              </div>
            ) : (
              <span />
            )}
            <span className="text-sm font-semibold text-secondary">View cards &rarr;</span>
          </div>
        </AvatarArtCard>
      </button>
      {open && <DeckListModal deck={deck} onClose={() => setOpen(false)} />}
    </section>
  )
}
