import { describe, it, expect } from 'vitest'
import {
  dismissArrival, getArrivals, isNewSince, mergeSeen, newPageKeys, pageKeyForPath, recordArrival,
} from '../newContent'

describe('pageKeyForPath', () => {
  it('matches a page and its sub pages', () => {
    expect(pageKeyForPath('/top-8')).toBe('top-8')
    expect(pageKeyForPath('/top-8/SomeEvent')).toBe('top-8')
    expect(pageKeyForPath('/articles/my-guide')).toBe('articles')
  })
  it('does not match look-alike paths or other pages', () => {
    expect(pageKeyForPath('/avatar/Sparkmage')).toBe(null)
    expect(pageKeyForPath('/top-8x')).toBe(null)
    expect(pageKeyForPath('/elo')).toBe(null)
    expect(pageKeyForPath('')).toBe(null)
  })
})

describe('newPageKeys', () => {
  const latest = { 'top-8': '2026-11-08T10:00:00Z', store: '2026-11-05T10:00:00Z' }
  it('flags pages never seen', () => {
    expect([...newPageKeys(latest, {})].sort()).toEqual(['store', 'top-8'])
  })
  it('clears pages seen at or after the newest content', () => {
    const seen = { 'top-8': '2026-11-08T10:00:00Z', store: '2026-11-04T00:00:00Z' }
    expect([...newPageKeys(latest, seen)]).toEqual(['store'])
  })
  it('handles missing data', () => {
    expect(newPageKeys(null, null).size).toBe(0)
  })
})

describe('mergeSeen', () => {
  it('keeps the newer time per page', () => {
    const a = { 'top-8': '2026-11-08T10:00:00Z', store: '2026-11-01T00:00:00Z' }
    const b = { 'top-8': '2026-11-01T00:00:00Z', store: '2026-11-06T00:00:00Z', articles: '2026-11-02T00:00:00Z' }
    expect(mergeSeen(a, b)).toEqual({
      'top-8': '2026-11-08T10:00:00Z', store: '2026-11-06T00:00:00Z', articles: '2026-11-02T00:00:00Z',
    })
  })
})

describe('isNewSince', () => {
  const now = Date.parse('2026-11-09T12:00:00Z')
  it('compares with the last visit', () => {
    expect(isNewSince('2026-11-08T00:00:00Z', '2026-11-07T00:00:00Z', now)).toBe(true)
    expect(isNewSince('2026-11-06T00:00:00Z', '2026-11-07T00:00:00Z', now)).toBe(false)
  })
  it('never visited: only the last 14 days count', () => {
    expect(isNewSince('2026-11-01T00:00:00Z', null, now)).toBe(true)
    expect(isNewSince('2026-10-20T00:00:00Z', null, now)).toBe(false)
  })
  it('ignores missing times', () => {
    expect(isNewSince(null, null, now)).toBe(false)
  })
})

describe('arrivals', () => {
  it('records and dismisses a page arrival', () => {
    recordArrival('store', { since: '2026-11-01T00:00:00Z', note: { text: 'New in the store: Mat', link: '/store' }, at: 'x' })
    expect(getArrivals().store.note.text).toBe('New in the store: Mat')
    expect(getArrivals().store.dismissed).toBe(false)
    dismissArrival('store')
    expect(getArrivals().store.dismissed).toBe(true)
    expect(getArrivals().store.since).toBe('2026-11-01T00:00:00Z')
  })
})
