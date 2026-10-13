import { describe, it, expect } from 'vitest'
import { render, screen } from '@/test/test-utils'
import LinkifiedText from '../LinkifiedText'

describe('LinkifiedText', () => {
  it('links urls and leaves sentence punctuation outside', () => {
    render(<p><LinkifiedText text="See https://a.com/x, and www.b.com." /></p>)
    expect(screen.getByRole('link', { name: 'https://a.com/x' })).toHaveAttribute('href', 'https://a.com/x')
    expect(screen.getByRole('link', { name: 'www.b.com' })).toHaveAttribute('href', 'https://www.b.com')
    expect(screen.getByText(/and/).textContent).toBe('See https://a.com/x, and www.b.com.')
  })

  it('renders plain text untouched', () => {
    render(<p data-testid="t"><LinkifiedText text="No links here" /></p>)
    expect(screen.getByTestId('t').textContent).toBe('No links here')
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
})
