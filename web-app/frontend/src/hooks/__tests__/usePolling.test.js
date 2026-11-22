import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import usePolling from '../usePolling'

let visibility = 'visible'
function setVisibility(v) {
  visibility = v
  document.dispatchEvent(new Event('visibilitychange'))
}

describe('usePolling', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    visibility = 'visible'
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => visibility })
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('runs now and then on the interval while visible', () => {
    const fn = vi.fn()
    renderHook(() => usePolling(fn, 60000))
    expect(fn).toHaveBeenCalledTimes(1)
    act(() => { vi.advanceTimersByTime(60000) })
    expect(fn).toHaveBeenCalledTimes(2)
    act(() => { vi.advanceTimersByTime(120000) })
    expect(fn).toHaveBeenCalledTimes(4)
  })

  it('stops while the tab is hidden and catches up when shown', () => {
    const fn = vi.fn()
    renderHook(() => usePolling(fn, 60000))
    act(() => { setVisibility('hidden') })
    act(() => { vi.advanceTimersByTime(30 * 60000) })
    expect(fn).toHaveBeenCalledTimes(1)
    act(() => { setVisibility('visible') })
    expect(fn).toHaveBeenCalledTimes(2)
    act(() => { vi.advanceTimersByTime(60000) })
    expect(fn).toHaveBeenCalledTimes(3)
  })

  it('does not double up when shown again quickly', () => {
    const fn = vi.fn()
    renderHook(() => usePolling(fn, 60000))
    act(() => { setVisibility('hidden') })
    act(() => { vi.advanceTimersByTime(5000) })
    act(() => { setVisibility('visible') })
    expect(fn).toHaveBeenCalledTimes(1)
  })

  it('slows down when idle and wakes on activity', () => {
    const fn = vi.fn()
    renderHook(() => usePolling(fn, 60000, { idleMs: 10 * 60000, idleIntervalMs: 5 * 60000 }))
    act(() => { vi.advanceTimersByTime(10 * 60000) }) // 10 active ticks
    expect(fn).toHaveBeenCalledTimes(11)
    act(() => { vi.advanceTimersByTime(7 * 60000) }) // idle: next one 5 min later
    expect(fn).toHaveBeenCalledTimes(12)
    act(() => { window.dispatchEvent(new Event('keydown')) }) // overdue: runs now
    expect(fn).toHaveBeenCalledTimes(13)
    act(() => { vi.advanceTimersByTime(60000) }) // back to every minute
    expect(fn).toHaveBeenCalledTimes(14)
  })

  it('stops entirely when idle if idleIntervalMs is 0', () => {
    const fn = vi.fn()
    renderHook(() => usePolling(fn, 60000, { idleMs: 15 * 60000, idleIntervalMs: 0 }))
    act(() => { vi.advanceTimersByTime(60 * 60000) })
    expect(fn).toHaveBeenCalledTimes(16)
    act(() => { window.dispatchEvent(new Event('pointerdown')) })
    expect(fn).toHaveBeenCalledTimes(17)
  })

  it('does nothing when disabled', () => {
    const fn = vi.fn()
    renderHook(() => usePolling(fn, 60000, { enabled: false }))
    act(() => { vi.advanceTimersByTime(600000) })
    expect(fn).not.toHaveBeenCalled()
  })
})
