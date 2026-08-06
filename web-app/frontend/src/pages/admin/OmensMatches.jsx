import { useState, useEffect, Fragment } from 'react'
import { Link } from 'react-router-dom'
import { get } from '@/api/client'
import usePageTitle from '@/hooks/usePageTitle'
import Spinner from '@/components/ui/Spinner'

const ELEMENT_IMG = '/static/images/elements/'
const ELEMENT_FILE = {
  Earth: 'earth.png',
  Fire: 'fire.png',
  Water: 'water.png',
  Air: 'wind.png',
}

function ElementIcons({ elements }) {
  if (!elements?.length) return null
  return (
    <span className="flex gap-0.5 inline-flex">
      {elements.map((el) => {
        const file = ELEMENT_FILE[el]
        if (!file) return <span key={el} className="text-xs">{el}</span>
        return <img key={el} src={`${ELEMENT_IMG}${file}`} alt={el} title={el} className="w-4 h-4" />
      })}
    </span>
  )
}

function DeckBreakdown({ deck, label }) {
  if (!deck) return null
  const budgetPct = deck.max_budget > 0 ? Math.round((deck.total_points / deck.max_budget) * 100) : 0
  return (
    <div className="flex-1 min-w-[220px]">
      <div className="flex items-center gap-2 mb-2">
        <h5 className="text-xs font-semibold text-text-muted uppercase tracking-wide">{label}</h5>
        {deck.avatar && <span className="text-sm text-secondary font-medium">{deck.avatar}</span>}
        <ElementIcons elements={deck.elements} />
      </div>
      <div className="flex items-center gap-2 mb-2">
        <span className={`text-sm font-bold ${deck.is_valid ? 'text-accent-green' : 'text-accent-red'}`}>
          {deck.total_points}/{deck.max_budget}
        </span>
        <span className="text-xs text-text-muted">pts ({budgetPct}%)</span>
        <div className="flex-1 h-1.5 bg-bg-surface rounded-full overflow-hidden max-w-[100px]">
          <div
            className={`h-full rounded-full ${deck.is_valid ? 'bg-accent-green' : 'bg-accent-red'}`}
            style={{ width: `${Math.min(budgetPct, 100)}%` }}
          />
        </div>
      </div>
      {deck.cards?.length > 0 ? (
        <div className="space-y-0.5">
          {deck.cards.map((c) => (
            <div key={c.name} className="flex items-center justify-between text-xs py-0.5">
              <span className="text-text-secondary">{c.name} <span className="text-text-muted">x{c.quantity}</span></span>
              <span className="text-purple-400 font-medium ml-3 whitespace-nowrap">{c.points_each} x{c.quantity} = {c.points_total}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-text-muted italic">No pointed cards</p>
      )}
    </div>
  )
}

export default function OmensMatches() {
  usePageTitle('Omens Matches')
  const [matches, setMatches] = useState([])
  const [pagination, setPagination] = useState(null)
  const [maxBudget, setMaxBudget] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [page, setPage] = useState(1)
  const [expanded, setExpanded] = useState(null)

  useEffect(() => {
    setLoading(true)
    get(`/api/admin/omens-matches?page=${page}&per_page=50`)
      .then(d => {
        if (d.success) {
          setMatches(d.matches)
          setPagination(d.pagination)
          setMaxBudget(d.max_budget)
        } else {
          setError(d.error || 'Failed to load')
        }
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [page])

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/admin/audit-log" className="text-text-muted hover:text-secondary transition-colors text-sm">&larr; Admin</Link>
        <div>
          <h1 className="text-2xl font-display text-secondary">Omens Matches</h1>
          <p className="text-sm text-text-muted">
            All Omens (points-restricted) matches with deck card point breakdowns.
            {maxBudget != null && <> Budget: <span className="text-purple-400 font-medium">{maxBudget}</span> pts</>}
          </p>
        </div>
      </div>

      {pagination && (
        <div className="bg-bg-raised border border-border rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-purple-400">{pagination.total_matches.toLocaleString()}</div>
          <div className="text-xs text-text-muted mt-1">Total Omens Matches</div>
        </div>
      )}

      {loading ? <Spinner className="py-12" /> : error ? (
        <p className="text-text-muted text-sm py-8 text-center">Error: {error}</p>
      ) : matches.length === 0 ? (
        <p className="text-text-muted text-sm py-8 text-center">No Omens matches recorded yet.</p>
      ) : (
        <div className="bg-bg-raised border border-border rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm" style={{ minWidth: 700 }}>
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="py-2 px-3 text-text-muted font-semibold">ID</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Winner</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Winner Deck</th>
                  <th className="py-2 px-3 text-text-muted font-semibold text-center">Pts Used</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Loser</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Loser Deck</th>
                  <th className="py-2 px-3 text-text-muted font-semibold text-center">Pts Used</th>
                  <th className="py-2 px-3 text-text-muted font-semibold text-center">ELO</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Time</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Date</th>
                </tr>
              </thead>
              <tbody>
                {matches.map((m) => {
                  const isExpanded = expanded === m.match_id
                  return (
                    <Fragment key={m.match_id}>
                      <tr
                        className={`border-b border-border/50 hover:bg-bg-surface/50 cursor-pointer ${isExpanded ? 'bg-bg-surface/50' : ''}`}
                        onClick={() => setExpanded(isExpanded ? null : m.match_id)}
                      >
                        <td className="py-2 px-3 text-text-muted">
                          <span className="flex items-center gap-1">
                            <span className={`text-[10px] transition-transform ${isExpanded ? 'rotate-90' : ''}`}>&#9654;</span>
                            #{m.match_id}
                          </span>
                        </td>
                        <td className="py-2 px-3">
                          <Link to={`/player/${m.winner_id}`} className="text-accent-green hover:underline font-medium" onClick={e => e.stopPropagation()}>
                            {m.winner_name}
                          </Link>
                        </td>
                        <td className="py-2 px-3">
                          <span className="flex items-center gap-1.5">
                            {m.winner_deck?.avatar && <span className="text-text-secondary text-xs">{m.winner_deck.avatar}</span>}
                            <ElementIcons elements={m.winner_deck?.elements} />
                          </span>
                        </td>
                        <td className="py-2 px-3 text-center">
                          <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${m.winner_deck?.is_valid ? 'bg-purple-500/20 text-purple-400' : 'bg-accent-red/20 text-accent-red'}`}>
                            {m.winner_deck?.total_points ?? '?'}/{m.winner_deck?.max_budget ?? '?'}
                          </span>
                        </td>
                        <td className="py-2 px-3">
                          <Link to={`/player/${m.loser_id}`} className="text-accent-red hover:underline font-medium" onClick={e => e.stopPropagation()}>
                            {m.loser_name}
                          </Link>
                        </td>
                        <td className="py-2 px-3">
                          <span className="flex items-center gap-1.5">
                            {m.loser_deck?.avatar && <span className="text-text-secondary text-xs">{m.loser_deck.avatar}</span>}
                            <ElementIcons elements={m.loser_deck?.elements} />
                          </span>
                        </td>
                        <td className="py-2 px-3 text-center">
                          <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${m.loser_deck?.is_valid ? 'bg-purple-500/20 text-purple-400' : 'bg-accent-red/20 text-accent-red'}`}>
                            {m.loser_deck?.total_points ?? '?'}/{m.loser_deck?.max_budget ?? '?'}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-center text-xs">
                          <span className="text-accent-green">+{m.winner_elo_change || 0}</span>
                          {' / '}
                          <span className="text-accent-red">{m.loser_elo_change || 0}</span>
                        </td>
                        <td className="py-2 px-3 text-text-muted text-xs">{m.match_time ? `${m.match_time}m` : '-'}</td>
                        <td className="py-2 px-3 text-text-muted text-xs whitespace-nowrap">{m.date ? new Date(m.date).toLocaleDateString() : '-'}</td>
                      </tr>
                      {isExpanded && (
                        <tr className="bg-bg-surface/30 border-b border-border/50">
                          <td colSpan={10} className="py-4 px-6">
                            <div className="flex flex-wrap gap-8">
                              <DeckBreakdown deck={m.winner_deck} label={`Winner - ${m.winner_name}`} />
                              <DeckBreakdown deck={m.loser_deck} label={`Loser - ${m.loser_name}`} />
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {pagination && pagination.total_pages > 1 && (
        <div className="flex items-center justify-center gap-3">
          <button
            disabled={!pagination.has_previous}
            onClick={() => setPage(1)}
            className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40 disabled:cursor-not-allowed"
          >First</button>
          <button
            disabled={!pagination.has_previous}
            onClick={() => setPage(p => p - 1)}
            className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40 disabled:cursor-not-allowed"
          >&larr; Prev</button>
          <span className="text-sm font-medium">Page {pagination.current_page} of {pagination.total_pages}</span>
          <button
            disabled={!pagination.has_next}
            onClick={() => setPage(p => p + 1)}
            className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40 disabled:cursor-not-allowed"
          >Next &rarr;</button>
          <button
            disabled={!pagination.has_next}
            onClick={() => setPage(pagination.total_pages)}
            className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40 disabled:cursor-not-allowed"
          >Last</button>
        </div>
      )}
    </div>
  )
}
