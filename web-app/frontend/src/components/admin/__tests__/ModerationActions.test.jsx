import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, render, userEvent } from '@/test/test-utils'

vi.mock('@/api/client', async () => {
  const actual = await vi.importActual('@/api/client')
  return { ...actual, post: vi.fn() }
})

import { post } from '@/api/client'
import ModerationActions from '../ModerationActions'

const PROPS = {
  userId: '222222222222222222',
  userName: 'Opponent',
  canModerate: true,
  moderation: null,
  sourceKind: 'report',
  sourceRef: 5,
  defaultReason: 'Player report #5: toxic',
}

describe('ModerationActions', () => {
  beforeEach(() => { post.mockReset() })

  it('asks for confirmation before timing out, then shows the result', async () => {
    post.mockResolvedValue({
      success: true,
      moderation: { action: 'timeout', duration_minutes: 10080, by_name: 'Bruce', via: 'web', created_at: '2026-10-31 20:00:00' },
    })
    const user = userEvent.setup()
    render(<ModerationActions {...PROPS} />)

    await user.click(screen.getByRole('button', { name: 'Timeout' }))
    expect(post).not.toHaveBeenCalled()
    expect(screen.getByRole('dialog')).toHaveTextContent('Time out Opponent?')

    await user.selectOptions(screen.getByRole('combobox'), '10080')
    await user.click(screen.getByRole('button', { name: 'Confirm timeout' }))

    expect(post).toHaveBeenCalledWith('/api/admin/moderation', expect.objectContaining({
      action: 'timeout', user_id: PROPS.userId, minutes: 10080, confirm: true,
      reason: 'Player report #5: toxic', source_kind: 'report', source_ref: 5,
    }))
    expect(await screen.findByText(/Timed out 1 week by Bruce/)).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('cancel does nothing', async () => {
    const user = userEvent.setup()
    render(<ModerationActions {...PROPS} />)
    await user.click(screen.getByRole('button', { name: 'Ban' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(post).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('keeps the dialog open and shows Discord errors', async () => {
    post.mockRejectedValue(new Error('Discord refused. The bot needs Ban Members'))
    const user = userEvent.setup()
    render(<ModerationActions {...PROPS} />)
    await user.click(screen.getByRole('button', { name: 'Ban' }))
    await user.click(screen.getByRole('button', { name: 'Confirm ban' }))
    expect(await screen.findByText(/Ban Members/)).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('has no buttons for accounts without Discord', () => {
    render(<ModerationActions {...PROPS} userId="google_1" canModerate={false} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.getByText('No Discord account')).toBeInTheDocument()
  })
})

describe('ModerationActions pairing block', () => {
  beforeEach(() => { post.mockReset() })

  it('sends the duration and a reason the player will see', async () => {
    post.mockResolvedValue({ success: true, moderation: { action: 'pairing_block', duration_label: '72 hours', by_name: 'Bruce', via: 'web', created_at: '2026-10-31 20:00:00' } })
    const user = userEvent.setup()
    render(<ModerationActions {...PROPS} playerReason="Reported after a match: Rude" />)
    await user.click(screen.getByRole('button', { name: 'Pairing Block' }))
    expect(screen.getByRole('dialog')).toHaveTextContent('sent to the player')
    expect(screen.getByRole('textbox')).toHaveValue('Reported after a match: Rude')
    await user.selectOptions(screen.getByRole('combobox'), '72h')
    await user.click(screen.getByRole('button', { name: 'Confirm pairing block' }))
    expect(post).toHaveBeenCalledWith('/api/admin/moderation', expect.objectContaining({
      action: 'pairing_block', duration: '72h', reason: 'Reported after a match: Rude', confirm: true,
    }))
    expect(await screen.findByText(/Pairing block 72 hours by Bruce/)).toBeInTheDocument()
  })

  it('needs a reason', async () => {
    const user = userEvent.setup()
    render(<ModerationActions {...PROPS} playerReason="" />)
    await user.click(screen.getByRole('button', { name: 'Pairing Block' }))
    expect(screen.getByRole('button', { name: 'Confirm pairing block' })).toBeDisabled()
  })
})
