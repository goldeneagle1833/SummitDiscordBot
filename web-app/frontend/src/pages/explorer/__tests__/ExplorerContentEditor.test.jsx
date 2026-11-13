import { describe, it, expect, vi } from 'vitest'
import { screen, renderWithRouter, userEvent } from '@/test/test-utils'

vi.mock('@/api/explorer', () => ({
  fetchSiteContent: vi.fn(),
  saveSiteContent: vi.fn(),
  uploadSiteImages: vi.fn(),
}))

import { fetchSiteContent, saveSiteContent, uploadSiteImages } from '@/api/explorer'
import ExplorerContentEditor from '../ExplorerContentEditor'

describe('Explorer site content editor', () => {
  it('loads the saved text, adds a section and saves', async () => {
    fetchSiteContent.mockResolvedValue({ title: 'The Explorer Series', sections: [] })
    saveSiteContent.mockImplementation(async (c) => c)
    const user = userEvent.setup()
    renderWithRouter(<ExplorerContentEditor />)

    const title = await screen.findByLabelText('Title')
    expect(title).toHaveValue('The Explorer Series')
    await user.clear(title)
    await user.type(title, 'Explorer Series 2027')

    await user.click(screen.getByRole('button', { name: '+ Add section' }))
    await user.type(screen.getByLabelText('Heading'), 'Prizes')
    await user.type(screen.getByLabelText(/^Text/), 'Hand-painted alter')
    uploadSiteImages.mockResolvedValue({ urls: ['/static/uploads/explorer/a.jpg'] })
    const picker = screen.getByLabelText('+ Add pictures')
    await user.upload(picker, new File(['x'], 'photo.jpg', { type: 'image/jpeg' }))
    expect(await screen.findByRole('button', { name: 'Move picture left' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(saveSiteContent).toHaveBeenCalledWith(expect.objectContaining({
      title: 'Explorer Series 2027',
      sections: [{ title: 'Prizes', body: 'Hand-painted alter', images: ['/static/uploads/explorer/a.jpg'], hidden: false }],
    }))
    expect(await screen.findByText(/Saved/)).toBeInTheDocument()
  })
})
