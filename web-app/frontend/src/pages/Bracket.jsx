import { useState, useEffect, useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  getBracket,
  reportBracketMatch,
  confirmBracketMatch,
  adminSetMatchResult,
  adminResetMatch,
} from '@/api/brackets'
import BracketTree from '@/components/bracket/BracketTree'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'
import { useAuth } from '@/context/AuthContext'

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
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [reporting, setReporting] = useState(null)

  usePageTitle(data?.bracket?.name || 'Bracket')

  const load = useCallback(() => {
    getBracket(slug)
      .then((res) => {
        setData(res)
        setError(null)
      })
      .catch((e) => setError(e.status === 404 ? 'Bracket not found.' : 'Could not load this bracket.'))
  }, [slug])

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

  return (
    <div className="max-w-full px-4 py-6 space-y-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-2xl font-display text-text-primary">{bracket.name}</h1>
          <p className="text-sm text-text-muted">
            {entrants.length} players
            {bracket.elo_event_name ? ` · seeded from ${bracket.elo_event_name}` : ''}
            {bracket.status === 'complete' ? ' · finished' : ''}
          </p>
        </div>
        <Link to="/brackets" className="text-sm text-secondary hover:underline">
          All brackets
        </Link>
      </div>

      {champion && (
        <div className="bg-bg-surface border border-amber-400/40 rounded-lg px-5 py-3">
          <p className="text-xs uppercase tracking-wider text-text-muted">Winner</p>
          <p className="text-lg font-semibold text-amber-400">
            {champion.display_name}
            <span className="text-text-muted text-sm font-normal"> (seed {champion.seed})</span>
          </p>
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
      />

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
