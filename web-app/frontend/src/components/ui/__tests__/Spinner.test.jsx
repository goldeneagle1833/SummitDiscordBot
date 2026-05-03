import { describe, it, expect } from 'vitest'
import { render } from '@/test/test-utils'
import Spinner from '../Spinner'

describe('Spinner', () => {
  it('renders with default md size', () => {
    const { container } = render(<Spinner />)
    const spinner = container.querySelector('.animate-spin')
    expect(spinner).toBeInTheDocument()
    expect(spinner.className).toContain('h-8')
    expect(spinner.className).toContain('w-8')
  })

  it('renders with sm size', () => {
    const { container } = render(<Spinner size="sm" />)
    const spinner = container.querySelector('.animate-spin')
    expect(spinner.className).toContain('h-4')
    expect(spinner.className).toContain('w-4')
  })

  it('renders with lg size', () => {
    const { container } = render(<Spinner size="lg" />)
    const spinner = container.querySelector('.animate-spin')
    expect(spinner.className).toContain('h-12')
    expect(spinner.className).toContain('w-12')
  })

  it('applies custom className to wrapper', () => {
    const { container } = render(<Spinner className="py-20" />)
    const wrapper = container.firstChild
    expect(wrapper.className).toContain('py-20')
  })

  it('falls back to md for unknown size', () => {
    const { container } = render(<Spinner size="xl" />)
    const spinner = container.querySelector('.animate-spin')
    expect(spinner.className).toContain('h-8')
  })
})
