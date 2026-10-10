import { describe, it, expect, vi, afterEach } from 'vitest'
import { useState } from 'react'
import { render, screen, fireEvent, act } from '@testing-library/react'
import TimelineControls, { windowDays, tickMs } from '../TimelineControls'

const PLAY_TICK_MS = tickMs('normal')

// 400 days, so all-time Play would step more than one day at a time
const DATES = Array.from({ length: 400 }, (_, i) => new Date(Date.UTC(2025, 0, 1 + i)).toISOString().slice(0, 10))

function Harness({ initial }) {
  const [view, setView] = useState(initial)
  return (
    <>
      <TimelineControls dates={DATES} {...view} onChange={setView} />
      <output data-testid="state">{`${view.windowKey}|${view.endIdx}|${view.playing}`}</output>
    </>
  )
}

const state = () => screen.getByTestId('state').textContent

describe('windowDays', () => {
  it('reads day counts and all time', () => {
    expect(windowDays('14')).toBe(14)
    expect(windowDays('all')).toBeNull()
    expect(windowDays('9999')).toBe(365)
    expect(windowDays('nope')).toBeNull()
  })
})

describe('TimelineControls', () => {
  afterEach(() => vi.useRealTimers())

  it('slides a rolling window one day per Play step after filling it', () => {
    vi.useFakeTimers()
    render(<Harness initial={{ windowKey: 'all', endIdx: 399, playing: false }} />)
    fireEvent.click(screen.getByText('14 days'))
    fireEvent.click(screen.getByLabelText('Play'))
    // Starts with the first full 14 days, then adds one day and drops the oldest
    expect(state()).toBe('14|13|true')
    expect(screen.getByTestId('timeline-range')).toHaveTextContent('14-day window · Jan 1, 2025 to Jan 14, 2025')
    act(() => { vi.advanceTimersByTime(PLAY_TICK_MS) })
    expect(state()).toBe('14|14|true')
    expect(screen.getByTestId('timeline-range')).toHaveTextContent('Jan 2, 2025 to Jan 15, 2025')
  })

  it('takes a custom rolling length', () => {
    render(<Harness initial={{ windowKey: 'all', endIdx: 399, playing: false }} />)
    fireEvent.change(screen.getByLabelText('Custom rolling window in days'), { target: { value: '21' } })
    expect(state()).toBe('21|399|false')
    expect(screen.getByTestId('timeline-range')).toHaveTextContent('21-day window')
  })

  it('all time Play still covers the whole range in bigger steps', () => {
    vi.useFakeTimers()
    render(<Harness initial={{ windowKey: 'all', endIdx: 0, playing: false }} />)
    fireEvent.click(screen.getByLabelText('Play'))
    act(() => { vi.advanceTimersByTime(PLAY_TICK_MS) })
    expect(state()).toBe('all|3|true')
  })
})

describe('play speed', () => {
  afterEach(() => vi.useRealTimers())

  it('waits longer between steps on Slow', () => {
    vi.useFakeTimers()
    render(<Harness initial={{ windowKey: '14', endIdx: 13, playing: false }} />)
    fireEvent.change(screen.getByLabelText('Play speed'), { target: { value: 'slow' } })
    fireEvent.click(screen.getByLabelText('Play'))
    act(() => { vi.advanceTimersByTime(tickMs('normal')) })
    expect(state()).toBe('14|13|true')
    act(() => { vi.advanceTimersByTime(tickMs('slow') - tickMs('normal')) })
    expect(state()).toBe('14|14|true')
  })
})
