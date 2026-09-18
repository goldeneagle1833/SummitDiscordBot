import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { listBrackets, getMyBracketMatches } from '@/api/brackets'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'
import { useAuth } from '@/context/AuthContext'

function StatusBadge({ status }) {
  const styles = {
    published: 'bg-accent-green/20 text-accent-green',
    complete: 'bg-bg-raised text-text-muted',
  }
  const labels = { published: 'In progress', complete: 'Finished' }
  return (
    <span className={`px-2 py-0.5 text-xs rounded ${styles[status] || styles.complete}`}>
      {labels[status] || status}
    </span>
  )
}

export default function Brackets() {
  usePageTitle('Brackets')
  const { user } = useAuth()
  const [brackets, setBrackets] = useState(null)
  const [myMatches, setMyMatches] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    listBrackets()
      .then((res) => setBrackets(res.brackets || []))
      .catch(() => setError('Could not load brackets.'))
  }, [])

  useEffect(() => {
    if (!user) return
    getMyBracketMatches()
      .then((res) => setMyMatches(res.matches || []))
      .catch(() => setMyMatches([]))
  }, [user])

  if (error) return <p className="text-center text-accent-red py-12">{error}</p>
  if (!brackets) return <Spinner />

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 space-y-5">
      <div>
        <h1 className="text-2xl font-display text-text-primary">Brackets</h1>
        <p className="text-sm text-text-muted mt-1">
          Postseason brackets. Players report their own matches; the opponent confirms.
        </p>
      </div>

      {myMatches.length > 0 && (
        <div className="bg-secondary/10 border border-secondary/40 rounded-lg p-4">
          <h2 className="text-sm font-semibold mb-2">Waiting on you</h2>
          <ul className="space-y-1 text-sm">
            {myMatches.map((match) => (
              <li key={`${match.slug}-${match.match_no}`}>
                <Link to={`/brackets/${match.slug}`} className="text-secondary hover:underline">
                  {match.bracket_name} — {match.round_title}
                </Link>
                <span className="text-text-muted">
                  {' '}
                  ({match.needs === 'report' ? 'report your result' : 'confirm the result'})
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {brackets.length === 0 ? (
        <p className="text-text-muted text-center py-12">No brackets have been published yet.</p>
      ) : (
        <ul className="space-y-3">
          {brackets.map((bracket) => (
            <li key={bracket.slug}>
              <Link
                to={`/brackets/${bracket.slug}`}
                className="block bg-bg-surface border border-border rounded-lg px-5 py-4 hover:border-secondary transition-colors"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium">{bracket.name}</span>
                  <StatusBadge status={bracket.status} />
                </div>
                <p className="text-sm text-text-muted mt-1">
                  {bracket.entrant_count} players
                  {bracket.champion
                    ? ` · won by ${bracket.champion.display_name}`
                    : bracket.open_matches
                      ? ` · ${bracket.open_matches} match${bracket.open_matches > 1 ? 'es' : ''} ready to play`
                      : ''}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
