import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { render } from '@/test/test-utils'
import DisplayNameBanner from '../DisplayNameBanner'
import { setDisplayName } from '@/api/players'

vi.mock('@/api/players', () => ({
  setDisplayName: vi.fn(),
}))

describe('DisplayNameBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
  })

  it('offers a banner until a name is chosen', () => {
    render(<DisplayNameBanner playerId="1" defaultName="schotti" hasCustomName={false} />)
    expect(screen.getByText('Set Name')).toBeInTheDocument()
    expect(screen.queryByText('Change display name')).not.toBeInTheDocument()
  })

  it('still lets the owner change a name they already chose', async () => {
    setDisplayName.mockResolvedValue({ success: true, display_name: 'Phil' })
    const onNameChange = vi.fn()
    render(
      <DisplayNameBanner playerId="1" defaultName="schotti" hasCustomName={true} onNameChange={onNameChange} />
    )

    await userEvent.click(screen.getByText('Change display name'))
    const input = screen.getByPlaceholderText('Enter your display name')
    await userEvent.clear(input)
    await userEvent.type(input, 'Phil')
    await userEvent.click(screen.getByText('Save Name'))

    await waitFor(() => expect(setDisplayName).toHaveBeenCalledWith('1', 'Phil'))
    expect(onNameChange).toHaveBeenCalledWith('Phil')
  })

  it('keeps the change link even after the first-time banner was dismissed', () => {
    sessionStorage.setItem('display_name_banner_dismissed', '1')
    render(<DisplayNameBanner playerId="1" defaultName="Phil" hasCustomName={true} />)
    expect(screen.getByText('Change display name')).toBeInTheDocument()
  })
})
