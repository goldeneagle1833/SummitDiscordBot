import { describe, it, expect } from 'vitest'
import { unwrapLoginNext } from '../Login'

describe('unwrapLoginNext', () => {
  const origin = window.location.origin

  it('keeps an ordinary page', () => {
    expect(unwrapLoginNext(`${origin}/player/123`)).toBe(`${origin}/player/123`)
  })

  it('peels nested login pages off', () => {
    const inner = `${origin}/deck-rec/abc`
    const once = `${origin}/login?next=${encodeURIComponent(inner)}`
    const twice = `${origin}/login?next=${encodeURIComponent(once)}`
    expect(unwrapLoginNext(twice)).toBe(inner)
  })

  it('returns null for a login page with no next', () => {
    expect(unwrapLoginNext(`${origin}/login`)).toBeNull()
    expect(unwrapLoginNext(null)).toBeNull()
  })
})
