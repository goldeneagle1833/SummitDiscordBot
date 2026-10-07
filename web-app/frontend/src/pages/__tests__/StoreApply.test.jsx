import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, renderWithRouter, userEvent, within } from '@/test/test-utils'

vi.mock('@/api/store', async () => {
  const actual = await vi.importActual('@/api/store')
  return { ...actual, applyForStorefront: vi.fn(), getMyStorefrontApplications: vi.fn(), searchMembers: vi.fn() }
})

import { applyForStorefront, getMyStorefrontApplications, searchMembers } from '@/api/store'
import StoreApply from '../StoreApply'

describe('StoreApply page', () => {
  beforeEach(() => vi.clearAllMocks())

  it('needs the agreement before sending, then sends the form', async () => {
    getMyStorefrontApplications.mockResolvedValue({ applications: [] })
    applyForStorefront.mockResolvedValue({ ok: true })
    renderWithRouter(<StoreApply />)
    await userEvent.type(await screen.findByLabelText('Storefront name'), 'Explorer Store')
    await userEvent.type(screen.getByLabelText('Contact email'), 'shop@explorer.test')
    await userEvent.type(screen.getByLabelText(/About your group/), 'Weekly league')
    await userEvent.type(screen.getByLabelText('Shipping'), 'We ship from Ohio')
    const send = screen.getByRole('button', { name: 'Send application' })
    expect(send).toBeDisabled()
    await userEvent.click(screen.getByLabelText('I agree to the storefront agreement'))
    await userEvent.click(send)
    expect(applyForStorefront).toHaveBeenCalledWith({
      name: 'Explorer Store', contact_email: 'shop@explorer.test', website: '',
      description: 'Weekly league', shipping: 'We ship from Ohio', agreed: true, team: [],
    })
    expect(await screen.findByText(/Your application is in/)).toBeInTheDocument()
  })

  it('names managers and shippers from a member search', async () => {
    getMyStorefrontApplications.mockResolvedValue({ applications: [] })
    applyForStorefront.mockResolvedValue({ ok: true })
    searchMembers.mockResolvedValue({ users: [
      { user_id: '601', display_name: 'Mia' },
      { user_id: '602', display_name: 'Sam' },
    ] })
    renderWithRouter(<StoreApply />)
    const search = await screen.findByPlaceholderText('Search Summit members by name')
    await userEvent.type(search, 'mi')
    const mia = await screen.findByText('Mia')
    await userEvent.click(within(mia.closest('li')).getByRole('button', { name: 'Add as manager' }))
    await userEvent.type(search, 'sa')
    const sam = await screen.findByText('Sam')
    await userEvent.click(within(sam.closest('li')).getByRole('button', { name: 'Add as shipper' }))
    expect(searchMembers).toHaveBeenCalledWith('sa')
    expect(screen.getByText('Shipper')).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('Storefront name'), 'VIP')
    await userEvent.type(screen.getByLabelText('Contact email'), 'vip@test.com')
    await userEvent.type(screen.getByLabelText(/About your group/), 'x')
    await userEvent.type(screen.getByLabelText('Shipping'), 'y')
    await userEvent.click(screen.getByLabelText('I agree to the storefront agreement'))
    await userEvent.click(screen.getByRole('button', { name: 'Send application' }))
    expect(applyForStorefront).toHaveBeenCalledWith(expect.objectContaining({
      team: [{ user_id: '601', role: 'manager' }, { user_id: '602', role: 'fulfillment' }],
    }))
  })

  it('hides the form while an application is pending', async () => {
    getMyStorefrontApplications.mockResolvedValue({ applications: [
      { id: 1, name: 'Explorer Store', status: 'pending' },
    ] })
    renderWithRouter(<StoreApply />)
    expect(await screen.findByText('Waiting for review')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Send application' })).not.toBeInTheDocument()
  })

  it('links to an approved storefront', async () => {
    getMyStorefrontApplications.mockResolvedValue({ applications: [
      { id: 1, name: 'Explorer Store', status: 'approved', storefront_slug: 'explorer' },
    ] })
    renderWithRouter(<StoreApply />)
    expect(await screen.findByRole('link', { name: 'View storefront' })).toHaveAttribute('href', '/store?storefront=explorer')
    expect(screen.getByRole('button', { name: 'Send application' })).toBeInTheDocument()
  })
})
