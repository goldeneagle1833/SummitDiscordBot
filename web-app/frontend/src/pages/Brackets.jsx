import { useState, useEffect } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { listBrackets, getMyBracketMatches } from '@/api/brackets'
import Spinner from '@/components/ui/Spinner'
import BracketSwitcher, { pickActiveBracket, pickBracketFor } from '@/components/bracket/BracketSwitcher'
import usePageTitle from '@/hooks/usePageTitle'
import { useAuth } from '@/context/AuthContext'
import Bracket from './Bracket'

/**
 * `/brackets` opens straight onto the event being played - or, between
 * events, the last one finished - with tabs to flip to any other. That is
 * the constructed top cut; `?format=limited` opens on the Limited one. A
 * format with no top cut yet opens on its newest community bracket.
 */
export default function Brackets() {
  usePageTitle('Season Top Cut')
  const { user } = useAuth()
  const [params] = useSearchParams()
  const wanted = params.get('format') === 'limited' ? 'limited' : 'constructed'
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

  const canOrganize = Boolean(user?.is_bracket_organizer)
  // Asked for a format by name: stay on it, even with nothing in it yet.
  const active = params.get('format')
    ? pickBracketFor(brackets, wanted)
    : pickBracketFor(brackets, wanted) || pickActiveBracket(brackets)
  if (!active) {
    return (
      <div className="max-w-full px-4 py-6 space-y-5">
        <BracketSwitcher
          brackets={brackets}
          openFormat={wanted}
          canOrganize={canOrganize}
        />
        <h1 className="text-2xl font-display text-text-primary">
          {wanted === 'limited' ? 'Limited Brackets' : 'Season Top Cut'}
        </h1>
        <p className="text-text-muted text-center py-12">
          {brackets.length
            ? `No ${wanted === 'limited' ? 'Limited' : 'Constructed'} bracket has been published yet.`
            : 'No top cut bracket has been published yet.'}
        </p>
      </div>
    )
  }

  // Matches the bracket on screen already flags itself; point out the rest.
  const elsewhere = myMatches.filter((m) => m.slug !== active.slug)

  return (
    <>
      {elsewhere.length > 0 && (
        <div className="mx-4 mt-6 bg-secondary/10 border-l-2 border-secondary px-4 py-3">
          <h2 className="text-sm font-semibold mb-1">Waiting on you in another bracket</h2>
          <ul className="space-y-1 text-sm">
            {elsewhere.map((match) => (
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
      <Bracket slug={active.slug} brackets={brackets} />
    </>
  )
}
