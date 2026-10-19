import { describe, it, expect } from 'vitest'
import { europeFromTimeZone } from '../region'

describe('europeFromTimeZone', () => {
  it('treats Europe/* time zones as Europe', () => {
    expect(europeFromTimeZone('Europe/Berlin')).toBe(true)
    expect(europeFromTimeZone('America/New_York')).toBe(false)
    expect(europeFromTimeZone(undefined)).toBe(false)
  })
})
