import { describe, it, expect } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { Routes, Route, useParams } from 'react-router-dom'
import { renderWithRouter } from '@/test/test-utils'
import BracketSwitcher from '../BracketSwitcher'

const BRACKETS = [
  { slug: 'limited-s3', name: 'Limited Season 3 Top 8', status: 'published', format: 'limited' },
  { slug: 'gothic-s8', name: 'Gothic Season 8 Post Season Bracket', status: 'complete', format: 'constructed', set_name: 'Gothic' },
  { slug: 'gothic-s7', name: 'Gothic Season 7 Post Season Bracket', status: 'complete', format: 'constructed', set_name: 'Gothic' },
]

function Page() {
  const { slug } = useParams()
  return (
    <>
      <p data-testid="slug">{slug}</p>
      <BracketSwitcher brackets={BRACKETS} currentSlug={slug} />
    </>
  )
}

function renderAt(slug) {
  return renderWithRouter(
    <Routes>
      <Route path="/brackets/:slug" element={<Page />} />
    </Routes>,
    { route: `/brackets/${slug}` },
  )
}

describe('BracketSwitcher formats', () => {
  it('lists only the brackets of the format on screen', () => {
    renderAt('gothic-s8')
    expect(screen.getByRole('button', { name: /Constructed/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('link', { name: /Gothic Season 7/ })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Limited Season 3/ })).not.toBeInTheDocument()
  })

  it('switches to the live Limited bracket', () => {
    renderAt('gothic-s8')
    fireEvent.click(screen.getByRole('button', { name: /Limited/ }))
    expect(screen.getByTestId('slug')).toHaveTextContent('limited-s3')
    expect(screen.getByRole('button', { name: /Limited/ })).toHaveAttribute('aria-pressed', 'true')
  })

  it('always offers both formats, even before a Limited bracket exists', () => {
    renderWithRouter(<BracketSwitcher brackets={BRACKETS.slice(1)} currentSlug="gothic-s8" />)
    expect(screen.getByRole('group', { name: 'Format' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Limited/ })).toBeInTheDocument()
  })
})

const WITH_COMMUNITY = [
  ...BRACKETS,
  { slug: 'friday-draft', name: 'Friday Draft', status: 'published', format: 'limited', kind: 'community' },
  { slug: 'store-night', name: 'Store Night', status: 'published', format: 'constructed', kind: 'community' },
]

function CommunityPage() {
  const { slug } = useParams()
  return (
    <>
      <p data-testid="slug">{slug}</p>
      <BracketSwitcher brackets={WITH_COMMUNITY} currentSlug={slug} />
    </>
  )
}

function renderCommunityAt(slug, props = {}) {
  return renderWithRouter(
    <Routes>
      <Route path="/brackets/:slug" element={<CommunityPage {...props} />} />
    </Routes>,
    { route: `/brackets/${slug}` },
  )
}

describe('BracketSwitcher community brackets', () => {
  it('keeps community brackets apart from the season top cut', () => {
    renderCommunityAt('gothic-s8')
    expect(screen.getByRole('button', { name: /Season top cut/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByRole('link', { name: /Store Night/ })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Community/ }))
    expect(screen.getByTestId('slug')).toHaveTextContent('store-night')
    expect(screen.getByRole('button', { name: /Community/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByRole('link', { name: /Gothic Season 7/ })).not.toBeInTheDocument()
  })

  it('switching format lands on the top cut, not a community bracket', () => {
    renderCommunityAt('store-night')
    fireEvent.click(screen.getByRole('button', { name: /Limited/ }))
    expect(screen.getByTestId('slug')).toHaveTextContent('limited-s3')
  })

  it('offers organizers a way to create one', () => {
    renderWithRouter(<BracketSwitcher brackets={BRACKETS} currentSlug="gothic-s8" canOrganize />)
    expect(screen.getByRole('link', { name: /Create a bracket/ })).toHaveAttribute('href', '/brackets/manage')
  })

  it('shows nobody else the create link', () => {
    renderWithRouter(<BracketSwitcher brackets={BRACKETS} currentSlug="gothic-s8" />)
    expect(screen.queryByRole('link', { name: /Create a bracket/ })).not.toBeInTheDocument()
  })
})
