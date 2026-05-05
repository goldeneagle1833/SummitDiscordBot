import { useState, useEffect } from 'react'
import { useAuth } from '@/context/AuthContext'
import Spinner from '@/components/ui/Spinner'
import {
  fetchSeasons,
  fetchLeaderboard,
  deleteEvent,
} from '@/api/explorer'
import AddSeasonModal from '@/components/explorer/AddSeasonModal'
import AddEventModal from '@/components/explorer/AddEventModal'
import ExplorerAdminPanel from '@/components/explorer/ExplorerAdminPanel'

function QualifiedBadge() {
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-yellow-500/20 text-yellow-400 border border-yellow-500/30">
      Qualified
    </span>
  )
}

function EventRow({ result, onDelete, isAdmin }) {
  return (
    <tr className="border-b border-border/30 text-xs text-text-muted">
      <td className="py-1 pl-12 pr-2">{result.event_name}</td>
      <td className="py-1 px-2">{result.event_date || '—'}</td>
      <td className="py-1 px-2 text-center">{result.final_standing}</td>
      <td className="py-1 px-2 text-center">{result.wins}</td>
      <td className="py-1 px-2 text-center text-blue-300">{result.pathfinder}</td>
      <td className="py-1 px-2 text-center text-red-300">{result.persecutor}</td>
      <td className="py-1 px-2 text-center text-secondary">{result.grand_explorer}</td>
      {isAdmin && (
        <td className="py-1 px-2 text-center">
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(result.event_id) }}
            className="text-red-400 hover:text-red-300 transition-colors"
            title="Remove event"
          >
            ✕
          </button>
        </td>
      )}
    </tr>
  )
}

function PlayerRow({ player, rank, expanded, onToggle, isAdmin, onDeleteEvent }) {
  return (
    <>
      <tr
        className="border-b border-border hover:bg-white/5 cursor-pointer transition-colors"
        onClick={onToggle}
      >
        <td className="py-3 px-4 text-text-muted text-sm">{rank}</td>
        <td className="py-3 px-4">
          <div className="flex items-center gap-2">
            {player.image_url && (
              <img
                src={player.image_url}
                alt=""
                className="w-7 h-7 rounded-full object-cover flex-shrink-0"
                onError={(e) => { e.target.style.display = 'none' }}
              />
            )}
            <div>
              <span className="text-sm font-medium text-text-primary">{player.display_name}</span>
              {player.team_name && (
                <p className="text-xs text-text-muted truncate max-w-[180px]">{player.team_name}</p>
              )}
            </div>
          </div>
        </td>
        <td className="py-3 px-4 text-center text-sm font-semibold text-secondary">{player.grand_explorer}</td>
        <td className="py-3 px-4 text-center text-sm text-blue-300">{player.pathfinder_total}</td>
        <td className="py-3 px-4 text-center text-sm text-red-300">{player.persecutor_total}</td>
        <td className="py-3 px-4 text-center text-xs text-text-muted">{player.events_played}</td>
        <td className="py-3 px-4 text-center">
          {player.qualified && <QualifiedBadge />}
        </td>
        {isAdmin && <td />}
      </tr>
      {expanded && (
        <tr className="bg-bg-elevated">
          <td colSpan={isAdmin ? 8 : 7} className="pb-2">
            <table className="w-full">
              <thead>
                <tr className="text-xs text-text-muted border-b border-border/30">
                  <th className="py-1 pl-12 pr-2 text-left">Event</th>
                  <th className="py-1 px-2 text-left">Date</th>
                  <th className="py-1 px-2 text-center">Place</th>
                  <th className="py-1 px-2 text-center">Wins</th>
                  <th className="py-1 px-2 text-center text-blue-300">Path.</th>
                  <th className="py-1 px-2 text-center text-red-300">Pers.</th>
                  <th className="py-1 px-2 text-center text-secondary">GE</th>
                  {isAdmin && <th className="py-1 px-2" />}
                </tr>
              </thead>
              <tbody>
                {player.event_results.map((r) => (
                  <EventRow key={r.event_id} result={r} isAdmin={isAdmin} onDelete={onDeleteEvent} />
                ))}
              </tbody>
            </table>
          </td>
        </tr>
      )}
    </>
  )
}

export default function ExplorerStandings() {
  const { user } = useAuth()
  const isExplorerAdmin = user?.is_explorer_admin || user?.is_admin
  const isGlobalAdmin = user?.is_admin

  const [seasons, setSeasons] = useState([])
  const [selectedSeasonId, setSelectedSeasonId] = useState(null)
  const [leaderboard, setLeaderboard] = useState(null)
  const [loading, setLoading] = useState(true)
  const [lbLoading, setLbLoading] = useState(false)
  const [error, setError] = useState(null)
  const [expandedPlayers, setExpandedPlayers] = useState({})
  const [showAddSeason, setShowAddSeason] = useState(false)
  const [showAddEvent, setShowAddEvent] = useState(false)
  const [showAdminPanel, setShowAdminPanel] = useState(false)

  const loadSeasons = () => {
    fetchSeasons()
      .then((data) => {
        setSeasons(data)
        if (data.length > 0 && !selectedSeasonId) {
          setSelectedSeasonId(data[0].id)
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadSeasons() }, [])

  useEffect(() => {
    if (!selectedSeasonId) return
    setLbLoading(true)
    setLeaderboard(null)
    fetchLeaderboard(selectedSeasonId)
      .then(setLeaderboard)
      .catch((e) => setError(e.message))
      .finally(() => setLbLoading(false))
  }, [selectedSeasonId])

  const togglePlayer = (uid) => {
    setExpandedPlayers((prev) => ({ ...prev, [uid]: !prev[uid] }))
  }

  const handleDeleteEvent = async (eventId) => {
    if (!confirm('Delete this event and all its results?')) return
    try {
      await deleteEvent(eventId)
      // Reload leaderboard
      setLbLoading(true)
      fetchLeaderboard(selectedSeasonId)
        .then(setLeaderboard)
        .finally(() => setLbLoading(false))
    } catch (e) {
      alert(`Failed to delete event: ${e.message}`)
    }
  }

  if (loading) {
    return (
      <div className="max-w-content mx-auto px-4 py-12 flex justify-center">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="max-w-content mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-display text-text-primary">Community Series</h1>
          <p className="text-sm text-text-muted mt-0.5">Series leaderboard for The Community Series</p>
        </div>

        {isExplorerAdmin && (
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setShowAddSeason(true)}
              className="px-3 py-1.5 text-sm bg-bg-elevated border border-border rounded hover:border-secondary text-text-primary transition-colors"
            >
              + Add Series
            </button>
            {seasons.length > 0 && (
              <button
                onClick={() => setShowAddEvent(true)}
                className="px-3 py-1.5 text-sm bg-secondary text-black font-medium rounded hover:bg-secondary/80 transition-colors"
              >
                + Import Event
              </button>
            )}
            {isGlobalAdmin && (
              <button
                onClick={() => setShowAdminPanel(!showAdminPanel)}
                className="px-3 py-1.5 text-sm bg-bg-elevated border border-border rounded hover:border-accent-red text-text-muted transition-colors"
              >
                {showAdminPanel ? 'Hide Admin Panel' : 'Manage Admins'}
              </button>
            )}
          </div>
        )}
      </div>

      {/* Admin panel */}
      {showAdminPanel && isGlobalAdmin && (
        <div className="mb-6">
          <ExplorerAdminPanel />
        </div>
      )}

      {error && <p className="text-sm text-red-400 mb-4">{error}</p>}

      {seasons.length === 0 ? (
        <div className="bg-bg-surface border border-border rounded-lg p-8 text-center">
          <p className="text-text-muted">No series yet.{isExplorerAdmin ? ' Create one to get started.' : ''}</p>
        </div>
      ) : (
        <>
          {/* Series selector */}
          <div className="mb-6">
            <div className="flex items-center gap-3">
              <label className="text-sm text-text-muted">Series:</label>
              <select
                value={selectedSeasonId ?? ''}
                onChange={(e) => setSelectedSeasonId(Number(e.target.value))}
                className="bg-bg-elevated border border-border rounded px-3 py-1.5 text-sm text-text-primary"
              >
                {seasons.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} ({s.event_count} event{s.event_count !== 1 ? 's' : ''})
                  </option>
                ))}
              </select>
            </div>
            {selectedSeasonId && seasons.find((s) => s.id === selectedSeasonId)?.description && (
              <p className="text-sm text-text-muted mt-2">
                {seasons.find((s) => s.id === selectedSeasonId).description}
              </p>
            )}
          </div>

          {/* Points legend */}
          {leaderboard?.points_config && (
            <div className="mb-4 flex flex-wrap gap-4 text-xs text-text-muted">
              <span><span className="text-blue-300 font-medium">Pathfinder</span> = participation + win bonus</span>
              <span><span className="text-red-300 font-medium">Persecutor</span> = top-cut placement points</span>
              <span><span className="text-secondary font-medium">Grand Explorer</span> = Pathfinder + Persecutor</span>
              <span className="text-yellow-400">Qualified = Persecutor ≥ {leaderboard.points_config.trials_threshold}</span>
            </div>
          )}

          {/* Leaderboard table */}
          {lbLoading ? (
            <div className="flex justify-center py-12"><Spinner /></div>
          ) : !leaderboard || leaderboard.players.length === 0 ? (
            <div className="bg-bg-surface border border-border rounded-lg p-8 text-center">
              <p className="text-text-muted">No results yet for this series.{isExplorerAdmin ? ' Import an event to populate the leaderboard.' : ''}</p>
            </div>
          ) : (
            <div className="bg-bg-surface border border-border rounded-lg overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-border bg-bg-elevated text-left">
                      <th className="py-3 px-4 text-xs text-text-muted font-semibold uppercase tracking-wide w-12">#</th>
                      <th className="py-3 px-4 text-xs text-text-muted font-semibold uppercase tracking-wide">Player</th>
                      <th className="py-3 px-4 text-xs text-secondary font-semibold uppercase tracking-wide text-center">Grand Explorer</th>
                      <th className="py-3 px-4 text-xs text-blue-300 font-semibold uppercase tracking-wide text-center">Pathfinder</th>
                      <th className="py-3 px-4 text-xs text-red-300 font-semibold uppercase tracking-wide text-center">Persecutor</th>
                      <th className="py-3 px-4 text-xs text-text-muted font-semibold uppercase tracking-wide text-center">Events</th>
                      <th className="py-3 px-4 text-xs text-text-muted font-semibold uppercase tracking-wide text-center">Status</th>
                      {isExplorerAdmin && <th className="py-3 px-4 w-8" />}
                    </tr>
                  </thead>
                  <tbody>
                    {leaderboard.players.map((player) => (
                      <PlayerRow
                        key={player.cardeio_user_id}
                        player={player}
                        rank={player.rank}
                        expanded={!!expandedPlayers[player.cardeio_user_id]}
                        onToggle={() => togglePlayer(player.cardeio_user_id)}
                        isAdmin={isExplorerAdmin}
                        onDeleteEvent={handleDeleteEvent}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* Modals */}
      {showAddSeason && (
        <AddSeasonModal
          onClose={() => setShowAddSeason(false)}
          onCreated={(season) => {
            setShowAddSeason(false)
            loadSeasons()
            setSelectedSeasonId(season.id)
          }}
        />
      )}
      {showAddEvent && seasons.length > 0 && (
        <AddEventModal
          seasons={seasons}
          onClose={() => setShowAddEvent(false)}
          onSaved={() => {
            setShowAddEvent(false)
            // Reload leaderboard
            setLbLoading(true)
            fetchLeaderboard(selectedSeasonId)
              .then(setLeaderboard)
              .finally(() => setLbLoading(false))
          }}
        />
      )}
    </div>
  )
}
