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
      rumble: { voice: 3, no_voice: 1 },
    },
    days: [
      { date: '2026-09-21', ranked: { voice: 40, no_voice: 50 }, testing: { voice: 2, no_voice: 20 } },
      { date: '2026-09-22', ranked: { voice: 56, no_voice: 46 }, testing: { voice: 5, no_voice: 19 }, rumble: { voice: 3, no_voice: 1 } },
    ],
  })),
}))

describe('VoiceStatsCard', () => {
  it('shows season totals for every queue with the voice share', async () => {
    renderWithRouter(<VoiceStatsCard />)
    expect(await screen.findByRole('cell', { name: 'Ranked' })).toBeInTheDocument()
    for (const label of ['Casual', 'Rumble (Omens)', 'Rumble', 'Limited', 'Total']) {
      expect(screen.getByRole('cell', { name: label })).toBeInTheDocument()
    }
    expect(screen.getByText('50%')).toBeInTheDocument() // ranked
    expect(screen.getByText('15%')).toBeInTheDocument() // casual
    expect(screen.getByText('75%')).toBeInTheDocument() // rumble
    expect(screen.getByText('44%')).toBeInTheDocument() // total: 106 of 242
    expect(screen.getAllByText('--')).toHaveLength(2) // queues with no games yet
  })

  it('switches the chart queue filter', async () => {
    renderWithRouter(<VoiceStatsCard />)
    const rumble = await screen.findByRole('button', { name: 'Rumble' })
    expect(screen.getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(rumble)
    expect(rumble).toHaveAttribute('aria-pressed', 'true')
  })
})
