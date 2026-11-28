import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, Link, useNavigate, useSearchParams } from 'react-router-dom'
import { getPlayer, resetOwnProfile, undoProfileReset, setProfilePicture } from '@/api/players'
import { get } from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'
import PlayerHeader from '@/components/player/PlayerHeader'
import OverallStats from '@/components/player/OverallStats'
import EloBrackets from '@/components/player/EloBrackets'
import AvatarPerformance from '@/components/player/AvatarPerformance'
import AvatarMatchups from '@/components/player/AvatarMatchups'
import RecentDecks from '@/components/player/RecentDecks'
import FeaturedDeck from '@/components/player/FeaturedDeck'
import FeaturedDeckModal from '@/components/player/FeaturedDeckModal'
import ShowcaseModal from '@/components/player/ShowcaseModal'
import ProfilePictureModal from '@/components/player/ProfilePictureModal'
import { FavoriteCardBox, ProfileBio, RivalBox, useShowcase } from '@/components/player/ProfileShowcase'
import LimitedArena from '@/components/player/LimitedArena'
import { PreconMatchHistory, PreconStandings, usePreconPlayer, withPreconFilters } from '@/components/player/PlayerPrecon'
import MatchHistoryTable from '@/components/player/MatchHistoryTable'
import MatchFilters from '@/components/player/MatchFilters'
import RecordedGames from '@/components/player/RecordedGames'
import ExternalMatches from '@/components/player/ExternalMatches'
import PendingMatches from '@/components/player/PendingMatches'
import DisplayNameBanner from '@/components/player/DisplayNameBanner'
import ReportGameModal from '@/components/player/ReportGameModal'
import EditDeckModal from '@/components/player/EditDeckModal'
import AdminControls from '@/components/player/AdminControls'
import EloHistory from '@/components/player/EloHistory'
import AvatarEloHistory from '@/components/player/AvatarEloHistory'
import PostseasonSection from '@/components/player/PostseasonSection'
import { AvatarHonoursSection, useAvatarHonours } from '@/components/player/AvatarHonours'
import { PaperFinishesSection, usePaperFinishes } from '@/components/player/PaperFinishes'
import { EventAvatarBadgesSection, useEventAvatarBadges } from '@/components/player/EventAvatarBadges'
import ManageBadgesModal from '@/components/player/ManageBadgesModal'
import { profileBadges } from '@/components/player/profileBadges'
import PrivacySettingsModal from '@/components/player/PrivacySettingsModal'
import BlockListModal from '@/components/player/BlockListModal'
import QueueSettingsModal from '@/components/player/QueueSettingsModal'
import DataExportModal from '@/components/player/DataExportModal'
import CardStats from '@/components/player/CardStats'
import { useBracketMarks } from '@/components/player/BracketMarks'
import { useAuth } from '@/context/AuthContext'
import { provisionalOf } from '@/utils/provisional'

const PER_PAGE_OPTIONS = [15, 25, 50]

export default function Player() {
  usePageTitle('Player')
  const { playerId } = useParams()
  const { user: authUser, refreshUser } = useAuth()
  const isAdmin = authUser && authUser.is_admin
  const isOwner = authUser && String(authUser.user_id) === String(playerId)
  const canSeeLifetime = isAdmin || isOwner
  // The logged-in player on their own page (Google ids may or may not carry the prefix)
  const bareId = (id) => String(id ?? '').replace(/^google_/, '')
  const isSelf = Boolean(authUser) && bareId(authUser.user_id) === bareId(playerId)
  const [data, setData] = useState(null)
  const [events, setEvents] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Filter state
  const [eventFilter, setEventFilter] = useState(canSeeLifetime ? 'lifetime' : 'current')
  // Paper is hidden (nobody plays on the paper ladder), so the profile is always online
  const [eloSource, setEloSource] = useState('bot')
  const [page, setPage] = useState(1)
  const [casualPage, setCasualPage] = useState(1)
  const [externalPage, setExternalPage] = useState(1)
  const [perPage, setPerPage] = useState(15)
  const [statsType, setStatsType] = useState('ranked')
  // Matches tab filters; a ref so every fetch (paging, period) keeps them
  const [matchFilters, setMatchFilters] = useState({})
  const matchFiltersRef = useRef({})

  // Modal state
  const [showReportModal, setShowReportModal] = useState(false)
  const [showPrivacyModal, setShowPrivacyModal] = useState(false)
  const [showBlockListModal, setShowBlockListModal] = useState(false)
  const [showQueueSettingsModal, setShowQueueSettingsModal] = useState(false)
  const [showDataExportModal, setShowDataExportModal] = useState(false)
  const [showBadgesModal, setShowBadgesModal] = useState(false)
  const [showPictureModal, setShowPictureModal] = useState(false)
  // The hero card badges the player just picked; undefined = use the player data
  const [shownBadges, setShownBadgesState] = useState(undefined)
  const [showResetModal, setShowResetModal] = useState(false)
  const [resetLoading, setResetLoading] = useState(false)
  const [editDeck, setEditDeck] = useState(null)
  const [showFeaturedModal, setShowFeaturedModal] = useState(false)
  const [featuredDeck, setFeaturedDeckState] = useState(null)
  const [featuredKey, setFeaturedKey] = useState(0)
  // Profile showcase editor: null when closed, else the box it opens on
  const [showcaseFocus, setShowcaseFocus] = useState(null)
  const [showcaseKey, setShowcaseKey] = useState(0)
  const showcase = useShowcase(playerId, showcaseKey)

  // Profile tab, kept in the URL so a tab can be linked to
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = searchParams.get('tab') || 'matches'
  const setTab = (id) => {
    const next = new URLSearchParams(searchParams)
    if (id === 'matches') next.delete('tab')
    else next.set('tab', id)
    setSearchParams(next, { replace: true })
  }
  const navigate = useNavigate()
  // ?open=block-list (from /me/block-list) opens that panel on the owner's page
  const openPanel = searchParams.get('open')
  useEffect(() => {
    if (!openPanel || !data) return
    if (openPanel === 'block-list' && data.is_owner) setShowBlockListModal(true)
    const next = new URLSearchParams(searchParams)
    next.delete('open')
    setSearchParams(next, { replace: true })
  }, [openPanel, data]) // eslint-disable-line react-hooks/exhaustive-deps
  const avatarHonours = useAvatarHonours(playerId)
  const paperFinishes = usePaperFinishes(playerId)
  const eventAvatarBadges = useEventAvatarBadges(playerId)
  const precon = usePreconPlayer(playerId)
  const bracketMarks = useBracketMarks(playerId)
  const hasPostseason =
    Boolean(bracketMarks?.entries?.length) || avatarHonours.length > 0 || paperFinishes.length > 0
    || eventAvatarBadges.length > 0

  const fetchData = useCallback(
    (ev, pg, src, cpg, pp, epg) => {
      setLoading(true)
      getPlayer(playerId, {
        event: ev, source: src, page: pg, perPage: pp, casualPage: cpg, externalPage: epg,
        filters: matchFiltersRef.current,
      })
        .then((d) => {
          setData(d)
          setShownBadgesState(undefined)
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

  const changeMatchFilters = (next) => {
    matchFiltersRef.current = next
    setMatchFilters(next)
    refetch(undefined, 1, undefined, 1)
  }

  const refreshCurrentPage = () => fetchData(eventFilter, page, eloSource, casualPage, perPage, externalPage)


  const handleNameChange = (newName) => {
    setData((d) => d ? { ...d, name: newName, has_custom_display_name: true } : d)
    refreshUser?.() // the menu shows the signed-in name too
  }


  if (loading && !data) return <Spinner className="py-20" />
  if (error && !data) return <p className="text-center text-accent-red py-8">{error}</p>
  if (!data) return null

  // Headline numbers for the header card
  const avatarMode = data.avatar_event_elo?.elo_mode === 'avatar'
  const avatarEntries = data.avatar_event_elo?.entries || []
  const isLifetime = eventFilter === 'lifetime' || !eventFilter
  // provisional: { games } when the shown rating is a provisional Glicko-2 one
  // (fewer than 8 games): the header shows "Provisional (n/8)" and no rank.
  const headline = { elo: null, eloLabel: '', rank: null, rankLabel: 'Rank', note: '', provisional: null, legacyElo: null }
  const eventProv = provisionalOf(data, 'event')
  if (isLifetime) {
    const lifetimeProv = provisionalOf(data, 'lifetime')
    if (canSeeLifetime && (data.elo != null || lifetimeProv)) {
      headline.elo = data.elo
      headline.eloLabel = 'Lifetime Rating'
      headline.provisional = lifetimeProv
      headline.rank = lifetimeProv ? null : data.rank || null
      headline.legacyElo = data.legacy_elo ?? null
    } else if (eventProv || (data.event_elo && data.event_elo !== 1500)) {
      headline.elo = data.event_elo
      headline.eloLabel = 'Event Rating'
      headline.provisional = eventProv
    }
  } else if (avatarMode) {
    if (!avatarEntries.length) headline.note = 'No avatar games this event yet'
  } else if (provisionalOf(data, 'displayed')) {
    // displayed_* is the selected event's rating (event_* is the running one)
    headline.provisional = provisionalOf(data, 'displayed')
    headline.eloLabel = eventFilter === 'current' ? 'Current event rating' : 'Event Rating'
  } else if (data.displayed_elo != null && data.displayed_elo !== 1500) {
    headline.elo = data.displayed_elo
    headline.eloLabel = eventFilter === 'current' ? 'Current event rating' : 'Event Rating'
    headline.rank = data.displayed_rank > 0 ? data.displayed_rank : null
    headline.rankLabel = eventFilter === 'current' ? 'Event rank' : 'Rank'
  } else {
    headline.note = eventFilter === 'current' ? 'No current event data' : 'No data for this event'
  }

  const stats = statsType === 'casual' ? data.casual_stats : data
  const pastEvents = events?.events?.filter((e) => !e.is_active) || []
  const vis = data.profile_visibility || {}
  const sectionVisible = (key) => data.is_owner || vis[key]

  // A tab shows only when the viewer can see something on it
  const tabs = [
    { id: 'overview', label: 'Overview' },
    (sectionVisible('avatar_performance') && data.avatar_performance?.length > 0) && { id: 'avatars', label: 'Avatars' },
    ((sectionVisible('avatar_matchups') && data.avatar_matchups?.length > 0)
      || (sectionVisible('elo_brackets') && data.elo_vs_brackets?.length > 0)) && { id: 'matchups', label: 'Matchups' },
    sectionVisible('card_stats') && { id: 'cards', label: 'Card Stats' },
    data.limited?.has_data && { id: 'limited', label: 'Limited' },
    precon?.seasons?.length > 0 && { id: 'precon', label: 'LM / FM' },
    { id: 'matches', label: 'Matches' },
    hasPostseason && { id: 'postseason', label: 'Postseason' },
  ].filter(Boolean)
  const activeTab = tabs.some((t) => t.id === tab) ? tab : 'matches'

  const settingsItems = [
    { label: 'Profile picture', onClick: () => setShowPictureModal(true) },
    { label: 'Featured deck', onClick: () => setShowFeaturedModal(true) },
    { label: 'Profile showcase', onClick: () => setShowcaseFocus('bio') },
    { label: 'Privacy settings', onClick: () => setShowPrivacyModal(true) },
    { label: 'Profile badges', onClick: () => setShowBadgesModal(true) },
    { label: 'Block list', onClick: () => setShowBlockListModal(true) },
    /^\d+$/.test(String(playerId)) && { label: 'Queue settings', onClick: () => setShowQueueSettingsModal(true) },
    { label: data.profile_reset_at ? 'Undo Fresh Start' : 'Fresh Start', onClick: () => setShowResetModal(true) },
    authUser?.is_store_admin && { label: 'My orders', onClick: () => navigate('/store/orders') },
    // Only the player themselves, not an admin viewing their profile
    isSelf && { label: 'Export my data', onClick: () => setShowDataExportModal(true) },
  ].filter(Boolean)

  // Moderators can put someone's own picture back to their Discord one
  // (admins do it from the picture editor, like the owner)
  const canResetPicture = !data.is_owner && authUser?.is_moderator && data.picture_kind && data.picture_kind !== 'discord'
  const resetPicture = () => {
    if (!window.confirm(`Put ${data.name}'s picture back to their Discord picture?`)) return
    setProfilePicture(playerId, { kind: 'discord' })
      .then((d) => setData((prev) => prev && { ...prev, avatar_url: d.url, picture_kind: d.kind, picture_card: d.card }))
      .catch((err) => window.alert(err.message || 'Could not reset the picture'))
  }

  const hiddenSections = !data.is_owner && Object.values(vis).some((v) => !v)

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

      {/* Display name: a banner until the owner picks one, then a change link */}
      {data.is_owner && (
        <DisplayNameBanner
          playerId={playerId}
          defaultName={data.name}
          hasCustomName={data.has_custom_display_name}
          onNameChange={handleNameChange}
        />
      )}

      <PlayerHeader
        data={data}
        playerId={playerId}
        headline={headline}
        avatarEntries={avatarMode ? avatarEntries : []}
        eventFilter={eventFilter}
        pastEvents={pastEvents}
        onEventChange={(val) => refetch(val, 1, undefined, 1)}
        canSeeLifetime={canSeeLifetime}
        onReport={data.is_owner ? () => setShowReportModal(true) : undefined}
        settingsItems={data.is_owner ? settingsItems : []}
        onEditPicture={data.is_owner ? () => setShowPictureModal(true) : undefined}
        onResetPicture={canResetPicture ? resetPicture : undefined}
        onPostseason={() => setTab('postseason')}
        hiddenBadges={data.hidden_badges || []}
        shownBadges={shownBadges === undefined ? (data.shown_badges ?? null) : shownBadges}
        bio={showcase && (
          <ProfileBio bio={showcase.bio} isOwner={Boolean(data.is_owner)} onEdit={() => setShowcaseFocus('bio')} />
        )}
        featured={(
          <>
            <FeaturedDeck
              playerId={playerId}
              isOwner={Boolean(data.is_owner)}
              onEdit={() => setShowFeaturedModal(true)}
              recentDecks={data.recent_decks || []}
              refreshKey={featuredKey}
              onLoaded={setFeaturedDeckState}
            />
            {showcase && (
              <>
                <FavoriteCardBox
                  card={showcase.favorite_card}
                  isOwner={Boolean(data.is_owner)}
                  onEdit={() => setShowcaseFocus('card')}
                />
                <RivalBox
                  rival={showcase.rival}
                  isOwner={Boolean(data.is_owner)}
                  onEdit={() => setShowcaseFocus('rival')}
                />
              </>
            )}
          </>
        )}
      />

      <PendingMatches
        matches={data.pending_matches}
        playerId={playerId}
        isOwner={data.is_owner}
        onDispute={refreshCurrentPage}
      />

      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-border">
        <nav aria-label="Profile sections" className="flex flex-wrap gap-x-6" role="tablist">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={activeTab === t.id}
              onClick={() => setTab(t.id)}
              className={`min-h-11 px-1 text-[15px] font-semibold border-b-[3px] -mb-px transition-colors ${
                activeTab === t.id
                  ? 'text-text-primary border-secondary'
                  : 'text-text-muted border-transparent hover:text-text-primary'
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
        {hiddenSections && (
          <p className="text-xs text-text-muted pb-3">Some sections of this profile are private.</p>
        )}
      </div>

      {activeTab === 'overview' && (
        <div className="space-y-6">
          <OverallStats
            data={data}
            stats={stats}
            statsType={statsType}
            onStatsTypeChange={setStatsType}
          />
          {sectionVisible('elo_history') && (
            <EloHistory eloHistory={data.elo_history} currentElo={data.elo} open />
          )}
          {avatarMode && sectionVisible('elo_history') && (
            <AvatarEloHistory
              history={data.avatar_event_elo.history}
              entries={avatarEntries}
              eventName={data.avatar_event_elo.event_name}
              open
            />
          )}
          {sectionVisible('recent_decks') && (
            <RecentDecks decks={data.recent_decks} playerId={playerId} showLinks={sectionVisible('deck_urls')} open />
          )}
          {data.matches?.length > 0 && (
            <div className="flex justify-end">
              <button type="button" onClick={() => setTab('matches')} className="text-sm font-semibold text-secondary hover:underline">
                See all matches &rarr;
              </button>
            </div>
          )}
        </div>
      )}

      {activeTab === 'avatars' && (
        <AvatarPerformance
          avatars={data.avatar_performance}
          playerId={playerId}
          lifetimeElo={data.lifetime_avatar_elo}
          period={eventFilter}
          isAdmin={Boolean(isAdmin)}
          canEdit={Boolean(data.is_owner)}
          onHiddenChange={(names) => {
            const hidden = new Set(names)
            setData((d) => d && {
              ...d,
              avatar_performance: d.avatar_performance.map((a) => ({ ...a, hidden: hidden.has(a.name) })),
            })
          }}
        />
      )}

      {activeTab === 'matchups' && (
        <div className="space-y-6">
          {sectionVisible('avatar_matchups') && (
            <AvatarMatchups
              matchups={data.avatar_matchups}
              byAvatar={data.avatar_matchups_by_avatar}
              myAvatars={data.avatar_performance?.length ? data.avatar_performance.filter((a) => !a.hidden).map((a) => a.name) : null}
            />
          )}
          {sectionVisible('elo_brackets') && <EloBrackets brackets={data.elo_vs_brackets} />}
        </div>
      )}

      {activeTab === 'cards' && (
        <CardStats
          playerId={playerId}
          eventFilter={eventFilter}
          isOwner={data.is_owner}
          isPublic={Boolean(vis.card_stats)}
        />
      )}

      {activeTab === 'limited' && (
        <LimitedArena
          limited={data.limited}
          playerId={playerId}
          isOwner={data.is_owner}
          profileVisibility={vis}
          onMatchUpdate={refreshCurrentPage}
          open
        />
      )}

      {activeTab === 'precon' && <PreconStandings data={precon} />}

      {activeTab === 'matches' && (
        <div className="space-y-6">
          <MatchFilters filters={matchFilters} data={withPreconFilters(data.match_filters, precon, matchFilters)} onChange={changeMatchFilters} />

          <MatchHistoryTable
            title="Match History"
            subtitle={data.match_filters?.casual?.wins + data.match_filters?.casual?.losses > 0 ? 'Casual games do not affect ratings.' : undefined}
            matches={data.matches}
            emptyText={Object.keys(data.match_filters?.active || {}).length ? 'No matches fit these filters.' : undefined}
            pagination={data.pagination}
            playerId={playerId}
            isOwner={data.is_owner}
            profileVisibility={vis}
            perPage={perPage}
            perPageOptions={PER_PAGE_OPTIONS}
            onPageChange={(p) => refetch(undefined, p)}
            onPerPageChange={(pp) => refetch(undefined, 1, undefined, undefined, pp)}
            onEditDeck={data.is_owner ? (matchId, url) => setEditDeck({ matchId, url }) : undefined}
            onMatchUpdate={refreshCurrentPage}
          />

          <PreconMatchHistory data={precon} filters={matchFilters} />

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
        </div>
      )}

      {activeTab === 'postseason' && (
        <div className="space-y-8">
          <AvatarHonoursSection honours={avatarHonours} />
          <PostseasonSection playerId={playerId} />
          <EventAvatarBadgesSection badges={eventAvatarBadges} />
          <PaperFinishesSection finishes={paperFinishes} />
        </div>
      )}

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

      {showFeaturedModal && (
        <FeaturedDeckModal
          playerId={playerId}
          current={featuredDeck}
          recentDecks={data.recent_decks || []}
          onClose={() => setShowFeaturedModal(false)}
          onSaved={() => setFeaturedKey((k) => k + 1)}
        />
      )}

      {showPictureModal && (
        <ProfilePictureModal
          playerId={playerId}
          onClose={() => setShowPictureModal(false)}
          onSaved={(d) => setData((prev) => prev && { ...prev, avatar_url: d.url, picture_kind: d.kind, picture_card: d.card })}
        />
      )}

      {showcaseFocus && (
        <ShowcaseModal
          playerId={playerId}
          current={showcase}
          focus={showcaseFocus}
          onClose={() => setShowcaseFocus(null)}
          onSaved={() => setShowcaseKey((k) => k + 1)}
        />
      )}

      {showBadgesModal && (
        <ManageBadgesModal
          playerId={playerId}
          badges={profileBadges({
            marks: bracketMarks, honours: avatarHonours, paperFinishes, eventBadges: eventAvatarBadges,
          })}
          hidden={data.hidden_badges || []}
          shown={shownBadges === undefined ? (data.shown_badges ?? null) : shownBadges}
          onClose={() => setShowBadgesModal(false)}
          onSaved={setShownBadgesState}
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

      {showQueueSettingsModal && (
        <QueueSettingsModal
          playerId={playerId}
          onClose={() => setShowQueueSettingsModal(false)}
        />
      )}

      {showDataExportModal && (
        <DataExportModal
          playerId={playerId}
          onClose={() => setShowDataExportModal(false)}
        />
      )}

      {showResetModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={() => setShowResetModal(false)}>
          <div className="bg-bg-surface border border-border rounded-lg p-6 max-w-md w-full mx-4" onClick={e => e.stopPropagation()}>
            {data.profile_reset_at ? (
              <>
                <h3 className="text-lg font-semibold text-text-primary mb-3">Undo Fresh Start</h3>
                <p className="text-sm text-text-muted mb-2">
                  Your profile was reset on <strong className="text-text-primary">{new Date(data.profile_reset_at).toLocaleDateString()}</strong>.
                </p>
                <p className="text-sm text-text-muted mb-4">
                  Undoing this will restore your full match history and stats from before the reset.
                </p>
              </>
            ) : (
              <>
                <h3 className="text-lg font-semibold text-text-primary mb-3">Fresh Start</h3>
                <p className="text-sm text-text-muted mb-2">
                  This will hide your match history and stats from previous seasons on your profile. Games from the current season always stay visible.
                </p>
                <p className="text-sm text-text-muted mb-4">
                  Your rating will stay the same. No matches are deleted — they just won't be shown on your profile. You can undo this at any time.
                </p>
              </>
            )}
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setShowResetModal(false)}
                className="px-4 py-2 text-sm rounded border border-border text-text-muted hover:text-text-primary transition-colors"
                disabled={resetLoading}
              >
                Cancel
              </button>
              <button
                onClick={async () => {
                  setResetLoading(true)
                  try {
                    if (data.profile_reset_at) {
                      await undoProfileReset(playerId)
                    } else {
                      await resetOwnProfile(playerId)
                    }
                    setShowResetModal(false)
                    refreshCurrentPage()
                  } catch (err) {
                    alert(err.message || 'Failed to update profile')
                  } finally {
                    setResetLoading(false)
                  }
                }}
                className={`px-4 py-2 text-sm rounded transition-colors disabled:opacity-50 ${
                  data.profile_reset_at
                    ? 'bg-secondary text-black hover:opacity-90'
                    : 'bg-red-700 text-white hover:bg-red-600'
                }`}
                disabled={resetLoading}
              >
                {resetLoading
                  ? (data.profile_reset_at ? 'Restoring...' : 'Resetting...')
                  : (data.profile_reset_at ? 'Restore Full History' : 'Start Fresh')
                }
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  )
}
