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
import ExternalMatches from '@/components/player/ExternalMatches'
import DisplayNameBanner from '@/components/player/DisplayNameBanner'
import ReportGameModal from '@/components/player/ReportGameModal'
import EditDeckModal from '@/components/player/EditDeckModal'
import AdminControls from '@/components/player/AdminControls'
import EloHistory from '@/components/player/EloHistory'
import PlayerSeasons from '@/components/player/PlayerSeasons'
import PrivacySettingsModal from '@/components/player/PrivacySettingsModal'
import BlockListModal from '@/components/player/BlockListModal'
import { useAuth } from '@/context/AuthContext'

const PER_PAGE_OPTIONS = [15, 25, 50]

export default function Player() {
  usePageTitle('Player')
  const { playerId } = useParams()
  const { user: authUser } = useAuth()
  const isAdmin = authUser && authUser.is_admin
  const isOwner = authUser && String(authUser.user_id) === String(playerId)
  const canSeeLifetime = isAdmin || isOwner
  const [data, setData] = useState(null)
  const [events, setEvents] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Filter state
  const [eventFilter, setEventFilter] = useState(canSeeLifetime ? 'lifetime' : 'current')
  const [eloSource, setEloSource] = useState(() => {
    const saved = localStorage.getItem('elo_source_preference')
    return saved === 'web' || saved === 'bot' ? saved : 'bot'
  })
  const [page, setPage] = useState(1)
  const [casualPage, setCasualPage] = useState(1)
  const [externalPage, setExternalPage] = useState(1)
  const [perPage, setPerPage] = useState(15)
  const [statsType, setStatsType] = useState('ranked')

  // Modal state
  const [showReportModal, setShowReportModal] = useState(false)
  const [showPrivacyModal, setShowPrivacyModal] = useState(false)
  const [showBlockListModal, setShowBlockListModal] = useState(false)
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
    (ev, pg, src, cpg, pp, epg) => {
      setLoading(true)
      getPlayer(playerId, { event: ev, source: src, page: pg, perPage: pp, casualPage: cpg, externalPage: epg })
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
    fetchData(eventFilter, page, eloSource, casualPage, perPage, externalPage)
    get('/api/events').then(setEvents).catch(() => {})
  }, [playerId]) // eslint-disable-line react-hooks/exhaustive-deps

  const refetch = (ev, pg, src, cpg, pp, epg) => {
    const e = ev ?? eventFilter
    const p = pg ?? page
    const s = src ?? eloSource
    const c = cpg ?? casualPage
    const r = pp ?? perPage
    const x = epg ?? externalPage
    setEventFilter(e)
    setPage(p)
    setEloSource(s)
    setCasualPage(c)
    setPerPage(r)
    setExternalPage(x)
    fetchData(e, p, s, c, r, x)
  }

  const refreshCurrentPage = () => fetchData(eventFilter, page, eloSource, casualPage, perPage, externalPage)

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
    if (canSeeLifetime && data.elo != null) {
      eloText = `Lifetime ELO: ${data.elo}`
      if (data.event_elo && data.event_elo !== 1500) eloText += ` | Event ELO: ${data.event_elo}`
      rankText = data.rank ? `Rank #${data.rank}` : ''
    } else {
      eloText = data.event_elo && data.event_elo !== 1500 ? `Event ELO: ${data.event_elo}` : ''
      rankText = ''
    }
  } else if (eventFilter === 'current') {
    eloText = data.displayed_elo !== 1500 ? `Current Event ELO: ${data.displayed_elo}` : 'No current event data'
    rankText = data.displayed_rank > 0 ? `Event Rank #${data.displayed_rank}` : ''
  } else {
    eloText = data.displayed_elo !== 1500 ? `Event ELO: ${data.displayed_elo}` : 'No data for this event'
    rankText = data.displayed_rank > 0 ? `#${data.displayed_rank}` : ''
  }

  const stats = statsType === 'casual' ? data.casual_stats : data
  const pastEvents = events?.events?.filter((e) => !e.is_active) || []
  const vis = data.profile_visibility || {}
  const sectionVisible = (key) => data.is_owner || vis[key]
  const isProfilePrivate = !data.is_owner && Object.values(vis).every((v) => !v)

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

      {data.is_owner && <PlayerSeasons playerId={playerId} isOwner={data.is_owner} />}

      <PlayerHeader
        data={data}
        eloText={eloText}
        rankText={rankText}
        eloSource={eloSource}
        onSourceChange={handleSourceChange}
        eventFilter={eventFilter}
        pastEvents={pastEvents}
        onEventChange={(val) => refetch(val, 1, undefined, 1)}
        canSeeLifetime={canSeeLifetime}
      />

      {/* Report Game & Privacy Settings buttons (owner only) */}
      {data.is_owner && (
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={() => setShowReportModal(true)}
            className="px-4 py-2 text-sm bg-secondary text-black rounded hover:opacity-90 transition-opacity"
          >
            Report a Game
          </button>
          <button
            onClick={() => setShowPrivacyModal(true)}
            className="px-4 py-2 text-sm rounded border border-border text-text-muted hover:text-text-primary hover:border-secondary/50 transition-colors"
          >
            Privacy Settings
          </button>
          <button
            onClick={() => setShowBlockListModal(true)}
            className="px-4 py-2 text-sm rounded border border-border text-text-muted hover:text-text-primary hover:border-secondary/50 transition-colors"
          >
            Block List
          </button>
        </div>
      )}

      {isProfilePrivate && (
        <div className="text-center py-4 text-text-muted border border-border rounded-lg bg-bg-surface">
          <p className="text-sm">Some sections of this profile are private.</p>
        </div>
      )}

      <OverallStats
        data={data}
        stats={stats}
        statsType={statsType}
        onStatsTypeChange={setStatsType}
      />

      {sectionVisible('elo_history') && (
        <EloHistory
          eloHistory={data.elo_history}
          currentElo={data.elo}
          open={openSections.eloHistory}
          onToggle={() => toggle('eloHistory')}
        />
      )}

      {sectionVisible('elo_brackets') && (
        <EloBrackets
          brackets={data.elo_vs_brackets}
          open={openSections.eloBrackets}
          onToggle={() => toggle('eloBrackets')}
        />
      )}

      {sectionVisible('avatar_performance') && (
        <AvatarPerformance
          avatars={data.avatar_performance}
          playerId={playerId}
          open={openSections.avatarPerf}
          onToggle={() => toggle('avatarPerf')}
        />
      )}

      {sectionVisible('avatar_matchups') && (
        <AvatarMatchups
          matchups={data.avatar_matchups}
          open={openSections.avatarMatchups}
          onToggle={() => toggle('avatarMatchups')}
        />
      )}

      {sectionVisible('recent_decks') && (
        <RecentDecks
          decks={data.recent_decks}
          playerId={playerId}
          open={openSections.recentDecks}
          onToggle={() => toggle('recentDecks')}
        />
      )}

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
        perPage={perPage}
        perPageOptions={PER_PAGE_OPTIONS}
        onPageChange={(p) => refetch(undefined, p)}
        onPerPageChange={(pp) => refetch(undefined, 1, undefined, undefined, pp)}
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

      {data.external_matches?.length > 0 && (
        <ExternalMatches
          matches={data.external_matches}
          stats={data.external_stats}
          pagination={data.external_pagination}
          playerId={playerId}
          onPageChange={(p) => refetch(undefined, undefined, undefined, undefined, undefined, p)}
        />
      )}

      {sectionVisible('recorded_games') && <RecordedGames games={data.recorded_games} />}

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

      {showPrivacyModal && (
        <PrivacySettingsModal
          playerId={playerId}
          onClose={() => setShowPrivacyModal(false)}
          onSaved={refreshCurrentPage}
        />
      )}

      {showBlockListModal && (
        <BlockListModal
          playerId={playerId}
          onClose={() => setShowBlockListModal(false)}
        />
      )}

    </div>
  )
}
