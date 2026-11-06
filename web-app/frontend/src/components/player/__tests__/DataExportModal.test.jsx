import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import DataExportModal from '../DataExportModal'
import { downloadOwnData } from '@/api/players'

vi.mock('@/api/players', () => ({
  downloadOwnData: vi.fn(),
}))

describe('DataExportModal', () => {
  beforeEach(() => {
    downloadOwnData.mockReset()
    URL.createObjectURL = vi.fn(() => 'blob:x')
    URL.revokeObjectURL = vi.fn()
  })

  it('downloads the zip for this player', async () => {
    downloadOwnData.mockResolvedValue({ blob: new Blob(['zip']), filename: 'sorcerers-summit-data-2026-11-06.zip' })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    renderWithRouter(<DataExportModal playerId="100" onClose={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'Download my data' }))
    await waitFor(() => expect(screen.getByText('Your download has started.')).toBeInTheDocument())
    expect(downloadOwnData).toHaveBeenCalledWith('100')
    expect(click).toHaveBeenCalled()
    click.mockRestore()
  })

  it('shows the error when the export fails', async () => {
    downloadOwnData.mockRejectedValue(new Error('You can only export your own data'))
    renderWithRouter(<DataExportModal playerId="100" onClose={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'Download my data' }))
    await waitFor(() => expect(screen.getByText('You can only export your own data')).toBeInTheDocument())
  })
})
