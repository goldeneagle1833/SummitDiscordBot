import { useState, useEffect, useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  listBrackets,
  getBracket,
  getBracketDecks,
  reportBracketMatch,
  confirmBracketMatch,
  openBracketMatchTable,
  adminSetMatchResult,
  adminResetMatch,
  adminSetMatchReplay,
  adminClearMatchReplay,
  adminSwapBracketPlayers,
  adminPublishBracketToTop8,
} from '@/api/brackets'
import BracketTree from '@/components/bracket/BracketTree'
import DeckPanel from '@/components/bracket/DeckPanel'
import BracketSwitcher from '@/components/bracket/BracketSwitcher'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'
import { useAuth } from '@/context/AuthContext'
import { avatarMap, avatarUrl } from '@/utils/avatar'

function ReportModal({ match, slug, onClose, onDone }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function submit(winnerUserId) {
    setBusy(true)
    setError(null)
    try {
      await reportBracketMatch(slug, match.match_no, winnerUserId)
      onDone()
    } catch (e) {
      setError(e.message)
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="bg-bg-surface border border-border rounded-sm p-5 w-full max-w-sm">
        <h2 className="text-lg font-semibold mb-1">Report your result</h2>
        <p className="text-sm text-text-muted mb-4">
          {match.round_title}. Your opponent confirms it before the winner moves on.
        </p>

        <div className="space-y-2">
          {[
            { id: match.p1_user_id, name: match.p1_name, seed: match.p1_seed },
            { id: match.p2_user_id, name: match.p2_name, seed: match.p2_seed },
          ].map((player) => (
            <button
              key={player.id}
              disabled={busy}
              onClick={() => submit(player.id)}
              className="w-full px-3 py-2 rounded-sm bg-bg-raised border border-border text-sm text-left hover:border-secondary disabled:opacity-50"
            >
              <span className="text-text-muted text-xs mr-2">{player.seed}</span>
              {player.name} won
            </button>
          ))}
        </div>

        {error && <p className="text-accent-red text-sm mt-3">{error}</p>}

        <button
          onClick={onClose}
          disabled={busy}
          className="mt-4 text-sm text-text-muted hover:text-text-primary"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

/**
 * One bracket, with tabs across the top to switch to any other.
 *
 * `/brackets` renders this with the active bracket's slug passed in (and the
 * list it already loaded); `/brackets/:slug` takes the slug from the URL.
 */
export default function Bracket({ slug: slugProp, brackets: bracketsProp } = {}) {
  const params = useParams()
  const slug = slugProp || params.slug
  const { user } = useAuth()
  const isAdmin = Boolean(user?.is_admin)
  const [data, setData] = useState(null)
  const [decks, setDecks] = useState(null)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [reporting, setReporting] = useState(null)
  const [editingPairings, setEditingPairings] = useState(false)
  const [fetchedBrackets, setFetchedBrackets] = useState(null)
  const brackets = bracketsProp || fetchedBrackets

  useEffect(() => {
    if (bracketsProp) return
    Promise.resolve(listBrackets())
      .then((res) => setFetchedBrackets(res?.brackets || []))
      .catch(() => setFetchedBrackets([]))
  }, [bracketsProp])

  usePageTitle(data?.bracket?.name || 'Bracket')

  const loadDecks = useCallback(
    () => getBracketDecks(slug).then(setDecks).catch(() => setDecks(null)),
    [slug],
  )

  const load = useCallback(() => {
    getBracket(slug)
      .then((res) => {
        setData(res)
        setError(null)
        return loadDecks()
      })
      .catch((e) => setError(e.status === 404 ? 'Bracket not found.' : 'Could not load this bracket.'))
  }, [slug, loadDecks])

  useEffect(() => {
    load()
  }, [load])

  async function handleConfirm(match, agree) {
    try {
      await confirmBracketMatch(slug, match.match_no, agree)
      setNotice(agree ? 'Result confirmed.' : 'Result disputed — the match is open again.')
      load()
    } catch (e) {
      setNotice(e.message)
    }
  }

  async function handleOpenTable(match) {
    setNotice('Opening a table on Sorcery Online…')
    try {
      await openBracketMatchTable(slug, match.match_no)
      setNotice('Table ready — use "Join your table" on your match.')
      load()
    } catch (e) {
      setNotice(e.message)
    }
  }

  async function handleAdminAction(action, match, value) {
    try {
      if (action === 'result') {
        await adminSetMatchResult(slug, match.match_no, value)
      } else if (action === 'reset') {
        await adminResetMatch(slug, match.match_no)
      } else if (action === 'replay') {
        await adminSetMatchReplay(slug, match.match_no, value)
      } else if (action === 'clear-replay') {
        await adminClearMatchReplay(slug, match.match_no)
      }
      load()
    } catch (e) {
      setNotice(e.message)
    }
  }

  async function handleSwap(seed, withSeed) {
    try {
      const res = await adminSwapBracketPlayers(slug, seed, withSeed)
      setNotice(`Swapped ${res.swapped.join(' and ')}.`)
      load()
    } catch (e) {
      setNotice(e.message)
    }
  }

  async function handlePublishToTop8() {
    setNotice('Writing the Top 8 event…')
    try {
      const res = await adminPublishBracketToTop8(slug)
      setNotice(`Top 8 page updated with ${res.top8 + res.rest} decklists.`)
      load()
    } catch (e) {
      setNotice(e.message)
    }
  }

  if (error) {
    return (
      <div className="max-w-full px-4 py-6 space-y-5">
        <BracketSwitcher brackets={brackets} currentSlug={slug} />
        <div className="text-center py-12">
          <p className="text-accent-red">{error}</p>
          <Link to="/brackets" className="text-secondary hover:underline text-sm">
            Back to the current bracket
          </Link>
        </div>
      </div>
    )
  }
  if (!data || data.bracket?.slug !== slug) {
    return (
      <div className="max-w-full px-4 py-6 space-y-5">
        <BracketSwitcher brackets={brackets} currentSlug={slug} />
        <Spinner />
      </div>
    )
  }

  const { bracket, rounds, champion, entrants } = data
  // Nobody scouts their draw before the field is locked: the tree stays
  // hidden from players until every entrant has a decklist in. Admins still
  // see it, so they can chase the stragglers.
  const decksMissing = data.decks_missing ?? 0
  const bracketHidden = decksMissing > 0 && bracket.status !== 'complete' && !isAdmin
  const needsYou = rounds
    .flatMap((r) => r.matches)
    .filter((m) => m.viewer_can_report || m.viewer_can_confirm)

  const avatars = avatarMap(entrants, 64)
  const championEntrant = champion
    ? entrants.find((e) => String(e.user_id || '') === String(champion.user_id || ''))
    : null
  const allMatches = rounds.flatMap((r) => r.matches)
  const played = allMatches.filter((m) => m.state === 'complete').length
  const liveRound = rounds.find((r) =>
    r.matches.some((m) => m.playable && m.state !== 'complete'),
  )
  const canEditPairings =
    isAdmin &&
    bracket.status === 'published' &&
    allMatches.some((m) => m.p1_movable || m.p2_movable)

  return (
    <div className="max-w-full px-4 py-6 space-y-5">
      <BracketSwitcher brackets={brackets} currentSlug={slug} />

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p
            className={`text-[11px] font-semibold uppercase tracking-[0.18em] ${
              bracket.status === 'complete' ? 'text-text-muted' : 'text-accent-green'
            }`}
          >
            {bracket.status === 'complete'
              ? 'Final results'
              : liveRound
                ? `Live · ${liveRound.title}`
                : 'Live'}
          </p>
          <h1 className="text-3xl font-display text-text-primary leading-tight">{bracket.name}</h1>
          <p className="text-sm text-text-muted tabular-nums">
            {entrants.length} players
            {bracket.elo_event_name ? ` · seeded from ${bracket.elo_event_name}` : ''}
            {bracketHidden
              ? ' · waiting on decklists'
              : bracket.status === 'complete'
                ? ' · finished'
                : liveRound
                  ? ` · ${liveRound.title} in progress`
                  : ''}
            {!bracketHidden && ` · ${played}/${allMatches.length} matches played`}
          </p>
        </div>
        <div className="flex items-center gap-4">
          {canEditPairings && (
            <button
              onClick={() => setEditingPairings((on) => !on)}
              className={`text-sm px-3 py-1 rounded-sm border transition-colors ${
                editingPairings
                  ? 'bg-secondary text-black border-secondary'
                  : 'border-border text-text-muted hover:text-text-primary'
              }`}
            >
              {editingPairings ? 'Done editing' : 'Edit pairings'}
            </button>
          )}
        </div>
      </div>

      {canEditPairings && editingPairings && (
        <div className="bg-secondary/10 border-l-2 border-secondary px-4 py-3 text-sm">
          Drag a player onto another to swap their places. Players keep their seed and
          decklist. Only seats that haven’t been played, reported or given a Sorcery Online
          table can move.
        </div>
      )}

      {champion && (
        <div className="bg-bg-surface border border-border border-l-4 border-l-amber-400 px-5 py-4 flex items-center gap-4">
          {avatarUrl(championEntrant, 128) ? (
            <img
              src={avatarUrl(championEntrant, 128)}
              alt=""
              className="w-14 h-14 rounded-sm object-cover"
            />
          ) : (
            <span className="w-14 h-14 rounded-sm bg-bg-elevated" />
          )}
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">Champion</p>
            <p className="text-2xl font-semibold text-amber-400 leading-tight">
              {champion.user_id ? (
                <Link to={`/player/${champion.user_id}`} className="hover:underline">
                  {champion.display_name}
                </Link>
              ) : (
                champion.display_name
              )}
            </p>
            <p className="text-sm text-text-muted">Seed {champion.seed}</p>
          </div>
          {(bracket.event_folder || (isAdmin && bracket.status === 'complete')) && (
            <div className="ml-auto flex flex-col items-end gap-1 text-sm">
              {bracket.event_folder && (
                <Link
                  to={`/top-8/${encodeURIComponent(bracket.event_folder)}`}
                  className="text-secondary hover:underline"
                >
                  Decklists on the Top 8 page
                </Link>
              )}
              {isAdmin && bracket.status === 'complete' && (
                <button
                  onClick={handlePublishToTop8}
                  className="text-xs text-text-muted hover:text-text-primary"
                >
                  {bracket.event_folder ? 'Rebuild Top 8 event' : 'Add to Top 8 page'}
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {!user && (
        <p className="text-sm text-text-muted">
          <Link to="/login" className="text-secondary hover:underline">Log in</Link>{' '}
          to report your own matches.
        </p>
      )}

      {!bracketHidden && needsYou.length > 0 && (
        <div className="bg-secondary/10 border-l-2 border-secondary px-4 py-3 text-sm">
          You have {needsYou.length} match{needsYou.length > 1 ? 'es' : ''} waiting on you —
          the highlighted one{needsYou.length > 1 ? 's' : ''} below.
        </div>
      )}

      {isAdmin && decksMissing > 0 && bracket.status !== 'complete' && (
        <div className="bg-amber-400/10 border-l-2 border-amber-400 px-4 py-3 text-sm">
          Players can’t see the bracket yet — {decksMissing} decklist
          {decksMissing > 1 ? 's are' : ' is'} still to come. Only admins see the tree below.
        </div>
      )}

      {notice && <p className="text-sm text-text-muted">{notice}</p>}

      {bracketHidden ? (
        <div className="bg-bg-surface border border-border px-5 py-8 text-center space-y-1">
          <p className="text-lg font-semibold">The bracket is revealed once every decklist is in</p>
          <p className="text-sm text-text-muted">
            {decksMissing} of {entrants.length} players still
            {decksMissing === 1 ? ' needs' : ' need'} to submit a deck.
          </p>
        </div>
      ) : (
        <BracketTree
          rounds={rounds}
          onReport={setReporting}
          onConfirm={handleConfirm}
          onOpenTable={handleOpenTable}
          onAdminAction={isAdmin ? handleAdminAction : null}
          isAdmin={isAdmin}
          onSwap={canEditPairings && editingPairings ? handleSwap : undefined}
          avatars={avatars}
        />
      )}

      <DeckPanel slug={slug} roster={decks} isAdmin={isAdmin} onChanged={loadDecks} />

      {reporting && (
        <ReportModal
          match={reporting}
          slug={slug}
          onClose={() => setReporting(null)}
          onDone={() => {
            setReporting(null)
            setNotice('Reported. Your opponent has been asked to confirm.')
            load()
          }}
        />
      )}
    </div>
  )
}
