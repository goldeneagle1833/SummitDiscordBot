import { lazy, Suspense, useEffect, useRef } from 'react'
import { createBrowserRouter, RouterProvider, Navigate, Outlet, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from '@/context/AuthContext'
import Nav from '@/components/layout/Nav'
import Footer from '@/components/layout/Footer'
import AdminGuard from '@/components/layout/AdminGuard'
import StoreAdminGuard from '@/components/layout/StoreAdminGuard'
import LoginGuard from '@/components/layout/LoginGuard'
import ExplorerAdminGuard from '@/components/layout/ExplorerAdminGuard'
import ArticleReviewerGuard from '@/components/layout/ArticleReviewerGuard'
import Spinner from '@/components/ui/Spinner'
import { ES_BASE, ES_PATHS, ES_STOREFRONT_SLUG } from '@/utils/explorerSite'

/**
 * A page loaded on demand. After a deploy, a tab opened earlier still asks for
 * the old page files, which are gone; reload once to pick up the new build.
 */
function lazyPage(load) {
  return lazy(() => load().catch((err) => {
    let reloaded = false
    try { reloaded = sessionStorage.getItem('page-chunk-reload') === '1' } catch { /* storage blocked */ }
    if (!reloaded) {
      try { sessionStorage.setItem('page-chunk-reload', '1') } catch { /* storage blocked */ }
      window.location.reload()
      return new Promise(() => {})
    }
    throw err
  }).then((mod) => {
    try { sessionStorage.removeItem('page-chunk-reload') } catch { /* storage blocked */ }
    return mod
  }))
}

// Phase 3: Core data pages
const Leaderboard = lazyPage(() => import('@/pages/Leaderboard'))
const LimitedLeaderboard = lazyPage(() => import('@/pages/LimitedLeaderboard'))
const Player = lazyPage(() => import('@/pages/Player'))
const DeckStats = lazyPage(() => import('@/pages/DeckStats'))
const PlayerAvatar = lazyPage(() => import('@/pages/PlayerAvatar'))
const Matches = lazyPage(() => import('@/pages/Matches'))
const DeckSnapshot = lazyPage(() => import('@/pages/DeckSnapshot'))

// Phase 4: Events & Decks
const Events = lazyPage(() => import('@/pages/Events'))
const Brackets = lazyPage(() => import('@/pages/Brackets'))
const Bracket = lazyPage(() => import('@/pages/Bracket'))
const MyBrackets = lazyPage(() => import('@/pages/MyBrackets'))
const Standings = lazyPage(() => import('@/pages/Standings'))
const EventDetail = lazyPage(() => import('@/pages/EventDetail'))
const EventCompare = lazyPage(() => import('@/pages/EventCompare'))
const Stats = lazyPage(() => import('@/pages/Stats'))
const StatsEvent = lazyPage(() => import('@/pages/StatsEvent'))
const DeckDetail = lazyPage(() => import('@/pages/DeckDetail'))
const DeckRecommendations = lazyPage(() => import('@/pages/DeckRecommendations'))
const DeckArchetypes = lazyPage(() => import('@/pages/DeckArchetypes'))

// Phase 5: Cards & Avatars
const Avatars = lazyPage(() => import('@/pages/Avatars'))
const AvatarDetail = lazyPage(() => import('@/pages/AvatarDetail'))
const AvatarTopPlayers = lazyPage(() => import('@/pages/AvatarTopPlayers'))
const EloBreakdownMatches = lazyPage(() => import('@/pages/EloBreakdownMatches'))
const CardDetail = lazyPage(() => import('@/pages/CardDetail'))
const CardStats = lazyPage(() => import('@/pages/CardStats'))
const Elements = lazyPage(() => import('@/pages/Elements'))
// Phase 6: Content & Interactive
import Home from '@/pages/Home'
const About = lazyPage(() => import('@/pages/About'))
const SummitFormat = lazyPage(() => import('@/pages/SummitFormat'))
const Help = lazyPage(() => import('@/pages/Help'))
const Privacy = lazyPage(() => import('@/pages/Privacy'))
const Terms = lazyPage(() => import('@/pages/Terms'))
const DeckHelp = lazyPage(() => import('@/pages/DeckHelp'))
const Community = lazyPage(() => import('@/pages/Community'))
const Articles = lazyPage(() => import('@/pages/Articles'))
const ArticleDetail = lazyPage(() => import('@/pages/ArticleDetail'))
const ArticleEditor = lazyPage(() => import('@/pages/ArticleEditor'))
const MyArticles = lazyPage(() => import('@/pages/MyArticles'))
const ArticlesReview = lazyPage(() => import('@/pages/admin/ArticlesReview'))
const LifeCounter = lazyPage(() => import('@/pages/LifeCounter'))
const FunStats = lazyPage(() => import('@/pages/FunStats'))
const FartLeaderboard = lazyPage(() => import('@/pages/FartLeaderboard'))
const Rumble = lazyPage(() => import('@/pages/Rumble'))
const CardPoints = lazyPage(() => import('@/pages/CardPoints'))
const DeckBuilder = lazyPage(() => import('@/pages/DeckBuilder'))
const Login = lazyPage(() => import('@/pages/Login'))
const Store = lazyPage(() => import('@/pages/Store'))
const StoreCheckout = lazyPage(() => import('@/pages/StoreCheckout'))
const StorePrivateProduct = lazyPage(() => import('@/pages/StorePrivateProduct'))
const StoreSuccess = lazyPage(() => import('@/pages/StoreSuccess'))
const StoreCancelled = lazyPage(() => import('@/pages/StoreCancelled'))
const MyOrders = lazyPage(() => import('@/pages/MyOrders'))
const Feedback = lazyPage(() => import('@/pages/Feedback'))

const ExplorerStandings = lazyPage(() => import('@/pages/ExplorerStandings'))

// Phase 7: Admin
const AdminHub = lazyPage(() => import('@/pages/admin/AdminHub'))
const AuditLog = lazyPage(() => import('@/pages/admin/AuditLog'))
const StoreAdmin = lazyPage(() => import('@/pages/admin/StoreAdmin'))
const StoreOrderPrint = lazyPage(() => import('@/pages/admin/StoreOrderPrint'))
const ActiveConnections = lazyPage(() => import('@/pages/admin/ActiveConnections'))
const UniqueUsers = lazyPage(() => import('@/pages/admin/UniqueUsers'))
const SessionAnalytics = lazyPage(() => import('@/pages/admin/SessionAnalytics'))
const ExternalMatchesAdmin = lazyPage(() => import('@/pages/admin/ExternalMatches'))
const OmensMatchesAdmin = lazyPage(() => import('@/pages/admin/OmensMatches'))
const ChartDetail = lazyPage(() => import('@/pages/admin/ChartDetail'))
const Monitoring = lazyPage(() => import('@/pages/admin/Monitoring'))
const BracketsAdmin = lazyPage(() => import('@/pages/admin/BracketsAdmin'))
const UserProfiles = lazyPage(() => import('@/pages/admin/UserProfiles'))
const ExplorerApplications = lazyPage(() => import('@/pages/admin/ExplorerApplications'))
const ExplorerCalendar = lazyPage(() => import('@/pages/admin/ExplorerCalendar'))
const MetaReportsAdmin = lazyPage(() => import('@/pages/admin/MetaReports'))
const PaperBadgesAdmin = lazyPage(() => import('@/pages/admin/PaperBadges'))
const MetaReport = lazyPage(() => import('@/pages/MetaReport'))
const MetaReportEmail = lazyPage(() => import('@/pages/MetaReportEmail'))
const ExplorerApply = lazyPage(() => import('@/pages/ExplorerApply'))
// Explorer Series mini-site (its own header, menu and look under /explorer-series)
const ExplorerSiteLayout = lazyPage(() => import('@/components/explorer/ExplorerSiteLayout'))
const ExplorerHome = lazyPage(() => import('@/pages/explorer/ExplorerHome'))
const ExplorerEvents = lazyPage(() => import('@/pages/explorer/ExplorerEvents'))
const SeasonFeedback = lazyPage(() => import('@/pages/SeasonFeedback'))

// Error pages
import ErrorPage from '@/pages/ErrorPage'
import NotFound from '@/pages/NotFound'

function LazyPage({ children }) {
  return <Suspense fallback={<Spinner className="py-20" />}>{children}</Suspense>
}

const SESSION_ID = crypto.randomUUID?.() || Math.random().toString(36).slice(2)
const USER_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || null

function useHeartbeat(user) {
  const location = useLocation()
  useEffect(() => {
    const send = () => {
      const payload = { sid: SESSION_ID, path: location.pathname, timezone: USER_TZ }
      if (user && user.id) {
        payload.user_id = String(user.id)
        payload.username = user.username || null
      }
      const body = JSON.stringify(payload)
      if (navigator.sendBeacon) {
        navigator.sendBeacon('/api/analytics/heartbeat', new Blob([body], { type: 'application/json' }))
      } else {
        fetch('/api/analytics/heartbeat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: true })
      }
    }
    send()
    const id = setInterval(send, 30000)
    return () => clearInterval(id)
  }, [location.pathname, user])
}

function usePageTracking(user) {
  const location = useLocation()
  const prevPath = useRef(null)
  useEffect(() => {
    const path = location.pathname
    if (path === prevPath.current) return
    prevPath.current = path
    const payload = { path, referrer: document.referrer || null, sid: SESSION_ID }
    if (user && user.id) {
      payload.user_id = String(user.id)
      payload.username = user.username || null
    }
    const body = JSON.stringify(payload)
    if (navigator.sendBeacon) {
      navigator.sendBeacon('/api/analytics/page-view', new Blob([body], { type: 'application/json' }))
    } else {
      fetch('/api/analytics/page-view', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: true })
    }
  }, [location.pathname, user])
}

function TrackingProvider({ children }) {
  const { user } = useAuth()
  usePageTracking(user || null)
  useHeartbeat(user || null)
  return children
}

// Old links keep working: send them to the same page's new address, keeping
// any ?query (application ids, filters) and #hash.
function RedirectKeepQuery({ to }) {
  const { search, hash } = useLocation()
  return <Navigate to={`${to}${search}${hash}`} replace />
}

function ExplorerSite() {
  return (
    <AuthProvider>
      <TrackingProvider>
        <Suspense fallback={<Spinner className="py-20" />}>
          <ExplorerSiteLayout>
            <Suspense fallback={<Spinner className="py-20" />}>
              <Outlet />
            </Suspense>
          </ExplorerSiteLayout>
        </Suspense>
      </TrackingProvider>
    </AuthProvider>
  )
}

function Layout() {
  return (
    <AuthProvider>
      <TrackingProvider>
        <div className="min-h-screen flex flex-col">
          <Nav />
          <main className="flex-1 max-w-content mx-auto w-full px-4 py-6">
            {/* Pages load on demand, so a visit only downloads the page it opens */}
            <Suspense fallback={<Spinner className="py-20" />}>
              <Outlet />
            </Suspense>
          </main>
          <Footer />
        </div>
      </TrackingProvider>
    </AuthProvider>
  )
}

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: '/', element: <Home /> },
      // Phase 3: Core data pages
      { path: '/elo', element: <Leaderboard /> },
      { path: '/elo/limited', element: <LimitedLeaderboard /> },
      { path: '/elo/global', element: <Leaderboard /> },
      { path: '/elo/server/:serverId', element: <Leaderboard /> },
      { path: '/season/:seasonId', element: <Navigate to="/elo" replace /> },
      { path: '/player/:playerId', element: <Player /> },
      { path: '/match-history', element: <Matches /> },
      { path: '/deck-stats/:playerId', element: <DeckStats /> },
      { path: '/player/:playerId/avatar/:avatarName', element: <PlayerAvatar /> },
      { path: '/deck-snapshot/:matchId/:playerId', element: <DeckSnapshot /> },
      // Phase 4: Events & Decks
      { path: '/standings', element: <Standings /> },
      { path: '/brackets', element: <Brackets /> },
      { path: '/brackets/manage', element: <MyBrackets /> },
      { path: '/brackets/:slug', element: <Bracket /> },
      { path: '/top-8', element: <Events /> },
      { path: '/top-8/compare', element: <EventCompare /> },
      { path: '/top-8/:folder', element: <EventDetail /> },
      { path: '/stats', element: <Stats /> },
      { path: '/stats/:folder', element: <StatsEvent /> },
      { path: '/deck-rec', element: <DeckRecommendations /> },
      { path: '/deck-archetypes', element: <DeckArchetypes /> },
      { path: '/meta-report', element: <MetaReport /> },
      { path: '/meta-report/email', element: <MetaReportEmail /> },
      { path: '/meta-report/:slug', element: <MetaReport /> },
      { path: '/deck-rec/:deckId', element: <DeckDetail /> },
      // Phase 5: Cards & Avatars
      { path: '/avatars', element: <Avatars /> },
      { path: '/avatars/top-players', element: <AvatarTopPlayers /> },
      { path: '/avatar/:name', element: <AvatarDetail /> },
      { path: '/avatars/elo-matches', element: <EloBreakdownMatches /> },
      // The old all-cards name grid is retired; card pages link back to Card Stats.
      { path: '/cards', element: <Navigate to="/card-stats" replace /> },
      // Card Stats: Card Win Rates and Popular Cards merged (2026-11-03)
      { path: '/card-stats', element: <CardStats /> },
      { path: '/cards/played-winrates', element: <Navigate to="/card-stats" replace /> },
      { path: '/card/:name', element: <CardDetail /> },
      { path: '/elements', element: <Elements /> },
      // Phase 6: Content & Interactive
      { path: '/about', element: <About /> },
      { path: '/summit-format', element: <SummitFormat /> },
      { path: '/help', element: <Help /> },
      { path: '/privacy', element: <Privacy /> },
      { path: '/terms', element: <Terms /> },
      { path: '/deck-help', element: <DeckHelp /> },
      { path: '/community', element: <Community /> },
      // Player articles (community blog)
      { path: '/articles', element: <Articles /> },
      { path: '/articles/new', element: <LoginGuard><ArticleEditor /></LoginGuard> },
      { path: '/articles/mine', element: <LoginGuard><MyArticles /></LoginGuard> },
      { path: '/articles/:id/edit', element: <LoginGuard><ArticleEditor /></LoginGuard> },
      { path: '/articles/:slug', element: <ArticleDetail /> },
      { path: '/admin/articles', element: <ArticleReviewerGuard><ArticlesReview /></ArticleReviewerGuard> },
      { path: '/life-counter', element: <LifeCounter /> },
      // The Explorer Series moved to its own mini-site (2026-11-11)
      { path: '/explorer', element: <RedirectKeepQuery to={ES_PATHS.standings} /> },
      { path: '/explorer/apply', element: <RedirectKeepQuery to={ES_PATHS.host} /> },
      { path: '/fun-stats', element: <FunStats /> },
      { path: '/rumble', element: <Rumble /> },
      { path: '/card-points', element: <CardPoints /> },
      { path: '/deck-builder', element: <DeckBuilder /> },
      { path: '/secret-fart-leaderboard', element: <FartLeaderboard /> },
      { path: '/feedback', element: <Feedback /> },
      // Post-season survey: unlisted, the link goes out in the announcement
      { path: '/season-feedback', element: <SeasonFeedback /> },
      { path: '/login', element: <Login /> },
      // Popular Cards (was the creator-only Creator Stats page) merged into Card Stats
      { path: '/popular-cards', element: <Navigate to="/card-stats" replace /> },
      { path: '/creator', element: <Navigate to="/card-stats" replace /> },
      // Store (soft launch: public by direct link, not yet in the nav)
      { path: '/store', element: <Store /> },
      { path: '/store/checkout', element: <StoreCheckout /> },
      // Private (link only) listing, opened from its link or QR code
      { path: '/store/p/:token', element: <StorePrivateProduct /> },
      { path: '/store/success', element: <StoreSuccess /> },
      { path: '/store/cancelled', element: <StoreCancelled /> },
      { path: '/store/orders', element: <LoginGuard><MyOrders /></LoginGuard> },
      // Storefront applications are closed; old links land on the store
      { path: '/store/apply', element: <Navigate to="/store" replace /> },
      { path: '/admin/store', element: <StoreAdminGuard><StoreAdmin /></StoreAdminGuard> },
      { path: '/admin', element: <AdminGuard><AdminHub /></AdminGuard> },
      { path: '/admin/audit-log', element: <AdminGuard><AuditLog /></AdminGuard> },
      { path: '/admin/active-connections', element: <AdminGuard><ActiveConnections /></AdminGuard> },
      { path: '/admin/unique-users', element: <AdminGuard><UniqueUsers /></AdminGuard> },
      { path: '/admin/session-analytics', element: <AdminGuard><SessionAnalytics /></AdminGuard> },
      { path: '/admin/external-matches', element: <AdminGuard><ExternalMatchesAdmin /></AdminGuard> },
      { path: '/admin/omens-matches', element: <AdminGuard><OmensMatchesAdmin /></AdminGuard> },
      { path: '/admin/chart/:chartType', element: <AdminGuard><ChartDetail /></AdminGuard> },
      { path: '/admin/monitoring', element: <AdminGuard><Monitoring /></AdminGuard> },
      { path: '/admin/brackets', element: <AdminGuard><BracketsAdmin /></AdminGuard> },
      { path: '/admin/users', element: <AdminGuard><UserProfiles /></AdminGuard> },
      { path: '/admin/meta-reports', element: <AdminGuard><MetaReportsAdmin /></AdminGuard> },
      { path: '/admin/paper-badges', element: <AdminGuard><PaperBadgesAdmin /></AdminGuard> },
      { path: '/admin/explorer-applications', element: <RedirectKeepQuery to={ES_PATHS.applications} /> },
      { path: '/admin/explorer-calendar', element: <RedirectKeepQuery to={ES_PATHS.calendar} /> },
      // Error & 404
      { path: '/error', element: <ErrorPage /> },
      { path: '*', element: <NotFound /> },
    ],
  },
  // The Explorer Series mini-site: same app and login, its own chrome
  {
    path: ES_BASE,
    element: <ExplorerSite />,
    children: [
      { index: true, element: <ExplorerHome /> },
      { path: 'standings', element: <ExplorerStandings /> },
      { path: 'events', element: <ExplorerEvents /> },
      { path: 'host', element: <ExplorerApply /> },
      { path: 'shop', element: <Store storefrontSlug={ES_STOREFRONT_SLUG} /> },
      { path: 'admin/applications', element: <ExplorerAdminGuard><ExplorerApplications /></ExplorerAdminGuard> },
      { path: 'admin/calendar', element: <ExplorerAdminGuard><ExplorerCalendar /></ExplorerAdminGuard> },
      { path: '*', element: <Navigate to={ES_BASE} replace /> },
    ],
  },
  // Print views live outside the site chrome so only the form is printed
  {
    path: '/admin/store/orders/:id/print',
    element: (
      <AuthProvider>
        <StoreAdminGuard><StoreOrderPrint /></StoreAdminGuard>
      </AuthProvider>
    ),
  },
])

export default function App() {
  return <RouterProvider router={router} />
}
