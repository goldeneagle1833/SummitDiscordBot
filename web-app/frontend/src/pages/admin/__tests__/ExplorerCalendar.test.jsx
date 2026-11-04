import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, renderWithRouter, userEvent } from '@/test/test-utils'

vi.mock('@/api/explorerApplications', () => ({ getApplications: vi.fn() }))

import { getApplications } from '@/api/explorerApplications'
import ExplorerCalendar from '../ExplorerCalendar'

const row = (s, rank = 1) => ({ start_date: s, end_date: s, choice_rank: rank, confidence: 'high' })
const apps = [
  { id: 1, lgs_name: 'Columbus Games', city: 'Columbus', state: 'Ohio', latitude: 39.96, longitude: -83.0, status: 'approved', dates: [row('2027-04-10')] },
  { id: 2, lgs_name: 'Dayton Cards', city: 'Dayton', state: 'Ohio', latitude: 39.76, longitude: -84.19, status: 'pending', dates: [row('2027-04-11')] },
  { id: 3, lgs_name: 'Mile High', city: 'Denver', state: 'Colorado', latitude: 39.74, longitude: -104.99, status: 'rejected', dates: [row('2027-04-10')] },
  { id: 4, lgs_name: 'No Dates', status: 'pending', dates: [], dates_need_check: true },
]

describe('ExplorerCalendar', () => {
  beforeEach(() => getApplications.mockResolvedValue({ applications: apps }))

  it('opens on the month grid and shows a day on tap', async () => {
    const user = userEvent.setup()
    renderWithRouter(<ExplorerCalendar />)
    const day = await screen.findByRole('button', { name: /2027-04-10: 1 event, competing/ })
    await user.click(day)
    expect(screen.getByText('Saturday, April 10')).toBeInTheDocument()
    expect(screen.getByText(/Competing events within 100 miles/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /2027-04-11: 1 event, competing/ })).toBeInTheDocument()
  })

  it('shows weekends and flags competing events', async () => {
    const user = userEvent.setup()
    renderWithRouter(<ExplorerCalendar />)
    await user.click(await screen.findByRole('button', { name: 'Weekend list' }))
    expect(await screen.findByText('Columbus Games')).toBeInTheDocument()
    expect(screen.getByText('Dayton Cards')).toBeInTheDocument()
    expect(screen.getByText(/Competing: \d+ mi apart/)).toBeInTheDocument()
    // Rejected is hidden by default.
    expect(screen.queryByText('Mile High')).toBeNull()
  })

  it('approved only drops the clash', async () => {
    const user = userEvent.setup()
    renderWithRouter(<ExplorerCalendar />)
    await user.click(await screen.findByRole('button', { name: 'Weekend list' }))
    await screen.findByText('Columbus Games')
    await user.click(screen.getByLabelText('Approved only'))
    expect(screen.queryByText('Dayton Cards')).toBeNull()
    expect(screen.queryByText(/Competing:/)).toBeNull()
  })

  it('can narrow to problem weekends', async () => {
    const user = userEvent.setup()
    renderWithRouter(<ExplorerCalendar />)
    await user.click(await screen.findByRole('button', { name: 'Weekend list' }))
    await screen.findByText('Columbus Games')
    await user.click(screen.getByLabelText('Only competing or busy weekends'))
    expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(1)
  })
})
