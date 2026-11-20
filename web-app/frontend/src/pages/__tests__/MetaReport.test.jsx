import { describe, it, expect, vi, beforeEach } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import { renderWithProviders as renderWithRouter, screen, waitFor, userEvent } from '@/test/test-utils'
import MetaReport from '@/pages/MetaReport'
import { getMetaReport, getMetaReportDm, listMetaReports, setMetaReportDm } from '@/api/metaReports'
import { getMe } from '@/api/auth'

vi.mock('@/api/metaReports', () => ({
  listMetaReports: vi.fn(),
  getMetaReport: vi.fn(),
  getMetaReportDm: vi.fn(),
  setMetaReportDm: vi.fn(),
}))
vi.mock('@/api/auth', () => ({ getMe: vi.fn() }))
vi.mock('@/api/decks', () => ({ createPsoTable: vi.fn() }))

const REPORT = {
  slug: '2026-09-b',
  period: { label: 'Sep 16–30, 2026', publishLabel: 'Oct 15, 2026' },
  story: [{ headline: 'Pathfinder is the best deck nobody plays.', detail: '56% win rate.' }],
  ranked: {
    rankedGames: 1284,
    archetypes: [
      { avatar: 'Sparkmage', elements: 'Air / Fire', games: 180, wins: 99, winRate: 55, share: 14.2, tier: 'S', move: -1 },
      { avatar: 'Pathfinder', elements: 'Air / Earth', games: 60, wins: 34, winRate: 56.3, share: 5.2, tier: 'A', move: 'new' },
    ],
    matchups: {
      minGames: 20,
      archetypes: [{ avatar: 'Sparkmage', elements: 'Air / Fire' }, { avatar: 'Pathfinder', elements: 'Air / Earth' }],
      cells: [[null, { games: 30, winRate: 40 }], [{ games: 30, winRate: 60 }, null]],
    },
    counters: [{
      target: 'Sparkmage', counter: 'Pathfinder', winRate: 60, games: 30, targetElsewhere: 58, targetVsCounter: 40,
      signals: ['Lower curve: 2.6 average cost vs 3.4'], why: 'Pathfinder does it on a lower curve.',
    }],
    deckTypes: {
      minDeckGames: 20,
      minGames: 10,
      options: [
        { key: 'Fire', label: 'Mono Fire', kind: 'mono', games: 40, avatars: [{ avatar: 'Sparkmage', games: 25 }] },
        { key: 'Air / Water', label: 'Air / Water', kind: 'pair', games: 30, avatars: [] },
      ],
      picks: {
        'Fire|': {
          games: 40, winRate: 47.5,
          avatar: [{ avatar: 'Deathspeaker', games: 12, winRate: 25 }, { avatar: 'Pathfinder', games: 14, winRate: 64.3 }],
          deckType: [{ elements: 'Water', games: 11, winRate: 36.4 }],
          both: [],
        },
        'Fire|Sparkmage': {
          games: 25, winRate: 60,
          avatar: [{ avatar: 'Battlemage', games: 10, winRate: 30 }],
          deckType: [], both: [],
        },
        'Air / Water|': { games: 30, winRate: 55, avatar: [], deckType: [], both: [] },
      },
    },
    elementTrend: {
      days: ['2026-09-16', '2026-09-17', '2026-09-18'],
      series: { Air: [50, 55, null], Earth: [40, 35, 30], Fire: [45, 45, 50], Water: [40, 42, 44] },
      share: { Air: 52, Earth: 36, Fire: 47, Water: 45 },
      change: { Air: 3, Earth: -3 },
    },
  },
  cards: {
    available: true,
    rising: [{ name: 'Lightning Bolt', share: 41, change: 7.4, winRate: 55, trend: [51, 53, 55] }],
    falling: [{ name: 'Cave Trolls', share: 15, change: -6.2, winRate: 48, trend: [54, 48] }],
    sleeper: { name: 'Sling Pixies', winRate: 58.9, share: 6, games: 212 },
  },
  tournaments: {
    events: [{ name: 'Explorer Columbus', folder: 'explorer-columbus', date: '2026-09-27', players: 18, winnerAvatar: 'Pathfinder', winnerElements: 'Air / Earth' }],
    vsLadder: {
      available: true,
      tournament: [{ avatar: 'Geomancer', top8: 3, top8Total: 16, top8Share: 18.8, rankedShare: 2.8 }],
      ladder: [{ avatar: 'Imposter', top8: 0, top8Total: 16, top8Share: 0, rankedShare: 14.2 }],
    },
    deckToTry: { deckId: 'abc123xyz', avatar: 'Pathfinder', elements: 'Air / Earth', placement: 1, player: 'Ann', event: 'Explorer Columbus' },
  },
}

function renderPage(route = '/meta-report') {
  return renderWithRouter(
    <Routes>
      <Route path="/meta-report" element={<MetaReport />} />
      <Route path="/meta-report/:slug" element={<MetaReport />} />
    </Routes>,
    { route },
  )
}

describe('MetaReport', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listMetaReports.mockResolvedValue({ reports: [
      { slug: '2026-09-b', label: 'Sep 16–30, 2026', publishLabel: 'Oct 15, 2026' },
      { slug: '2026-09-a', label: 'Sep 1–15, 2026', publishLabel: 'Oct 1, 2026' },
    ] })
    getMetaReport.mockResolvedValue(REPORT)
    getMe.mockRejectedValue(new Error('not logged in'))
  })

  it('opens the newest report and shows each section', async () => {
    renderPage()
    expect(await screen.findByText('Pathfinder is the best deck nobody plays.')).toBeInTheDocument()
    expect(getMetaReport).toHaveBeenCalledWith('2026-09-b')
    expect(screen.getByRole('combobox', { name: 'Report' })).toHaveValue('2026-09-b')
    expect(screen.getByText('Lightning Bolt')).toBeInTheDocument()
    expect(screen.getByText('Sling Pixies')).toBeInTheDocument()
    expect(screen.getAllByText('60%').length).toBeGreaterThan(0)
    expect(screen.getByRole('link', { name: 'Top 8 lists' })).toHaveAttribute('href', '/top-8/explorer-columbus')
    expect(screen.getByRole('button', { name: /share/i })).toBeInTheDocument()
  })

  it('shows counter picks, the element trend and tournament vs ladder', async () => {
    renderPage()
    expect(await screen.findByText('Pathfinder does it on a lower curve.')).toBeInTheDocument()
    expect(screen.getByText('Lower curve: 2.6 average cost vs 3.4')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Element share of ranked decks by day' })).toBeInTheDocument()
    expect(screen.getByText('Wins Top 8s, rare on the ladder')).toBeInTheDocument()
    expect(screen.getByText('Geomancer')).toBeInTheDocument()
  })

  it('shows what a deck type loses to and beats', async () => {
    renderPage()
    expect(await screen.findByText("Your deck's matchups")).toBeInTheDocument()
    expect(screen.getByText('Mono Fire decks')).toBeInTheDocument()
    expect(screen.getByText('Deathspeaker')).toBeInTheDocument()
    expect(screen.getByText('25%')).toBeInTheDocument()
    expect(screen.getByText('64.3%')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Deck types' }))
    expect(screen.getByText('36.4%')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Avatars' }))
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Your Avatar' }), 'Sparkmage')
    expect(screen.getByText('Sparkmage Mono Fire decks')).toBeInTheDocument()
    expect(screen.getByText('Battlemage')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Your deck type' }), 'Air / Water')
    expect(screen.getByText('Air / Water decks')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Your Avatar' })).toHaveValue('')
  })

  it('says so when no deck type has enough games', async () => {
    getMetaReport.mockResolvedValue({ ...REPORT, ranked: { ...REPORT.ranked, deckTypes: { options: [], picks: {} } } })
    renderPage()
    expect(await screen.findByText(/Not enough ranked games to break matchups down by deck type/)).toBeInTheDocument()
  })

  it('loads an older report from the picker', async () => {
    renderPage()
    await screen.findByText('Pathfinder is the best deck nobody plays.')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Report' }), '2026-09-a')
    await waitFor(() => expect(getMetaReport).toHaveBeenCalledWith('2026-09-a'))
  })

  it('shares with the share sheet when the device has one', async () => {
    const share = vi.fn().mockResolvedValue()
    Object.defineProperty(navigator, 'share', { value: share, configurable: true })
    renderPage('/meta-report/2026-09-b')
    await screen.findByText('Pathfinder is the best deck nobody plays.')
    await userEvent.click(screen.getByRole('button', { name: /share/i }))
    expect(share).toHaveBeenCalledWith(expect.objectContaining({
      title: 'Summit Meta Report: Sep 16–30, 2026',
      url: expect.stringContaining('/meta-report/2026-09-b'),
    }))
    delete navigator.share
  })

  it('asks logged-out visitors to log in with Discord for DMs', async () => {
    renderPage()
    expect(await screen.findByRole('link', { name: 'Log in with Discord' })).toHaveAttribute('href', expect.stringContaining('/auth/discord'))
  })

  it('turns report DMs on for a Discord login', async () => {
    getMe.mockResolvedValue({ id: '123', username: 'Fan' })
    getMetaReportDm.mockResolvedValue({ canDm: true, subscribed: false })
    setMetaReportDm.mockResolvedValue({ canDm: true, subscribed: true })
    renderPage()
    const toggle = await screen.findByRole('switch')
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    await userEvent.click(toggle)
    expect(setMetaReportDm).toHaveBeenCalledWith(true)
    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'))
  })

  it('explains when nothing is published yet', async () => {
    listMetaReports.mockResolvedValue({ reports: [] })
    renderPage()
    expect(await screen.findByText(/first Meta Report hasn/)).toBeInTheDocument()
  })
})
