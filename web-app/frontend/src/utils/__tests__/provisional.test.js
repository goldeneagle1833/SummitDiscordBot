import { describe, it, expect } from 'vitest'
import {
  HIDDEN_CHANGE_TITLE, PROVISIONAL_GAMES, isHidden, isNum, isProvisional, provisionalLabel, provisionalOf, signed,
} from '../provisional'

describe('provisional helpers', () => {
  it('labels a provisional rating with games out of 8', () => {
    expect(PROVISIONAL_GAMES).toBe(8)
    expect(provisionalLabel(3)).toBe('Provisional (3/8)')
    expect(provisionalLabel(undefined)).toBe('Provisional (0/8)')
    expect(HIDDEN_CHANGE_TITLE).toBe('Provisional: shown after 8 games')
  })

  it('reads plain and prefixed provisional flags', () => {
    expect(provisionalOf({ elo: null, provisional: true, provisional_games: 5 })).toEqual({ games: 5 })
    const profile = { event_provisional: true, event_provisional_games: 2, lifetime_provisional: false }
    expect(provisionalOf(profile, 'event')).toEqual({ games: 2 })
    expect(provisionalOf(profile, 'lifetime')).toBeNull()
    expect(isProvisional(profile, 'event')).toBe(true)
  })

  it('treats today’s data (no flags) as settled', () => {
    expect(provisionalOf({ elo: 1612 })).toBeNull()
    expect(provisionalOf(null)).toBeNull()
    expect(isHidden({ elo_change: 12 }, 'elo_change')).toBe(false)
  })

  it('spots hidden per-match changes', () => {
    expect(isHidden({ elo_change: null, elo_change_hidden: true }, 'elo_change')).toBe(true)
    expect(isHidden({ winner_elo_change: null, winner_elo_change_hidden: true }, 'winner_elo_change')).toBe(true)
    expect(isHidden({ winner_elo_change_hidden: true }, 'loser_elo_change')).toBe(false)
  })

  it('formats signed numbers and checks for real numbers', () => {
    expect(signed(12)).toBe('+12')
    expect(signed(-8)).toBe('-8')
    expect(signed(0)).toBe('0')
    expect(isNum(0)).toBe(true)
    expect(isNum(1500)).toBe(true)
    expect(isNum(null)).toBe(false)
    expect(isNum(undefined)).toBe(false)
    expect(isNum(NaN)).toBe(false)
  })
})
