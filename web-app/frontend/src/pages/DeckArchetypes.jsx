import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import usePageTitle from '@/hooks/usePageTitle'
import { getAvatarImageFiles } from '@/api/cards'
import { getDeckArchetype, getDeckArchetypes } from '@/api/deckArchetypes'

// Archetypes are grouped on the server from the Top 8 page's tournament decks
// and every deck reported in a ranked match (services/deck_archetypes.py).
const ELEMENTS = ['Air', 'Earth', 'Fire', 'Water']
const SOURCES = [
  { value: 'all', label: 'Tournaments + Ranked' },
  { value: 'tournament', label: 'Tournaments only' },
]
// A win rate over fewer games than this is noise, so it doesn't rank.
const MIN_GAMES_FOR_WIN_RATE = 20
// While the server builds its first snapshot, check back this often.
const BUILDING_POLL_MS = 4000
// "Event size" options: tournaments that published at least this many decks.
const EVENT_SIZE_OPTIONS = [0, 8, 16, 32, 64, 100]
const NO_FILTERS = { from: '', to: '', minEventDecks: 0 }
// Card art shown beside the detail panel (Sorcery cards are 5:7).
const PREVIEW_WIDTH = 260
const PREVIEW_HEIGHT = Math.round(PREVIEW_WIDTH * 7 / 5)
const SORT_OPTIONS = [
  { value: 'wins', label: 'Most wins' },
  { value: 'top8', label: 'Most Top 8s' },
  { value: 'size', label: 'Most played' },
  { value: 'events', label: 'Most tournaments' },
  { value: 'rankedGames', label: 'Most ranked games', ranked: true },
  { value: 'winRate', label: 'Best ranked win rate', ranked: true },
  { value: 'alpha', label: 'Name A–Z' },
]

// Reuse Sorcerers Summit's existing Avatar artwork, served by Flask.
// The image inventory is shared with the Avatar Win Rates page.
function avatarImage(group, imageFiles) {
  const name = group.avatar
  if (!name || !imageFiles.length) return null

  const normalize = (value) => value.toLowerCase().replace(/[^a-z0-9]/g, '')
  const avatarName = normalize(name)
  const imageBase = (filename) => normalize(filename.replace(/\.(png|jpe?g|webp)$/i, ''))

  const match = imageFiles.find((filename) => imageBase(filename) === avatarName)
    || imageFiles.find((filename) => imageBase(filename).includes(avatarName))
    || imageFiles.find((filename) => avatarName.includes(imageBase(filename)))

  // An Avatar with no matching artwork (e.g. Templar) gets a plain card.
  return match ? `/avatar-images/${encodeURIComponent(match)}` : null
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString('en-US')
}

function availableElements(label) {
  return ELEMENTS.filter((element) => String(label || '').includes(element))
}

function formatPercent(rate) {
  return `${Math.round((rate || 0) * 100)}%`
}

function rankedRate(group) {
  return group.rankedGames >= MIN_GAMES_FOR_WIN_RATE ? group.rankedWinRate ?? -1 : -1
}

function groupSort(a, b, sort) {
  switch (sort) {
    case 'rankedGames': return b.rankedGames - a.rankedGames || b.size - a.size
    case 'winRate': return rankedRate(b) - rankedRate(a) || b.rankedGames - a.rankedGames
    case 'top8': return b.top8 - a.top8 || b.wins - a.wins || b.size - a.size
    case 'size': return b.size - a.size || b.top8 - a.top8 || b.wins - a.wins
    case 'events': return b.events - a.events || b.size - a.size
    case 'alpha': return a.name.localeCompare(b.name) || b.size - a.size
    default: return b.wins - a.wins || b.top8 - a.top8 || b.size - a.size
  }
}

function bestPlacement(deck) {
  const known = (deck.entries || [])
    .map((entry) => entry.placement)
    .filter((placement) => Number.isInteger(placement))
  return known.length ? Math.min(...known) : null
}

function deckPlayer(deck) {
  return deck.entries?.[0]?.player || deck.ranked?.player
}

// `tournament` shows the deck's event results only, never its ranked record.
function DeckLink({ deck, label, description, tournament = false }) {
  if (!deck) return null
  const placement = bestPlacement(deck)
  const player = tournament ? deck.entries?.[0]?.player : deckPlayer(deck)
  const content = (
    <>
      <span className="min-w-0">
        {label && <span className="block text-xs text-secondary font-semibold mb-1">{label}</span>}
        <span className="block text-sm font-semibold text-text-primary truncate">{deck.name}</span>
        <span className="block text-xs text-text-muted mt-1 truncate">
          {description || `${deck.avatar} · ${deck.elements || 'Elements unspecified'}`}
          {player && ` · ${player}`}
          {placement != null && ` · Best finish: #${placement}`}
          {deck.ranked && !tournament && ` · Ranked ${deck.ranked.wins}–${deck.ranked.losses}`}
        </span>
      </span>
      {(deck.deckRecId || deck.url) && <span aria-hidden="true" className="text-secondary shrink-0">{deck.deckRecId ? '→' : '↗'}</span>}
    </>
  )
  const className = 'flex items-center justify-between gap-3 rounded-lg border border-border bg-bg-raised/50 p-3'
  // Lists on Sorcery TCG open on Summit's Deck Rec page.
  if (deck.deckRecId) {
    return (
      <Link className={`${className} hover:border-secondary/60 transition-colors`} to={`/deck-rec/${encodeURIComponent(deck.deckRecId)}`}>
        {content}
      </Link>
    )
  }
  // Ranked decks reported without a link have no page to open.
  if (!deck.url) return <div className={className}>{content}</div>
  return (
    <a
      className={`${className} hover:border-secondary/60 transition-colors`}
      href={deck.url}
      target="_blank"
      rel="noopener noreferrer"
    >
      {content}
    </a>
  )
}

function rankedSummary(group) {
  if (!group.rankedGames) return null
  return `${formatNumber(group.rankedGames)} ranked game${group.rankedGames === 1 ? '' : 's'} · ${formatPercent(group.rankedWinRate)} win rate`
}

function ArchetypeCard({ group, imageFiles, onSelect }) {
  const image = avatarImage(group, imageFiles)
  const winning = group.wins > 0
  const placed = group.top8 > 0 || group.topCut > 0
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-label={`View ${group.name}, ${group.size} decks`}
      className="relative text-left rounded-soft overflow-hidden border border-border bg-bg-surface hover:border-primary/60 transition-colors group focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-secondary"
      style={{ minHeight: 190 }}
    >
      {image && (
        <div
          className="absolute inset-0 bg-cover bg-center transition-transform duration-300 group-hover:scale-105"
          style={{ backgroundImage: `url('${image}')`, backgroundPosition: 'center 25%', opacity: 0.62 }}
          aria-hidden="true"
        />
      )}
      <div className="absolute inset-0 bg-gradient-to-t from-bg-base via-bg-base/65 to-bg-base/25" aria-hidden="true" />
      <div className="relative flex flex-col justify-between h-full p-3 min-h-[190px]" style={{ textShadow: '0 1px 4px rgba(0,0,0,.75)' }}>
        <div>
          <span
            className={`absolute top-3 right-3 text-xl leading-none ${winning ? 'text-yellow-400' : placed ? 'text-gray-300' : 'text-text-muted/70'}`}
            title={winning ? 'Tournament-winning archetype' : placed ? 'Top Cut archetype' : 'No confirmed Top Cut'}
            aria-hidden="true"
          >
            {winning || placed ? '★' : '☆'}
          </span>
          <h2 className="font-bold text-lg text-text-primary leading-tight break-words pr-7">{group.name}</h2>
        </div>
        <div>
          <p className="text-xs text-text-primary/80 mb-2">
            {group.events} tournament{group.events === 1 ? '' : 's'}
            {group.rankedGames > 0 && <span className="block">{rankedSummary(group)}</span>}
          </p>
          <div className="grid grid-cols-3 border-t border-white/20 pt-2 text-center">
            {[
              { value: group.size, label: 'Decks', color: 'text-sky-300' },
              { value: group.top8, label: 'Top 8', color: 'text-violet-300' },
              { value: group.wins, label: 'Wins', color: 'text-yellow-400' },
            ].map((stat, index) => (
              <div key={stat.label} className={`min-w-0 px-1 ${index > 0 ? 'border-l border-white/15' : ''}`}>
                <div className={`font-bold text-lg tabular-nums ${stat.color}`}>
                  {formatNumber(stat.value)}
                </div>
                <div className="text-[11px] text-text-muted">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </button>
  )
}

function ArchetypeDetails({ group, source, filters, imageFiles, onClose }) {
  const [zone, setZone] = useState('spellbook')
  const [showAll, setShowAll] = useState(false)
  const [detail, setDetail] = useState(null)
  const [detailError, setDetailError] = useState('')
  const [open, setOpen] = useState(false)
  const [preview, setPreview] = useState(null)
  const panelRef = useRef(null)

  // Slide in from the right on the frame after mounting.
  useEffect(() => {
    const frame = requestAnimationFrame(() => setOpen(true))
    return () => cancelAnimationFrame(frame)
  }, [])

  // Card art for a hovered "Most played" row, shown in the dimmed space beside
  // the panel. Skipped when the window leaves no room beside it.
  // Sites (the atlas) are landscape cards whose images are stored upright, so
  // they are turned 90° clockwise.
  const showPreview = (card, event) => {
    const panel = panelRef.current?.getBoundingClientRect()
    const site = zone === 'atlas'
    const width = site ? PREVIEW_HEIGHT : PREVIEW_WIDTH
    const height = site ? PREVIEW_WIDTH : PREVIEW_HEIGHT
    if (!card.image || !panel || panel.left < width + 32) return
    const row = event.currentTarget.getBoundingClientRect()
    const top = Math.max(16, Math.min(row.top + row.height / 2 - height / 2, window.innerHeight - height - 16))
    setPreview({ image: card.image, name: card.name, site, width, height, top, right: window.innerWidth - panel.left + 24 })
  }

  useEffect(() => {
    let active = true
    getDeckArchetype(group.id, source, filters)
      .then((data) => { if (active) setDetail(data) })
      .catch((err) => { if (active) setDetailError(err.status === 404 ? 'This archetype has no decks right now. Close this panel and pick another.' : 'Could not load this archetype.') })
    return () => { active = false }
  }, [group.id, source, filters])

  useEffect(() => {
    const oldOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const handleKey = (event) => { if (event.key === 'Escape') onClose() }
    document.addEventListener('keydown', handleKey)
    return () => {
      document.body.style.overflow = oldOverflow
      document.removeEventListener('keydown', handleKey)
    }
  }, [onClose])

  const decks = detail?.decks || {}
  // The server already lists members best finish first, then most ranked games.
  const members = (detail?.members || []).map((id) => decks[id]).filter(Boolean)
  const patterns = (detail?.patterns || {})[zone] || []
  const recommendations = (detail?.recommendations || []).map((rec) => ({ ...rec, deck: decks[rec.deckId] })).filter((rec) => rec.deck)
  const image = avatarImage(group, imageFiles)

  return createPortal(
    <div
      className={`fixed inset-0 z-[1000] flex justify-end transition-colors duration-300 ${open ? 'bg-black/75' : 'bg-black/0'}`}
      onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}
    >
      {preview && (
        <div
          className="fixed pointer-events-none flex items-center justify-center"
          style={{ top: preview.top, right: preview.right, width: preview.width, height: preview.height }}
        >
          <img
            src={`/card-images/${encodeURIComponent(preview.image)}`}
            alt={preview.name}
            className={`max-w-none rounded-xl shadow-2xl ${preview.site ? 'rotate-90' : ''}`}
            style={{ width: PREVIEW_WIDTH, height: PREVIEW_HEIGHT }}
          />
        </div>
      )}
      <section
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="archetype-detail-title"
        className={`w-full md:w-1/2 h-full overflow-y-auto bg-bg-base border-l border-border shadow-2xl transition-transform duration-300 ease-out ${open ? 'translate-x-0' : 'translate-x-full'}`}
      >
        <div className="sticky top-0 z-20 flex justify-between items-center p-3 border-b border-border bg-bg-base/95 backdrop-blur-sm">
          <span className="uppercase text-xs tracking-widest font-semibold text-secondary">Deck Archetypes</span>
          <button type="button" onClick={onClose} className="px-3 py-1.5 rounded bg-bg-raised border border-border hover:border-secondary/70" aria-label="Close archetype details">Close ×</button>
        </div>
        <div className="relative overflow-hidden min-h-[180px] flex flex-col justify-end p-5 border-b border-border">
          {image && <div className="absolute inset-0 bg-cover bg-center" style={{ backgroundImage: `url('${image}')`, opacity: 0.4 }} aria-hidden="true" />}
          <div className="absolute inset-0 bg-gradient-to-t from-bg-base via-bg-base/70 to-transparent" aria-hidden="true" />
          <div className="relative">
            <p className="text-xs text-secondary font-semibold uppercase tracking-widest mb-2">
              {formatNumber(group.size)} decklists · {formatNumber(group.tournamentDecks)} from tournaments
            </p>
            <h2 id="archetype-detail-title" className="text-2xl sm:text-3xl font-display text-text-primary mb-2">{group.name}</h2>
            <p className="text-sm text-text-muted">{group.events} tournaments · {group.top8} Top 8 appearances · {group.wins} wins</p>
            {group.rankedGames > 0 && (
              <p className="text-sm text-text-muted mt-1">
                Ranked: {formatNumber(group.rankedWins)}–{formatNumber(group.rankedLosses)} across {formatNumber(group.rankedGames)} games ({formatPercent(group.rankedWinRate)})
              </p>
            )}
          </div>
        </div>
        {!detail ? (
          <p className="p-5 text-sm text-text-muted">{detailError || 'Loading archetype…'}</p>
        ) : (
        <div className="p-4 sm:p-5 space-y-8">
          <section>
            <h3 className="text-lg font-semibold text-text-primary mb-1">Recommended decklists</h3>
            <p className="text-xs text-text-muted mb-3">Decks from the Top 8 page in this archetype. Open a list on Summit's Deck Rec page.</p>
            <div className="grid gap-2">
              {recommendations.length === 0 && <p className="text-sm text-text-muted">No Top 8 decks in this archetype yet.</p>}
              {recommendations.map((rec) => <DeckLink key={rec.deckId} deck={rec.deck} label={rec.label} description={rec.deck.entries?.[0]?.event} tournament />)}
            </div>
          </section>
          <section>
            <h3 className="text-lg font-semibold text-text-primary mb-1">Most played cards</h3>
            <p className="text-xs text-text-muted mb-3">Card inclusion across the {formatNumber(group.size)} decklist{group.size === 1 ? '' : 's'} in this group.</p>
            <div className="flex gap-2 mb-3 flex-wrap">
              {['spellbook', 'atlas', 'collection'].map((name) => (
                <button
                  type="button"
                  key={name}
                  onClick={() => { setZone(name); setPreview(null) }}
                  className={`text-sm px-3 py-1.5 rounded border capitalize transition-colors ${zone === name ? 'border-secondary text-secondary bg-secondary/10' : 'border-border bg-bg-surface text-text-muted hover:border-secondary/40'}`}
                >{name}</button>
              ))}
            </div>
            <div className="rounded-lg border border-border bg-bg-surface divide-y divide-border/60">
              {patterns.length === 0 && <p className="p-3 text-sm text-text-muted">No cards recorded in this section.</p>}
              {patterns.map((card) => (
                <div
                  key={card.name}
                  className={`flex items-center justify-between gap-4 px-3 py-2 text-sm ${card.image ? 'hover:bg-bg-raised/60' : ''}`}
                  onMouseEnter={(event) => showPreview(card, event)}
                  onMouseLeave={() => setPreview(null)}
                >
                  <span className="text-text-primary min-w-0 truncate">{card.name}</span>
                  <span className="text-text-muted shrink-0 tabular-nums">{Math.round(card.rate * 100)}% · {card.avgCopies} avg.</span>
                </div>
              ))}
            </div>
          </section>
          <section>
            <h3 className="text-lg font-semibold text-text-primary mb-3">
              {members.length < (group.tournamentDecks ?? 0) ? `Top ${formatNumber(members.length)} of ${formatNumber(group.tournamentDecks)} tournament decks` : `Tournament decks in this archetype (${members.length})`}
            </h3>
            <div className="grid gap-2">
              {(showAll ? members : members.slice(0, 10)).map((deck) => <DeckLink key={deck.id} deck={deck} description={deck.entries?.[0]?.event} tournament />)}
            </div>
            {members.length === 0 && <p className="text-sm text-text-muted">No public tournament lists in this archetype yet.</p>}
            {members.length > 10 && (
              <button type="button" className="mt-3 text-sm text-secondary hover:underline" onClick={() => setShowAll((value) => !value)}>
                {showAll ? 'Show fewer decks' : `Show all ${members.length} decks`}
              </button>
            )}
          </section>
        </div>
        )}
      </section>
    </div>,
    document.body,
  )
}


function AboutDataPanel({ meta, onClose }) {
  useEffect(() => {
    const previousOverflow = document.body.style.overflow
    const previousFocus = document.activeElement
    document.body.style.overflow = 'hidden'
    const onKeyDown = (event) => { if (event.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKeyDown)
    document.getElementById('deck-archetypes-about-close')?.focus()
    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', onKeyDown)
      previousFocus?.focus?.()
    }
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[1000] flex justify-end bg-black/75" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="deck-archetypes-about-title"
        className="w-full max-w-2xl h-full overflow-y-auto bg-bg-base border-l border-border shadow-2xl"
      >
        <div className="sticky top-0 z-20 flex items-center justify-between gap-3 p-3 border-b border-border bg-bg-base/95 backdrop-blur-sm">
          <span className="uppercase text-xs tracking-widest font-semibold text-secondary">Dataset and methodology</span>
          <button id="deck-archetypes-about-close" type="button" onClick={onClose} className="px-3 py-1.5 rounded bg-bg-raised border border-border hover:border-secondary/70">Close ×</button>
        </div>
        <div className="p-4 sm:p-6 space-y-6 text-sm text-text-muted leading-relaxed">
          <header>
            <h2 id="deck-archetypes-about-title" className="text-2xl font-display text-text-primary mb-2">About the Data</h2>
            <p>This explorer groups real decklists by their card combinations, helping players discover recurring archetypes and find real decks to try. It is rebuilt from the site's own data about once an hour, so new Top 8 events and ranked matches show up on their own.</p>
          </header>
          <section>
            <h3 className="text-base font-semibold text-text-primary mb-2">Where the decks come from</h3>
            <p><strong className="text-text-primary">Tournaments</strong>: every decklist on the Top 8 page, plus tournament lists from the original archetype snapshot whose events aren't on the Top 8 page yet. <strong className="text-text-primary">Ranked</strong>: every deck reported in a ranked match on Sorcerers Summit, with its ranked win/loss record.</p>
            <p className="mt-2">Choose <strong className="text-text-primary">Tournaments only</strong> to group just the tournament lists. A deck that was played in a tournament and on ranked counts once, with both records.</p>
          </section>
          <section>
            <h3 className="text-base font-semibold text-text-primary mb-2">How archetypes are identified</h3>
            <p>Each deck contributes once. Decks are compared with weighted Jaccard similarity over their Spellbooks, Atlases and Collections, counting copies of each card. Spellbook cards count most, and cards that nearly every deck plays count less than distinctive ones. Every archetype is one Avatar and element pair (a deck's top two elements by Spellbook copies), so all decks with the same Avatar and elements are in the same group. Similarity decides the order inside a group: the deck most similar to the rest comes first.</p>
            <p className="mt-2">These are Avatar and element groups, not manually assigned labels such as “aggro” or “control”. Changing the minimum deck count hides or shows smaller groups. With ranked decks included, a ranked deck that is the only one of its Avatar and elements is left out.</p>
          </section>
          <section>
            <h3 className="text-base font-semibold text-text-primary mb-2">Deck recommendations</h3>
            <p>Recommended lists only come from decks on the Top 8 page. The representative list is the Top 8 deck most similar to the rest of its archetype. Others highlight the best tournament finish and the deck taken to the most tournaments. Ranked games never decide a recommendation. Card inclusion percentages describe how often a card appears among decks in that group.</p>
          </section>
          <section>
            <h3 className="text-base font-semibold text-text-primary mb-2">Dataset coverage</h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 my-3">
              {[
                { label: 'Tournament events', value: meta?.tournamentCount },
                { label: 'Tournament decklists', value: meta?.tournamentDecks },
                { label: 'Ranked decklists', value: meta?.source === 'tournament' ? null : meta?.rankedDecks },
                { label: 'Ranked games', value: meta?.source === 'tournament' ? null : meta?.rankedGames },
                { label: 'Decklists still loading', value: meta?.pendingDecks },
                { label: 'Unavailable decklists', value: meta?.unavailableDecks },
              ].map((stat) => (
                <div key={stat.label} className="rounded-lg border border-border bg-bg-surface p-3 text-center">
                  <div className="text-lg font-bold text-secondary tabular-nums">{stat.value == null ? '—' : formatNumber(stat.value)}</div>
                  <div className="text-xs text-text-muted">{stat.label}</div>
                </div>
              ))}
            </div>
            <p>The tournament archive combines online league events and in-person tournaments. Published lists differ in scope: some contain only a Top 8, some include additional finalists, and others provide a broader field. The number of published decks should not be treated as total attendance.</p>
            {meta?.pendingDecks > 0 && <p className="mt-2">Some older tournament lists are still being downloaded from Sorcery TCG and will appear as they arrive.</p>}
          </section>
          <section>
            <h3 className="text-base font-semibold text-text-primary mb-2">How to interpret the figures</h3>
            <p><strong className="text-text-primary">Decks</strong> counts lists grouped into an archetype. <strong className="text-text-primary">Top 8</strong> counts decks with a Top 8 finish. <strong className="text-text-primary">Wins</strong> counts tournament victories. These are not match win rates.</p>
            <p className="mt-2"><strong className="text-text-primary">Dates</strong> limit tournaments and ranked games to that range. Events with only a year in their name count for that whole year. <strong className="text-text-primary">Event size</strong> keeps only tournaments that published at least that many decklists; it doesn't affect ranked games. Filters change which decks and results count; they don't regroup decks.</p>
            <p className="mt-2"><strong className="text-text-primary">Ranked win rate</strong> is every ranked game played with a deck in the archetype. Sorting by win rate only ranks archetypes with at least {MIN_GAMES_FOR_WIN_RATE} ranked games.</p>
            <p className="mt-2">Missing placements are not counted as losses. Finalist-only events can overrepresent successful builds, so tournament figures describe the collected records rather than the entire competitive player population.</p>
          </section>
          <section>
            <h3 className="text-base font-semibold text-text-primary mb-2">Data limitations</h3>
            <p>Tournament decklists were retrieved after their events and may have been edited since. Ranked decks use the most recent list reported for each deck link. Element labels come from each deck's Spellbook thresholds.</p>
          </section>
        </div>
      </section>
    </div>
  )
}

export default function DeckArchetypes() {
  usePageTitle('Deck Archetypes')
  const [data, setData] = useState(null)
  const [imageFiles, setImageFiles] = useState([])
  const [error, setError] = useState('')
  const [avatar, setAvatar] = useState('all')
  const [element, setElement] = useState('all')
  const [sort, setSort] = useState('wins')
  const [minSize, setMinSize] = useState(4)
  const [top8Only, setTop8Only] = useState(false)
  const [selectedId, setSelectedId] = useState(null)
  const [showAbout, setShowAbout] = useState(false)
  const [source, setSource] = useState('all')
  const [filters, setFilters] = useState(NO_FILTERS)
  const [updating, setUpdating] = useState(false)

  useEffect(() => {
    let active = true
    getAvatarImageFiles()
      .then((files) => {
        if (active && Array.isArray(files)) setImageFiles(files)
      })
      .catch(() => {}) // Missing artwork must not prevent archetype browsing.
    return () => { active = false }
  }, [])

  // Switching between tournaments and ranked starts over; changing a filter
  // keeps the current cards on screen until the new numbers arrive.
  useEffect(() => {
    setData(null)
    setSelectedId(null)
  }, [source])

  useEffect(() => {
    let active = true
    let timer = null
    setError('')
    setUpdating(true)
    const load = () => {
      getDeckArchetypes(source, filters)
        .then((result) => {
          if (!active) return
          // The server is still building its first snapshot; check back shortly.
          if (result.status === 'building') {
            timer = setTimeout(load, BUILDING_POLL_MS)
            return
          }
          setData(result)
          setUpdating(false)
        })
        .catch((err) => {
          if (!active) return
          setError(err.message || 'Could not load deck archetypes')
          setUpdating(false)
        })
    }
    load()
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [source, filters])

  const setFilter = (name, value) => setFilters((current) => ({ ...current, [name]: value }))
  const filtersActive = filters.from || filters.to || filters.minEventDecks > 0

  const avatars = useMemo(() => {
    if (!data) return []
    return [...new Set(data.groups.flatMap((group) => group.avatars.map(([name]) => name)))].sort()
  }, [data])

  useEffect(() => {
    if (source === 'tournament' && SORT_OPTIONS.find((item) => item.value === sort)?.ranked) setSort('wins')
  }, [source, sort])

  const groups = useMemo(() => {
    if (!data) return []
    return data.groups
      .filter((group) => group.size >= minSize)
      .filter((group) => avatar === 'all' || group.avatars.some(([name]) => name === avatar))
      .filter((group) => element === 'all' || group.elements.some(([name]) => availableElements(name).includes(element)))
      .filter((group) => !top8Only || group.top8 > 0)
      .sort((a, b) => groupSort(a, b, sort))
  }, [data, avatar, element, sort, minSize, top8Only])

  const selected = data?.groups.find((group) => group.id === selectedId)

  if (error) {
    return <div className="rounded-lg bg-bg-surface border border-border p-6 text-accent-red">{error}. Please try again in a moment.</div>
  }

  return (
    <div>
      <header className="text-center mb-6">
        <h1 className="text-2xl font-display text-secondary mb-2">Deck Archetypes</h1>
        <p className="text-sm text-text-muted max-w-2xl mx-auto">
          Discover recurring Sorcery deck builds using similarity analysis of tournament decklists and ranked match decks.
        </p>
        <button
          type="button"
          onClick={() => setShowAbout(true)}
          className="mt-3 rounded-lg border border-border bg-bg-surface px-4 py-2 text-sm font-medium text-secondary hover:border-secondary/60 transition-colors"
          aria-haspopup="dialog"
        >
          About the Data
        </button>
      </header>

      <div className="rounded-lg border border-border bg-bg-surface p-3 mb-5">
        <div className="flex flex-wrap gap-2 mb-3" role="group" aria-label="Decks to include">
          {SOURCES.map((item) => (
            <button
              type="button"
              key={item.value}
              onClick={() => setSource(item.value)}
              aria-pressed={source === item.value}
              className={`text-sm px-3 py-1.5 rounded border transition-colors ${source === item.value ? 'border-secondary text-secondary bg-secondary/10' : 'border-border bg-bg-raised text-text-muted hover:border-secondary/40'}`}
            >{item.label}</button>
          ))}
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-text-muted min-w-[155px] flex-1 sm:flex-none">
            Avatar
            <select value={avatar} onChange={(event) => setAvatar(event.target.value)} className="bg-bg-raised border border-border rounded px-3 py-2 text-sm text-text-primary">
              <option value="all">All avatars</option>
              {avatars.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-text-muted min-w-[135px] flex-1 sm:flex-none">
            Element
            <select value={element} onChange={(event) => setElement(event.target.value)} className="bg-bg-raised border border-border rounded px-3 py-2 text-sm text-text-primary">
              <option value="all">All elements</option>
              {ELEMENTS.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-text-muted min-w-[140px] flex-1 sm:flex-none">
            Sort
            <select value={sort} onChange={(event) => setSort(event.target.value)} className="bg-bg-raised border border-border rounded px-3 py-2 text-sm text-text-primary">
              {SORT_OPTIONS.filter((item) => !item.ranked || source === 'all').map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-text-muted min-w-[140px] flex-1 sm:flex-none">
            Minimum decks
            <select value={minSize} onChange={(event) => setMinSize(Number(event.target.value))} className="bg-bg-raised border border-border rounded px-3 py-2 text-sm text-text-primary">
              {[1, 2, 3, 4, 5, 8, 10, 20, 50].map((value) => <option key={value} value={value}>{value} deck{value === 1 ? '' : 's'}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-text-muted min-w-[140px] flex-1 sm:flex-none">
            From
            <input
              type="date"
              value={filters.from}
              max={filters.to || undefined}
              onChange={(event) => setFilter('from', event.target.value)}
              className="bg-bg-raised border border-border rounded px-3 py-2 text-sm text-text-primary"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-text-muted min-w-[140px] flex-1 sm:flex-none">
            To
            <input
              type="date"
              value={filters.to}
              min={filters.from || undefined}
              onChange={(event) => setFilter('to', event.target.value)}
              className="bg-bg-raised border border-border rounded px-3 py-2 text-sm text-text-primary"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-text-muted min-w-[150px] flex-1 sm:flex-none">
            Event size
            <select value={filters.minEventDecks} onChange={(event) => setFilter('minEventDecks', Number(event.target.value))} className="bg-bg-raised border border-border rounded px-3 py-2 text-sm text-text-primary">
              {EVENT_SIZE_OPTIONS.map((value) => (
                <option key={value} value={value}>{value === 0 ? 'Any size' : `${value}+ decks`}</option>
              ))}
            </select>
          </label>
          {filtersActive && (
            <button type="button" onClick={() => setFilters(NO_FILTERS)} className="text-sm text-secondary hover:underline pb-2">
              Clear dates and size
            </button>
          )}
          <label className="flex items-center gap-2 text-sm text-text-muted pb-2 cursor-pointer">
            <input type="checkbox" checked={top8Only} onChange={(event) => setTop8Only(event.target.checked)} className="accent-yellow-500" />
            Has Top 8
          </label>
        </div>
        <div className="mt-3 pt-2 border-t border-border/70 flex flex-wrap justify-between gap-2 text-xs text-text-muted" aria-live="polite">
          <span>
            {data ? formatNumber(groups.length) : '…'} archetypes · {formatNumber(data?.meta?.fetchedDecks)} decks · {formatNumber(data?.meta?.tournamentCount)} tournaments
            {source === 'all' && data && ` · ${formatNumber(data.meta.rankedGames)} ranked games`}
          </span>
          <span>{updating && data ? 'Updating… · ' : ''}Updated hourly</span>
        </div>
      </div>

      {!data ? (
        <p className="text-center text-text-muted py-12">Loading deck archetypes…</p>
      ) : groups.length === 0 ? (
        <p className="text-center text-text-muted py-12">No archetypes match these filters. Try a smaller minimum group size, a wider date range or any event size.</p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
          {groups.map((group) => <ArchetypeCard key={group.id} group={group} imageFiles={imageFiles} onSelect={() => setSelectedId(group.id)} />)}
        </div>
      )}

      <p className="mt-6 text-xs text-text-muted text-center">
        Top 8 results and wins are tournament placements. Ranked win rates come from games reported on Sorcerers Summit.
      </p>
      {showAbout && <AboutDataPanel meta={data?.meta} onClose={() => setShowAbout(false)} />}
      {selected && <ArchetypeDetails key={`${source}-${selected.id}`} group={selected} source={source} filters={filters} imageFiles={imageFiles} onClose={() => setSelectedId(null)} />}
    </div>
  )
}
