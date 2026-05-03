import { describe, it, expect } from 'vitest'
import { render, screen } from '@/test/test-utils'
import Badge from '../Badge'

describe('Badge', () => {
  it('renders children text', () => {
    render(<Badge>New</Badge>)
    expect(screen.getByText('New')).toBeInTheDocument()
  })

  it('applies default variant styling', () => {
    render(<Badge>Default</Badge>)
    expect(screen.getByText('Default').className).toContain('bg-bg-elevated')
  })

  it('applies success variant styling', () => {
    render(<Badge variant="success">Win</Badge>)
    expect(screen.getByText('Win').className).toContain('text-accent-green')
  })

  it('applies danger variant styling', () => {
    render(<Badge variant="danger">Loss</Badge>)
    expect(screen.getByText('Loss').className).toContain('text-accent-red')
  })

  it('merges custom className', () => {
    render(<Badge className="ml-2">Tag</Badge>)
    expect(screen.getByText('Tag').className).toContain('ml-2')
  })
})
