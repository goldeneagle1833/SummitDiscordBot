import { lazy, Suspense } from 'react'
import { createBrowserRouter, RouterProvider, Outlet } from 'react-router-dom'
import { AuthProvider } from '@/context/AuthContext'
import Nav from '@/components/layout/Nav'
import Footer from '@/components/layout/Footer'
import AdminGuard from '@/components/layout/AdminGuard'
import Spinner from '@/components/ui/Spinner'

// Phase 3: Core data pages
import Leaderboard from '@/pages/Leaderboard'
import Season from '@/pages/Season'
import Player from '@/pages/Player'
import DeckStats from '@/pages/DeckStats'
import Matches from '@/pages/Matches'
import DeckSnapshot from '@/pages/DeckSnapshot'

// Phase 4: Events & Decks
import Events from '@/pages/Events'
import EventDetail from '@/pages/EventDetail'
import Stats from '@/pages/Stats'
import StatsEvent from '@/pages/StatsEvent'
import DeckDetail from '@/pages/DeckDetail'
import DeckRecommendations from '@/pages/DeckRecommendations'

// Phase 5: Cards & Avatars
import Avatars from '@/pages/Avatars'
import AvatarDetail from '@/pages/AvatarDetail'
import Cards from '@/pages/Cards'
import CardDetail from '@/pages/CardDetail'
import Elements from '@/pages/Elements'
import LivePopularCards from '@/pages/LivePopularCards'

// Phase 6: Content & Interactive
import Home from '@/pages/Home'
import About from '@/pages/About'
import Help from '@/pages/Help'
import Privacy from '@/pages/Privacy'
import Terms from '@/pages/Terms'
import DeckHelp from '@/pages/DeckHelp'
import Community from '@/pages/Community'
import LifeCounter from '@/pages/LifeCounter'
import FunStats from '@/pages/FunStats'
import FartLeaderboard from '@/pages/FartLeaderboard'
import Login from '@/pages/Login'

// Lazy-loaded pages
const CurioTracking = lazy(() => import('@/pages/CurioTracking'))

// Phase 7: Admin
import AuditLog from '@/pages/admin/AuditLog'

// Error pages
import ErrorPage from '@/pages/ErrorPage'
import NotFound from '@/pages/NotFound'

function LazyPage({ children }) {
  return <Suspense fallback={<Spinner className="py-20" />}>{children}</Suspense>
}

function Layout() {
  return (
    <AuthProvider>
      <div className="min-h-screen flex flex-col">
        <Nav />
        <main className="flex-1 max-w-content mx-auto w-full px-4 py-6">
          <Outlet />
        </main>
        <Footer />
      </div>
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
      { path: '/elo/limited', element: <Leaderboard /> },
      { path: '/elo/global', element: <Leaderboard /> },
      { path: '/elo/server/:serverId', element: <Leaderboard /> },
      { path: '/season/:seasonId', element: <Season /> },
      { path: '/player/:playerId', element: <Player /> },
      { path: '/match-history', element: <Matches /> },
      { path: '/deck-stats/:playerId', element: <DeckStats /> },
      { path: '/deck-snapshot/:matchId/:playerId', element: <DeckSnapshot /> },
      // Phase 4: Events & Decks
      { path: '/top-8', element: <Events /> },
      { path: '/top-8/:folder', element: <EventDetail /> },
      { path: '/stats', element: <Stats /> },
      { path: '/stats/:folder', element: <StatsEvent /> },
      { path: '/deck-rec', element: <DeckRecommendations /> },
      { path: '/deck-rec/:deckId', element: <DeckDetail /> },
      // Phase 5: Cards & Avatars
      { path: '/avatars', element: <Avatars /> },
      { path: '/avatar/:name', element: <AvatarDetail /> },
      { path: '/cards', element: <Cards /> },
      { path: '/card/:name', element: <CardDetail /> },
      { path: '/elements', element: <Elements /> },
      { path: '/live-popular-cards', element: <LivePopularCards /> },
      // Phase 6: Content & Interactive
      { path: '/about', element: <About /> },
      { path: '/help', element: <Help /> },
      { path: '/privacy', element: <Privacy /> },
      { path: '/terms', element: <Terms /> },
      { path: '/deck-help', element: <DeckHelp /> },
      { path: '/community', element: <Community /> },
      { path: '/life-counter', element: <LifeCounter /> },
      { path: '/curio-tracking', element: <LazyPage><CurioTracking /></LazyPage> },
      { path: '/fun-stats', element: <FunStats /> },
      { path: '/secret-fart-leaderboard', element: <FartLeaderboard /> },
      { path: '/login', element: <Login /> },
      // Phase 7: Admin
      { path: '/admin/audit-log', element: <AdminGuard><AuditLog /></AdminGuard> },
      // Error & 404
      { path: '/error', element: <ErrorPage /> },
      { path: '*', element: <NotFound /> },
    ],
  },
])

export default function App() {
  return <RouterProvider router={router} />
}
