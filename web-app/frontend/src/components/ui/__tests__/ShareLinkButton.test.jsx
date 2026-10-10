import { describe, it, expect, vi, afterEach } from 'vitest'
import { fireEvent } from '@testing-library/react'
import { screen, renderWithRouter, waitFor } from '@/test/test-utils'
import ShareLinkButton from '../ShareLinkButton'

describe('ShareLinkButton', () => {
  afterEach(() => vi.restoreAllMocks())

  it('copies the full event URL and confirms', async () => {
    const writeText = vi.fn().mockResolvedValue()
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    renderWithRouter(<ShareLinkButton path="/top-8/My%20Event" />)
    fireEvent.click(screen.getByRole('button', { name: /share/i }))
    await waitFor(() => expect(screen.getByText('Link copied')).toBeInTheDocument())
    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/top-8/My%20Event`)
  })

  it('falls back to a prompt when the clipboard is blocked', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) },
      configurable: true,
    })
    const prompt = vi.spyOn(window, 'prompt').mockImplementation(() => null)
    renderWithRouter(<ShareLinkButton path="/top-8/x" />)
    fireEvent.click(screen.getByRole('button', { name: /share/i }))
    await waitFor(() => expect(prompt).toHaveBeenCalledWith('Copy this link:', `${window.location.origin}/top-8/x`))
  })
})
