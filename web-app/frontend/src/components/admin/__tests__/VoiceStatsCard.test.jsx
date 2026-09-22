import { describe, it, expect, vi } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import { VoiceStatsCard } from '../DashboardSection'

vi.mock('@/api/client', () => ({
  get: vi.fn(() => Promise.resolve({
    success: true,
    queues: {
      ranked: { voice: 96, no_voice: 96 },
      testing: { voice: 7, no_voice: 39 },
    },
    days: [
      { date: '2026-09-21', ranked: { voice: 40, no_voice: 50 }, testing: { voice: 2, no_voice: 20 } },
      { date: '2026-09-22', ranked: { voice: 56, no_voice: 46 }, testing: { voice: 5, no_voice: 19 } },
    ],
  })),
}))

describe('VoiceStatsCard', () => {
  it('shows season totals per queue with the voice share', async () => {
    renderWithRouter(<VoiceStatsCard />)
    expect(await screen.findByText('Ranked')).toBeInTheDocument()
    expect(screen.getByText('50%')).toBeInTheDocument()
    expect(screen.getByText('15%')).toBeInTheDocument()
    expect(screen.getByText('43%')).toBeInTheDocument()
  })

  it('switches the chart queue filter', async () => {
    renderWithRouter(<VoiceStatsCard />)
    const casual = await screen.findByRole('button', { name: 'Casual' })
    expect(screen.getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(casual)
    expect(casual).toHaveAttribute('aria-pressed', 'true')
  })
})
