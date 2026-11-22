import { describe, it, expect, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import NavPicksSection, { countNavPicks } from '../NavPicksSection'
import { get } from '@/api/client'

vi.mock('@/api/client', () => ({ get: vi.fn() }))

describe('countNavPicks', () => {
  it('counts each page once per person and applies renames', () => {
    const { rows, people, onlyDefaults } = countNavPicks([
      ['Feedback', 'Community', '__v2'],
      ['Feedback', 'Card Win Rates', 'Popular Cards', '__v2'],
      ['Avatars', '__v2'],
      // old save from before the __v2 change: locked links are dropped
      ['Top 8 Decks', 'Feedback'],
    ])
    const byLabel = Object.fromEntries(rows.map((r) => [r.label, r.count]))
    expect(people).toBe(4)
    expect(byLabel.Feedback).toBe(3)
    expect(byLabel['Card Stats']).toBe(1)
    expect(byLabel['Top 8 Decks']).toBe(0)
    expect(byLabel.Avatars).toBeUndefined()
    expect(onlyDefaults).toBe(1)
    expect(rows[0].label).toBe('Feedback')
  })
})

describe('NavPicksSection', () => {
  it('shows the ranked list', async () => {
    get.mockResolvedValue({ saves: [['Community', '__v2'], ['Community', 'Help', '__v2']], profiles: 9 })
    renderWithRouter(<NavPicksSection />)
    await waitFor(() => expect(screen.getByText('People who customized')).toBeInTheDocument())
    expect(screen.getAllByText('Community').length).toBeGreaterThan(1)
    expect(screen.getByText('1.5')).toBeInTheDocument()
  })
})
