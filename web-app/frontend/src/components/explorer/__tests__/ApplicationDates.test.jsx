import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ApplicationDates, { dateLabel } from '../ApplicationDates'

const row = (over) => ({
  id: 1, start_date: '2027-04-10', end_date: '2027-04-10', precision: 'day',
  confidence: 'high', source: 'parser', raw_text: '4/10/27', confirmed_at: null, ...over,
})

describe('ApplicationDates', () => {
  it('labels days, ranges and unreadable answers', () => {
    expect(dateLabel(row())).toBe('Sat, Apr 10')
    expect(dateLabel(row({ end_date: '2027-04-11' }))).toBe('Apr 10 – Apr 11')
    expect(dateLabel(row({ start_date: null, end_date: null, raw_text: 'TBD' }))).toBe("Couldn't read “TBD”")
  })

  it('confirms with Looks right', async () => {
    const onConfirm = vi.fn()
    render(<ApplicationDates dates={[row({ confidence: 'low', precision: 'week', raw_text: 'mid-June' })]} needsCheck onConfirm={onConfirm} onSave={vi.fn()} />)
    expect(screen.getByText('Needs a check')).toBeInTheDocument()
    expect(screen.getByText('“mid-June”')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Looks right' }))
    expect(onConfirm).toHaveBeenCalled()
  })

  it('saves fixed dates', async () => {
    const onSave = vi.fn().mockResolvedValue(true)
    render(<ApplicationDates dates={[]} onConfirm={vi.fn()} onSave={onSave} />)
    await userEvent.click(screen.getByRole('button', { name: 'Add dates' }))
    await userEvent.type(screen.getByLabelText('Choice 1'), '2027-06-12')
    await userEvent.click(screen.getByRole('button', { name: 'Save dates' }))
    expect(onSave).toHaveBeenCalledWith([{ start: '2027-06-12', end: '2027-06-12' }])
  })

  it('hides Looks right once confirmed', () => {
    render(<ApplicationDates dates={[row({ confirmed_at: 'x', confirmed_by: 'Bruce' })]} onConfirm={vi.fn()} onSave={vi.fn()} />)
    expect(screen.queryByRole('button', { name: 'Looks right' })).toBeNull()
    expect(screen.getByText('Checked by Bruce')).toBeInTheDocument()
  })
})
