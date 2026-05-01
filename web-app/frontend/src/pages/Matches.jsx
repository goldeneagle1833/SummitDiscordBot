import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { getMatches, getAvailableDates } from '@/api/matches'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

export default function Matches() {
  usePageTitle('Match History')
  const [matches, setMatches] = useState([])
  const [availableDates, setAvailableDates] = useState([])
  const [selectedDate, setSelectedDate] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const dateRef = useRef(null)

  useEffect(() => {
    Promise.all([getMatches(), getAvailableDates()])
      .then(([matchData, dateData]) => {
        setMatches(matchData)
        setAvailableDates(dateData)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  const handleDateChange = (e) => {
    const date = e.target.value
    if (date && !availableDates.includes(date)) {
      alert('No match data available for this date')
      e.target.value = ''
      return
    }
    setSelectedDate(date)
    setLoading(true)
    getMatches(date || undefined)
      .then(setMatches)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }

  const clearDate = () => {
    setSelectedDate('')
    if (dateRef.current) dateRef.current.value = ''
    setLoading(true)
    getMatches()
      .then(setMatches)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }

  const minDate = availableDates.length > 0 ? availableDates[availableDates.length - 1] : undefined
  const maxDate = availableDates.length > 0 ? availableDates[0] : undefined

  const sectionTitle = selectedDate
    ? `Matches on ${new Date(selectedDate + 'T00:00:00').toLocaleDateString()}`
    : 'Last 24 Hours'

  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      {/* Hero */}
      <section className="text-center mb-8">
        <h1 className="text-2xl font-display text-secondary mb-2">Match History</h1>
        <p className="text-text-muted text-sm">Matches from the last 24 hours</p>
      </section>

      {/* Section title + date controls */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
        <h3 className="text-lg font-semibold text-text-primary">{sectionTitle}</h3>
        <div className="flex items-center gap-2">
          <label htmlFor="date-picker" className="text-sm text-text-muted whitespace-nowrap">Select Date:</label>
          <input
            ref={dateRef}
            id="date-picker"
            type="date"
            value={selectedDate}
            min={minDate}
            max={maxDate}
            onChange={handleDateChange}
            className="bg-bg-raised border border-border rounded px-3 py-1.5 text-sm text-text-primary"
          />
          <button
            onClick={clearDate}
            className="bg-bg-raised border border-border rounded px-3 py-1.5 text-sm text-text-muted hover:text-text-primary transition-colors whitespace-nowrap"
          >
            Show Last 24 Hours
          </button>
        </div>
      </div>

      {/* Match Table */}
      {loading ? (
        <Spinner className="py-20" />
      ) : matches.length === 0 ? (
        <p className="text-center text-text-muted py-8">No matches recorded</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left">
                <th className="py-2 px-3 font-semibold text-text-muted">Match ID</th>
                <th className="py-2 px-3 font-semibold text-text-muted">Winner</th>
                <th className="py-2 px-3 font-semibold text-text-muted">Winner ELO</th>
                <th className="py-2 px-3 font-semibold text-text-muted">Loser</th>
                <th className="py-2 px-3 font-semibold text-text-muted">Loser ELO</th>
                <th className="py-2 px-3 font-semibold text-text-muted">Match Time</th>
                <th className="py-2 px-3 font-semibold text-text-muted">Date</th>
              </tr>
            </thead>
            <tbody>
              {matches.map((match) => {
                const winSign = match.winner_elo_change >= 0 ? '+' : ''
                const loseSign = match.loser_elo_change >= 0 ? '+' : ''
                const matchTime = match.match_time ? `${match.match_time} min` : '-'
                const date = match.timestamp ? new Date(match.timestamp).toLocaleDateString() : '-'

                return (
                  <tr key={match.match_id} className="border-b border-border/50 hover:bg-bg-surface/50">
                    <td className="py-2 px-3 text-text-muted">#{match.match_id}</td>
                    <td className="py-2 px-3">
                      <Link to={`/player/${match.winner_id}`} className="text-secondary hover:underline">
                        {match.winner}
                      </Link>
                    </td>
                    <td className="py-2 px-3 text-accent-green">{winSign}{match.winner_elo_change}</td>
                    <td className="py-2 px-3">
                      <Link to={`/player/${match.loser_id}`} className="text-secondary hover:underline">
                        {match.loser}
                      </Link>
                    </td>
                    <td className="py-2 px-3 text-accent-red">{loseSign}{match.loser_elo_change}</td>
                    <td className="py-2 px-3 text-text-muted">{matchTime}</td>
                    <td className="py-2 px-3 text-text-muted">{date}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
