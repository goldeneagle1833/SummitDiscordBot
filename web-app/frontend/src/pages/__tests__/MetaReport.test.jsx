import { describe, it, expect, vi, beforeEach } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import { renderWithRouter, screen, waitFor, userEvent } from '@/test/test-utils'
import MetaReport from '@/pages/MetaReport'
import { getMetaReport, listMetaReports, subscribeMetaReport } from '@/api/metaReports'

vi.mock('@/api/metaReports', () => ({
  listMetaReports: vi.fn(),
  getMetaReport: vi.fn(),
  subscribeMetaReport: vi.fn(),
}))
vi.mock('@/api/decks', () => ({ createPsoTable: vi.fn() }))

const REPORT = {
  slug: '2026-09-b',
  period: { label: 'Sep 16–30, 2026', publishLabel: 'Oct 16, 2026' },
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
  },
  cards: {
    available: true,
    rising: [{ name: 'Lightning Bolt', share: 41, change: 7.4, winRate: 55, trend: [51, 53, 55] }],
    falling: [{ name: 'Cave Trolls', share: 15, change: -6.2, winRate: 48, trend: [54, 48] }],
    sleeper: { name: 'Sling Pixies', winRate: 58.9, share: 6, games: 212 },
  },
  tournaments: {
    events: [{ name: 'Explorer Columbus', folder: 'explorer-columbus', date: '2026-09-27', players: 18, winnerAvatar: 'Pathfinder', winnerElements: 'Air / Earth' }],
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
      { slug: '2026-09-b', label: 'Sep 16–30, 2026', publishLabel: 'Oct 16, 2026' },
      { slug: '2026-09-a', label: 'Sep 1–15, 2026', publishLabel: 'Oct 1, 2026' },
    ] })
    getMetaReport.mockResolvedValue(REPORT)
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

  it('signs up for email', async () => {
    subscribeMetaReport.mockResolvedValue({ status: 'confirm_sent' })
    renderPage()
    await screen.findByText('Pathfinder is the best deck nobody plays.')
    await userEvent.type(screen.getByLabelText('Email address'), 'fan@example.com')
    await userEvent.click(screen.getByRole('button', { name: 'Sign up' }))
    expect(subscribeMetaReport).toHaveBeenCalledWith('fan@example.com')
    expect(await screen.findByText(/check your inbox/i)).toBeInTheDocument()
  })

  it('explains when nothing is published yet', async () => {
    listMetaReports.mockResolvedValue({ reports: [] })
    renderPage()
    expect(await screen.findByText(/first Meta Report hasn/)).toBeInTheDocument()
  })
})
