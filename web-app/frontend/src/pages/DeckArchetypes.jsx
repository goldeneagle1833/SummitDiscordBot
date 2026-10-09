import { useEffect, useMemo, useState } from 'react'
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

function DeckLink({ deck, label, description }) {
  if (!deck) return null
  const placement = bestPlacement(deck)
  const player = deckPlayer(deck)
  const content = (
    <>
      <span className="min-w-0">
        {label && <span className="block text-xs text-secondary font-semibold mb-1">{label}</span>}
        <span className="block text-sm font-semibold text-text-primary truncate">{deck.name}</span>
        <span className="block text-xs text-text-muted mt-1 truncate">
          {description || `${deck.avatar} · ${deck.elements || 'Elements unspecified'}`}
          {player && ` · ${player}`}
          {placement != null && ` · Best finish: #${placement}`}
          {deck.ranked && ` · Ranked ${deck.ranked.wins}–${deck.ranked.losses}`}
        </span>
      </span>
      {deck.url && <span aria-hidden="true" className="text-secondary shrink-0">↗</span>}
    </>
  )
  const className = 'flex items-center justify-between gap-3 rounded-lg border border-border bg-bg-raised/50 p-3'
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

function ArchetypeDetails({ group, source, imageFiles, onClose }) {
  const [zone, setZone] = useState('spellbook')
  const [showAll, setShowAll] = useState(false)
  const [detail, setDetail] = useState(null)
  const [detailError, setDetailError] = useState('')

  useEffect(() => {
    let active = true
    getDeckArchetype(group.id, source)
      .then((data) => { if (active) setDetail(data) })
      .catch((err) => { if (active) setDetailError(err.status === 404 ? 'This archetype was just regrouped. Close this panel and pick it again.' : 'Could not load this archetype.') })
    return () => { active = false }
  }, [group.id, source])

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

  return (
    <div className="fixed inset-0 z-[1000] flex justify-end bg-black/75" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="archetype-detail-title"
        className="w-full max-w-2xl h-full overflow-y-auto bg-bg-base border-l border-border shadow-2xl"
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
            <p className="text-xs text-text-muted mb-3">Real decks selected from this archetype. Open a list on Sorcery TCG.</p>
            <div className="grid gap-2">
              {recommendations.map((rec) => <DeckLink key={rec.deckId} deck={rec.deck} label={rec.label} />)}
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
                  onClick={() => setZone(name)}
                  className={`text-sm px-3 py-1.5 rounded border capitalize transition-colors ${zone === name ? 'border-secondary text-secondary bg-secondary/10' : 'border-border bg-bg-surface text-text-muted hover:border-secondary/40'}`}
                >{name}</button>
              ))}
            </div>
            <div className="rounded-lg border border-border bg-bg-surface divide-y divide-border/60">
              {patterns.length === 0 && <p className="p-3 text-sm text-text-muted">No cards recorded in this section.</p>}
              {patterns.map((card) => (
                <div key={card.name} className="flex items-center justify-between gap-4 px-3 py-2 text-sm">
                  <span className="text-text-primary min-w-0 truncate">{card.name}</span>
                  <span className="text-text-muted shrink-0 tabular-nums">{Math.round(card.rate * 100)}% · {card.avgCopies} avg.</span>
                </div>
              ))}
            </div>
          </section>
          <section>
            <h3 className="text-lg font-semibold text-text-primary mb-3">
              {members.length < group.size ? `Top ${formatNumber(members.length)} of ${formatNumber(group.size)} decks` : `All decks in this archetype (${members.length})`}
            </h3>
            <div className="grid gap-2">
              {(showAll ? members : members.slice(0, 10)).map((deck) => <DeckLink key={deck.id} deck={deck} />)}
            </div>
            {members.length > 10 && (
              <button type="button" className="mt-3 text-sm text-secondary hover:underline" onClick={() => setShowAll((value) => !value)}>
                {showAll ? 'Show fewer decks' : `Show all ${members.length} decks`}
              </button>
            )}
          </section>
        </div>
        )}
      </section>
    </div>
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
            <p>Each deck contributes once. Decks are compared with weighted Jaccard similarity over their Spellbooks, Atlases and Collections, counting copies of each card. Spellbook cards count most, and cards that nearly every deck plays count less than distinctive ones. Decks are only grouped with decks of the same Avatar and the same element pair (their top two elements by Spellbook copies), using hierarchical clustering. A popular Avatar and element pair can still split into several archetypes when its builds differ.</p>
            <p className="mt-2">These are statistical groups, not manually assigned labels such as “aggro” or “control”. Decks in a group are on average at least <strong className="text-text-primary">{Math.round((meta?.threshold ?? 0.35) * 100)}% similar</strong>. Changing the minimum deck count hides or shows smaller groups; it does not recalculate the clusters. With ranked decks included, one-off ranked lists that match nothing are left out.</p>
          </section>
          <section>
            <h3 className="text-base font-semibold text-text-primary mb-2">Deck recommendations</h3>
            <p>Recommended lists are actual decks. The representative list is the one most similar to the rest of its archetype. Others highlight the best tournament finish and the best ranked record. Card inclusion percentages describe how often a card appears among decks in that group.</p>
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

  useEffect(() => {
    let active = true
    getAvatarImageFiles()
      .then((files) => {
        if (active && Array.isArray(files)) setImageFiles(files)
      })
      .catch(() => {}) // Missing artwork must not prevent archetype browsing.
    return () => { active = false }
  }, [])

  useEffect(() => {
    let active = true
    let timer = null
    setData(null)
    setError('')
    setSelectedId(null)
    const load = () => {
      getDeckArchetypes(source)
        .then((result) => {
          if (!active) return
          // The server is still building its first snapshot; check back shortly.
          if (result.status === 'building') timer = setTimeout(load, BUILDING_POLL_MS)
          else setData(result)
        })
        .catch((err) => { if (active) setError(err.message || 'Could not load deck archetypes') })
    }
    load()
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [source])

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
          <span>Updated hourly · {Math.round((data?.meta?.threshold ?? 0.35) * 100)}% similarity</span>
        </div>
      </div>

      {!data ? (
        <p className="text-center text-text-muted py-12">Loading deck archetypes…</p>
      ) : groups.length === 0 ? (
        <p className="text-center text-text-muted py-12">No archetypes match these filters. Try a smaller minimum group size.</p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
          {groups.map((group) => <ArchetypeCard key={group.id} group={group} imageFiles={imageFiles} onSelect={() => setSelectedId(group.id)} />)}
        </div>
      )}

      <p className="mt-6 text-xs text-text-muted text-center">
        Top 8 results and wins are tournament placements. Ranked win rates come from games reported on Sorcerers Summit.
      </p>
      {showAbout && <AboutDataPanel meta={data?.meta} onClose={() => setShowAbout(false)} />}
      {selected && <ArchetypeDetails key={`${source}-${selected.id}`} group={selected} source={source} imageFiles={imageFiles} onClose={() => setSelectedId(null)} />}
    </div>
  )
}
