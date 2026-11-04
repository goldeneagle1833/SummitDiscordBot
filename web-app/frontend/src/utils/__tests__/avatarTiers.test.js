import { describe, it, expect } from 'vitest'
import { avatarArchetypes } from '@/utils/avatarTiers'

describe('avatarArchetypes', () => {
  const avatars = [
    { name: 'Sparkmage', total: 300, wins: 180 },
    { name: 'Pathfinder', total: 200, wins: 90 },
    { name: 'Geomancer', total: 100, wins: 55 },
    { name: 'Tiny', total: 10, wins: 9 },
  ]

  it('drops Avatars under the game minimum and works out share and win rate', () => {
    const { archetypes, minimum, deckGames } = avatarArchetypes(avatars)
    expect(deckGames).toBe(610)
    expect(minimum).toBe(20)
    expect(archetypes.map((a) => a.avatar)).not.toContain('Tiny')
    const spark = archetypes.find((a) => a.avatar === 'Sparkmage')
    expect(spark.share).toBe(49.2)
    expect(spark.winRate).toBe(60)
  })

  it('puts the best score in S tier', () => {
    const { archetypes } = avatarArchetypes(avatars)
    expect(archetypes[0].avatar).toBe('Sparkmage')
    expect(archetypes[0].tier).toBe('S')
    expect(archetypes.every((a) => ['S', 'A', 'B', 'C'].includes(a.tier))).toBe(true)
  })

  it('handles no data', () => {
    expect(avatarArchetypes([]).archetypes).toEqual([])
  })
})
