import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DecayTag } from '../DecayTag'

describe('DecayTag', () => {
  it('shows points lost to inactivity', () => {
    render(<DecayTag decay={30} />)
    expect(screen.getByTestId('decay-tag')).toHaveTextContent('-30 idle')
  })

  it('warns a day or two before decay starts', () => {
    render(<DecayTag decay={0} inDays={2} />)
    expect(screen.getByTestId('decay-soon-tag')).toHaveTextContent('decays in 2d')
  })

  it('renders nothing for an active entry', () => {
    const { container } = render(<DecayTag decay={0} inDays={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})
