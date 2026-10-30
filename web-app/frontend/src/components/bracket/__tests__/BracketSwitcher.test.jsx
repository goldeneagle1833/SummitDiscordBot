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

  it('shows no format switch without a Limited bracket', () => {
    renderWithRouter(<BracketSwitcher brackets={BRACKETS.slice(1)} currentSlug="gothic-s8" />)
    expect(screen.queryByRole('group', { name: 'Format' })).not.toBeInTheDocument()
  })

  it('gives the underdog bracket its own tab, apart from the top cut', () => {
    const brackets = [
      { slug: 's8-underdog', name: 'Season 8 Underdog Bracket', status: 'published', format: 'underdog' },
      ...BRACKETS.slice(1),
    ]
    renderWithRouter(<BracketSwitcher brackets={brackets} currentSlug="gothic-s8" />)
    expect(screen.getByRole('button', { name: /Underdog/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Limited/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Underdog Bracket/ })).not.toBeInTheDocument()
  })
})
