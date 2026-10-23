import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import { AvatarHonourBadge, AvatarHonoursSection, resetAvatarHonoursCache } from '../AvatarHonours'

vi.mock('@/api/avatarHonours', () => ({ getAvatarHonours: vi.fn() }))

const HONOURS = [
  { season: 'Gothic Season 8', avatar: 'Druid', place: 3, label: '3rd Druid', title: 'Gothic Season 8 3rd Druid', wins: 9, losses: 4 },
  { season: 'Gothic Season 7', avatar: 'Imposter', place: 1, label: 'Top Imposter', title: 'Gothic Season 7 Top Imposter', wins: 14, losses: 2, elo: 1712 },
  { season: 'Gothic Season 7', avatar: 'Seer', place: 2, label: '2nd Seer', title: 'Gothic Season 7 2nd Seer', wins: 11, losses: 3 },
]

describe('AvatarHonours', () => {
  beforeEach(() => resetAvatarHonoursCache())

  it('shows the best honour on the badge with a count of the rest', () => {
    renderWithRouter(<AvatarHonourBadge honours={HONOURS} />)
    expect(screen.getByText('Top Imposter')).toBeInTheDocument()
    expect(screen.getByText('Gothic Season 7')).toBeInTheDocument()
    expect(screen.getByText('+2')).toBeInTheDocument()
  })

  it('renders nothing without honours', () => {
    const { container } = renderWithRouter(<AvatarHonourBadge honours={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('groups the section by season', () => {
    renderWithRouter(<AvatarHonoursSection honours={HONOURS} />)
    expect(screen.getByText('Gothic Season 8')).toBeInTheDocument()
    expect(screen.getByText('Gothic Season 7')).toBeInTheDocument()
    expect(screen.getByText('2nd Seer')).toBeInTheDocument()
    expect(screen.getByText('1712 Elo · 14-2')).toBeInTheDocument()
  })
})
