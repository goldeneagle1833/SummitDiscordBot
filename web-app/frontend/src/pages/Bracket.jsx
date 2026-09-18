import { useState, useEffect, useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  getBracket,
  getBracketDecks,
  reportBracketMatch,
  confirmBracketMatch,
  adminSetMatchResult,
  adminResetMatch,
} from '@/api/brackets'
import BracketTree from '@/components/bracket/BracketTree'
import DeckPanel from '@/components/bracket/DeckPanel'
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
      <div className="bg-bg-surface border border-border rounded-lg p-5 w-full max-w-sm">
        <h2 className="text-lg font-display mb-1">Report your result</h2>
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
              className="w-full px-3 py-2 rounded bg-bg-raised border border-border text-sm text-left hover:border-secondary disabled:opacity-50"
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

export default function Bracket() {
  const { slug } = useParams()
  const { user } = useAuth()
  const isAdmin = Boolean(user?.is_admin)
  const [data, setData] = useState(null)
  const [decks, setDecks] = useState(null)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [reporting, setReporting] = useState(null)

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

  async function handleAdminAction(action, match, winnerUserId) {
    try {
      if (action === 'result') {
        await adminSetMatchResult(slug, match.match_no, winnerUserId)
      } else if (action === 'reset') {
        await adminResetMatch(slug, match.match_no)
      }
      load()
    } catch (e) {
      setNotice(e.message)
    }
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-accent-red">{error}</p>
        <Link to="/brackets" className="text-secondary hover:underline text-sm">
          All brackets
        </Link>
      </div>
    )
  }
  if (!data) return <Spinner />

  const { bracket, rounds, champion, entrants } = data
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

  return (
    <div className="max-w-full px-4 py-6 space-y-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-2xl font-display text-text-primary">{bracket.name}</h1>
          <p className="text-sm text-text-muted">
            {entrants.length} players
            {bracket.elo_event_name ? ` · seeded from ${bracket.elo_event_name}` : ''}
            {bracket.status === 'complete'
              ? ' · finished'
              : liveRound
                ? ` · ${liveRound.title} in progress`
                : ''}
            {` · ${played}/${allMatches.length} matches played`}
          </p>
        </div>
        <Link to="/brackets" className="text-sm text-secondary hover:underline">
          All brackets
        </Link>
      </div>

      {champion && (
        <div className="bg-gradient-to-r from-amber-400/10 to-transparent border border-amber-400/40 rounded-lg px-5 py-4 flex items-center gap-4">
          {avatarUrl(championEntrant, 128) ? (
            <img
              src={avatarUrl(championEntrant, 128)}
              alt=""
              className="w-14 h-14 rounded-full object-cover ring-2 ring-amber-400/60"
            />
          ) : (
            <span className="w-14 h-14 rounded-full bg-bg-elevated ring-2 ring-amber-400/60" />
          )}
          <div>
            <p className="text-xs uppercase tracking-wider text-text-muted">Winner</p>
            <p className="text-xl font-semibold text-amber-400">
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
        </div>
      )}

      {!user && (
        <p className="text-sm text-text-muted">
          <Link to="/login" className="text-secondary hover:underline">Log in</Link>{' '}
          to report your own matches.
        </p>
      )}

      {needsYou.length > 0 && (
        <div className="bg-secondary/10 border border-secondary/40 rounded-lg px-4 py-3 text-sm">
          You have {needsYou.length} match{needsYou.length > 1 ? 'es' : ''} waiting on you —
          the highlighted one{needsYou.length > 1 ? 's' : ''} below.
        </div>
      )}

      {notice && <p className="text-sm text-text-muted">{notice}</p>}

      <BracketTree
        rounds={rounds}
        onReport={setReporting}
        onConfirm={handleConfirm}
        onAdminAction={isAdmin ? handleAdminAction : null}
        isAdmin={isAdmin}
        avatars={avatars}
      />

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
