import { describe, it, expect, vi } from 'vitest'
import { screen, renderWithRouter, userEvent } from '@/test/test-utils'
import Button from '../Button'

describe('Button', () => {
  it('renders as a <button> by default', () => {
    renderWithRouter(<Button>Click me</Button>)
    const btn = screen.getByRole('button', { name: /click me/i })
    expect(btn).toBeInTheDocument()
    expect(btn.tagName).toBe('BUTTON')
  })

  it('renders as a <Link> when "to" prop is provided', () => {
    renderWithRouter(<Button to="/about">About</Button>)
    const link = screen.getByRole('link', { name: /about/i })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/about')
  })

  it('renders as an <a> when "href" prop is provided', () => {
    renderWithRouter(<Button href="https://example.com">External</Button>)
    const link = screen.getByRole('link', { name: /external/i })
    expect(link).toHaveAttribute('href', 'https://example.com')
  })

  it('applies primary variant classes by default', () => {
    renderWithRouter(<Button>Primary</Button>)
    const btn = screen.getByRole('button', { name: /primary/i })
    expect(btn.className).toContain('bg-primary')
  })

  it('applies danger variant classes', () => {
    renderWithRouter(<Button variant="danger">Delete</Button>)
    const btn = screen.getByRole('button', { name: /delete/i })
    expect(btn.className).toContain('bg-accent-red')
  })

  it('applies ghost variant classes', () => {
    renderWithRouter(<Button variant="ghost">Ghost</Button>)
    const btn = screen.getByRole('button', { name: /ghost/i })
    expect(btn.className).toContain('bg-transparent')
  })

  it('merges custom className', () => {
    renderWithRouter(<Button className="mt-4">Styled</Button>)
    const btn = screen.getByRole('button', { name: /styled/i })
    expect(btn.className).toContain('mt-4')
  })

  it('forwards the disabled attribute', () => {
    renderWithRouter(<Button disabled>Disabled</Button>)
    const btn = screen.getByRole('button', { name: /disabled/i })
    expect(btn).toBeDisabled()
  })

  it('calls onClick handler when clicked', async () => {
    const user = userEvent.setup()
    const handleClick = vi.fn()
    renderWithRouter(<Button onClick={handleClick}>Go</Button>)
    await user.click(screen.getByRole('button', { name: /go/i }))
    expect(handleClick).toHaveBeenCalledTimes(1)
  })

  it('falls back to primary variant for unknown variant', () => {
    renderWithRouter(<Button variant="nonexistent">Fallback</Button>)
    const btn = screen.getByRole('button', { name: /fallback/i })
    expect(btn.className).toContain('bg-primary')
  })
})
