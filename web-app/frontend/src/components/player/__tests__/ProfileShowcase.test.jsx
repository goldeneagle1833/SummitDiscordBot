import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { FavoriteCardBox, ProfileBio, RivalBox } from '../ProfileShowcase'

const wrap = (ui) => render(<MemoryRouter>{ui}</MemoryRouter>)

describe('profile showcase', () => {
  it('shows visitors nothing at all for empty boxes and no bio', () => {
    const { container } = wrap(
      <>
        <ProfileBio bio={null} isOwner={false} />
        <FavoriteCardBox card={null} isOwner={false} />
        <RivalBox rival={null} isOwner={false} />
      </>
    )
    expect(container.innerHTML).toBe('')
  })

  it('prompts the owner to fill each one in', () => {
    wrap(
      <>
        <ProfileBio bio={null} isOwner />
        <FavoriteCardBox card={null} isOwner />
        <RivalBox rival={null} isOwner />
      </>
    )
    expect(screen.getByText('+ Add a short description')).toBeTruthy()
    expect(screen.getByText('Pick a card')).toBeTruthy()
    expect(screen.getByText('Pick a rival')).toBeTruthy()
  })

  it('shows filled boxes to visitors without edit buttons', () => {
    wrap(
      <>
        <ProfileBio bio="Earth player from Ohio" isOwner={false} />
        <FavoriteCardBox card={{ name: 'Pudge Butcher', image: 'p.png' }} isOwner={false} />
        <RivalBox rival={{ id: '3', name: 'Rob', avatar_url: null, wins: 5, losses: 3 }} isOwner={false} />
      </>
    )
    expect(screen.getByText('Earth player from Ohio')).toBeTruthy()
    expect(screen.getByText('Pudge Butcher')).toBeTruthy()
    expect(screen.getByText('Rob').closest('a').getAttribute('href')).toBe('/player/3')
    expect(screen.queryByText('Edit')).toBeNull()
  })
})
