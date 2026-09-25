import { describe, it, expect } from 'vitest'
import { getAvatarImagePath, badgesByPlayer } from '../avatarBadges'

const FILES = ['Avatar_of_Earth.png', 'avatar-of-air.webp', 'Dragonlord.jpg']

describe('getAvatarImagePath', () => {
  it('matches names regardless of case and punctuation', () => {
    expect(getAvatarImagePath('Avatar of Earth', FILES)).toBe('Avatar_of_Earth.png')
    expect(getAvatarImagePath('Avatar of Air', FILES)).toBe('avatar-of-air.webp')
  })

  it('returns null when nothing matches', () => {
    expect(getAvatarImagePath('Sparkmage', FILES)).toBeNull()
  })
})

describe('badgesByPlayer', () => {
  it('groups badges per player, best score first, with image paths', () => {
    const map = badgesByPlayer(
      [
        { avatar: 'Avatar of Air', player_id: '3', avatar_score: 40, wins: 5, losses: 2 },
        { avatar: 'Dragonlord', player_id: '3', avatar_score: 60, wins: 9, losses: 1 },
        { avatar: 'Sparkmage', player_id: '1', avatar_score: 50, wins: 7, losses: 3 },
      ],
      FILES,
    )
    expect(map['3'].map((b) => b.avatar)).toEqual(['Dragonlord', 'Avatar of Air'])
    expect(map['3'][0].imgSrc).toBe('/avatar-images/Dragonlord.jpg')
    expect(map['1'][0].imgSrc).toBeNull()
    expect(map['2']).toBeUndefined()
  })
})
