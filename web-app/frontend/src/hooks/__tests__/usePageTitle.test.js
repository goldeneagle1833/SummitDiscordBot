import { describe, it, expect, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import usePageTitle from '../usePageTitle'

describe('usePageTitle', () => {
  afterEach(() => {
    document.title = ''
  })

  it('sets document title with suffix', () => {
    renderHook(() => usePageTitle('About'))
    expect(document.title).toBe('About | Sorcerers Summit')
  })

  it('sets default title when given empty string', () => {
    renderHook(() => usePageTitle(''))
    expect(document.title).toBe('Sorcerers Summit')
  })

  it('sets default title when given null', () => {
    renderHook(() => usePageTitle(null))
    expect(document.title).toBe('Sorcerers Summit')
  })

  it('updates title when value changes', () => {
    const { rerender } = renderHook(({ title }) => usePageTitle(title), {
      initialProps: { title: 'Page A' },
    })
    expect(document.title).toBe('Page A | Sorcerers Summit')

    rerender({ title: 'Page B' })
    expect(document.title).toBe('Page B | Sorcerers Summit')
  })
})
