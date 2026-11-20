import { describe, it, expect } from 'vitest'
import { buildCalendar, milesBetween, weekStart } from '../calendarModel'

const columbus = { latitude: 39.96, longitude: -83.0 }
const dayton = { latitude: 39.76, longitude: -84.19 } // ~65 miles
const denver = { latitude: 39.74, longitude: -104.99 }

const app = (id, place, dates, extra = {}) => ({
  id, ...place, status: 'pending',
  dates: dates.map(([s, e], i) => ({ start_date: s, end_date: e || s, choice_rank: i + 1 })),
  ...extra,
})
const week = (weeks, saturday) => weeks.find((w) => w.saturday === saturday)

describe('calendarModel', () => {
  it('measures miles', () => {
    expect(Math.round(milesBetween(columbus, dayton))).toBeGreaterThan(55)
    expect(milesBetween(columbus, dayton)).toBeLessThan(75)
    expect(milesBetween(columbus, {})).toBeNull()
  })

  it('weeks start on Monday', () => {
    expect(weekStart(new Date('2027-04-10T00:00:00Z')).toISOString().slice(0, 10)).toBe('2027-04-05')
  })

  it('covers March through October', () => {
    const weeks = buildCalendar([])
    expect(weeks[0].start).toBe('2027-03-01')
    expect(weeks.at(-1).sunday).toBe('2027-10-31')
  })

  it('flags same weekend under 100 miles as competing, far apart as not', () => {
    const weeks = buildCalendar([
      app(1, columbus, [['2027-04-10']]),
      app(2, dayton, [['2027-04-11']]),
      app(3, denver, [['2027-04-10']]),
    ])
    const w = week(weeks, '2027-04-10')
    expect(w.exact.map((e) => e.application.id)).toEqual([1, 2, 3])
    expect(w.competing).toHaveLength(1)
    expect([w.competing[0].a.application.id, w.competing[0].b.application.id]).toEqual([1, 2])
  })

  it('keeps vague windows as flexible, never competing', () => {
    const weeks = buildCalendar([
      app(1, columbus, [['2027-06-01', '2027-08-31']]),
      app(2, dayton, [['2027-06-12']]),
    ])
    const w = week(weeks, '2027-06-12')
    expect(w.flexible.map((e) => e.application.id)).toEqual([1])
    expect(w.competing).toHaveLength(0)
  })

  it('can show first choices only', () => {
    const weeks = buildCalendar([app(1, columbus, [['2027-04-10'], ['2027-05-15']])], { firstChoiceOnly: true })
    expect(week(weeks, '2027-05-15').exact).toHaveLength(0)
    expect(week(weeks, '2027-04-10').exact).toHaveLength(1)
  })

  it('marks busy weekends', () => {
    const many = [1, 2, 3, 4].map((id) => app(id, { latitude: id * 10, longitude: id * 10 }, [['2027-07-17']]))
    expect(week(buildCalendar(many), '2027-07-17').busy).toBe(true)
  })
})
