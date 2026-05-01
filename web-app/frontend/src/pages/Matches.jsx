import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getMatches, getAvailableDates } from '@/api/matches'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

export default function Matches() {
  usePageTitle('Match History')
  const [matches, setMatches] = useState([])
  const [dates, setDates] = useState([])
  const [selectedDate, setSelectedDate] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    Promise.all([getMatches(), getAvailableDates()])
      .then(([matchData, dateData]) => {
        setMatches(matchData)
        setDates(dateData)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  const handleDateChange = (date) => {
    setSelectedDate(date)
    setLoading(true)
    getMatches(date || undefined)
      .then(setMatches)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }

  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-display text-secondary">Match History</h1>
        <select
          value={selectedDate}
          onChange={(e) => handleDateChange(e.target.value)}
          className="bg-bg-elevated border border-border rounded-soft px-3 py-1.5 text-sm text-text"
        >
          <option value="">All dates</option>
          {dates.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
      </div>

      {loading ? (
        <Spinner className="py-20" />
      ) : matches.length === 0 ? (
        <p className="text-center text-text-muted py-8">No matches found.</p>
      ) : (
        <div className="space-y-2">
          {matches.map((match) => (
            <div key={match.match_id} className="bg-bg-surface border border-border rounded-soft p-3 flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm">
                <Link to={`/player/${match.winner_id}`} className="text-accent-green hover:text-accent-green/80 font-medium">
                  {match.winner_name}
                </Link>
                <span className="text-text-muted">beat</span>
                <Link to={`/player/${match.loser_id}`} className="text-accent-red hover:opacity-80 font-medium">
                  {match.loser_name}
                </Link>
              </div>
              <div className="flex items-center gap-3 text-xs text-text-muted">
                {match.winner_elo_change != null && (
                  <span className="text-accent-green">+{match.winner_elo_change}</span>
                )}
                {match.match_time && (
                  <span>{new Date(match.match_time).toLocaleDateString()}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
