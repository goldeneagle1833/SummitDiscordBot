import { useState, useEffect, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getPlayer } from '@/api/players'
import { get } from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'
import PlayerHeader from '@/components/player/PlayerHeader'
import OverallStats from '@/components/player/OverallStats'
import EloBrackets from '@/components/player/EloBrackets'
import AvatarPerformance from '@/components/player/AvatarPerformance'
import AvatarMatchups from '@/components/player/AvatarMatchups'
import RecentDecks from '@/components/player/RecentDecks'
import LimitedArena from '@/components/player/LimitedArena'
import MatchHistoryTable from '@/components/player/MatchHistoryTable'
import RecordedGames from '@/components/player/RecordedGames'
import DisplayNameBanner from '@/components/player/DisplayNameBanner'
import ReportGameModal from '@/components/player/ReportGameModal'
import EditDeckModal from '@/components/player/EditDeckModal'
import AdminControls from '@/components/player/AdminControls'
import EloHistory from '@/components/player/EloHistory'
import PlayerSeasons from '@/components/player/PlayerSeasons'

const PER_PAGE = 50

export default function Player() {
  usePageTitle('Player')
  const { playerId } = useParams()
  const [data, setData] = useState(null)
  const [events, setEvents] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Filter state
  const [eventFilter, setEventFilter] = useState('lifetime')
  const [eloSource, setEloSource] = useState(() => {
    const saved = localStorage.getItem('elo_source_preference')
    return saved === 'web' || saved === 'bot' ? saved : 'bot'
  })
  const [page, setPage] = useState(1)
  const [casualPage, setCasualPage] = useState(1)
  const [statsType, setStatsType] = useState('ranked')

  // Modal state
  const [showReportModal, setShowReportModal] = useState(false)
  const [editDeck, setEditDeck] = useState(null)

  // Collapsible sections
  const [openSections, setOpenSections] = useState({
    eloHistory: false,
    eloBrackets: false,
    avatarPerf: false,
    avatarMatchups: false,
    recentDecks: false,
    limitedArena: false,
  })
  const toggle = (key) => setOpenSections((s) => ({ ...s, [key]: !s[key] }))

  const fetchData = useCallback(
    (ev, pg, src, cpg) => {
      setLoading(true)
      getPlayer(playerId, { event: ev, source: src, page: pg, perPage: PER_PAGE, casualPage: cpg })
        .then((d) => {
          setData(d)
          setError(null)
        })
        .catch((err) => setError(err.message))
        .finally(() => setLoading(false))
    },
    [playerId],
  )

  useEffect(() => {
    fetchData(eventFilter, page, eloSource, casualPage)
    get('/api/events').then(setEvents).catch(() => {})
  }, [playerId]) // eslint-disable-line react-hooks/exhaustive-deps

  const refetch = (ev, pg, src, cpg) => {
    const e = ev ?? eventFilter
    const p = pg ?? page
    const s = src ?? eloSource
    const c = cpg ?? casualPage
    setEventFilter(e)
    setPage(p)
    setEloSource(s)
    setCasualPage(c)
    fetchData(e, p, s, c)
  }

  const refreshCurrentPage = () => fetchData(eventFilter, page, eloSource, casualPage)

  const handleSourceChange = (src) => {
    localStorage.setItem('elo_source_preference', src)
    refetch(undefined, 1, src, 1)
  }

  const handleNameChange = (newName) => {
    setData((d) => d ? { ...d, name: newName, has_custom_display_name: true } : d)
  }

  if (loading && !data) return <Spinner className="py-20" />
  if (error && !data) return <p className="text-center text-accent-red py-8">{error}</p>
  if (!data) return null

  // ELO display logic
  let eloText = ''
  let rankText = ''
  if (eventFilter === 'lifetime' || !eventFilter) {
    eloText = `Lifetime ELO: ${data.elo}`
    if (data.event_elo && data.event_elo !== 1500) eloText += ` | Event ELO: ${data.event_elo}`
    rankText = data.rank ? `Rank #${data.rank}` : ''
  } else if (eventFilter === 'current') {
    eloText = data.displayed_elo !== 1500 ? `Current Event ELO: ${data.displayed_elo}` : 'No current event data'
    rankText = data.displayed_rank > 0 ? `Event Rank #${data.displayed_rank}` : ''
  } else {
    eloText = data.displayed_elo !== 1500 ? `Event ELO: ${data.displayed_elo}` : 'No data for this event'
    rankText = data.displayed_rank > 0 ? `#${data.displayed_rank}` : ''
  }

  const stats = statsType === 'casual' ? data.casual_stats : data
  const pastEvents = events?.events?.filter((e) => !e.is_active) || []

  return (
    <div className="space-y-6">
      <Link to="/" className="text-sm text-secondary hover:underline">&larr; Back to Leaderboard</Link>

      {/* Admin Controls (admin only) */}
      {data.is_admin && (
        <AdminControls
          playerId={playerId}
          playerName={data.name}
          onAction={refreshCurrentPage}
        />
      )}

      {/* Display Name Banner (owner only, no custom name yet) */}
      {data.is_owner && (
        <DisplayNameBanner
          playerId={playerId}
          defaultName={data.name}
          hasCustomName={data.has_custom_display_name}
          onNameChange={handleNameChange}
        />
      )}

      <PlayerSeasons playerId={playerId} isOwner={data.is_owner} />

      <PlayerHeader
        data={data}
        eloText={eloText}
        rankText={rankText}
        eloSource={eloSource}
        onSourceChange={handleSourceChange}
        eventFilter={eventFilter}
        pastEvents={pastEvents}
        onEventChange={(val) => refetch(val, 1, undefined, 1)}
      />

      {/* Report Game button (owner only) */}
      {data.is_owner && (
        <button
          onClick={() => setShowReportModal(true)}
          className="px-4 py-2 text-sm bg-secondary text-black rounded hover:opacity-90 transition-opacity"
        >
          Report a Game
        </button>
      )}

      <OverallStats
        data={data}
        stats={stats}
        statsType={statsType}
        onStatsTypeChange={setStatsType}
      />

      <EloHistory
        matches={data.matches}
        currentElo={data.elo}
        totalMatches={data.pagination?.total_matches}
        open={openSections.eloHistory}
        onToggle={() => toggle('eloHistory')}
      />

      <EloBrackets
        brackets={data.elo_vs_brackets}
        open={openSections.eloBrackets}
        onToggle={() => toggle('eloBrackets')}
      />

      <AvatarPerformance
        avatars={data.avatar_performance}
        open={openSections.avatarPerf}
        onToggle={() => toggle('avatarPerf')}
      />

      <AvatarMatchups
        matchups={data.avatar_matchups}
        open={openSections.avatarMatchups}
        onToggle={() => toggle('avatarMatchups')}
      />

      <RecentDecks
        decks={data.recent_decks}
        playerId={playerId}
        open={openSections.recentDecks}
        onToggle={() => toggle('recentDecks')}
      />

      <LimitedArena
        limited={data.limited}
        playerId={playerId}
        open={openSections.limitedArena}
        onToggle={() => toggle('limitedArena')}
      />

      <MatchHistoryTable
        title="Ranked Match History"
        matches={data.matches}
        pagination={data.pagination}
        playerId={playerId}
        isOwner={data.is_owner}
        onPageChange={(p) => refetch(undefined, p)}
        onEditDeck={data.is_owner ? (matchId, url) => setEditDeck({ matchId, url }) : undefined}
      />

      {data.casual_matches?.length > 0 && (
        <MatchHistoryTable
          title="Casual Match History"
          subtitle="Casual games do not affect ELO ratings."
          matches={data.casual_matches}
          pagination={data.casual_pagination}
          playerId={playerId}
          isOwner={data.is_owner}
          onPageChange={(p) => refetch(undefined, undefined, undefined, p)}
          onEditDeck={data.is_owner ? (matchId, url) => setEditDeck({ matchId, url }) : undefined}
        />
      )}

      <RecordedGames games={data.recorded_games} />

      {/* Modals */}
      {showReportModal && (
        <ReportGameModal
          playerId={playerId}
          onClose={() => setShowReportModal(false)}
          onReported={refreshCurrentPage}
        />
      )}

      {editDeck && (
        <EditDeckModal
          matchId={editDeck.matchId}
          currentUrl={editDeck.url}
          eloSource={eloSource}
          onClose={() => setEditDeck(null)}
          onSaved={refreshCurrentPage}
        />
      )}
    </div>
  )
}
