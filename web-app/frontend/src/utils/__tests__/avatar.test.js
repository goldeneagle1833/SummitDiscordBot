import { describe, it, expect } from 'vitest'
import { avatarUrl, avatarMap } from '../avatar'

describe('avatarUrl', () => {
  it('builds a Discord CDN url from the avatar hash', () => {
    expect(avatarUrl({ user_id: '123', avatar: 'abc', provider: 'discord' })).toBe(
      'https://cdn.discordapp.com/avatars/123/abc.png?size=64',
    )
  })

  it('honours the requested size', () => {
    expect(avatarUrl({ user_id: '123', avatar: 'abc', provider: 'discord' }, 128)).toContain(
      'size=128',
    )
  })

  it('passes a Google avatar through unchanged', () => {
    const url = 'https://lh3.googleusercontent.com/a/xyz'
    expect(avatarUrl({ user_id: '123', avatar: url, provider: 'google' })).toBe(url)
  })

  it('returns null when there is nothing to show', () => {
    expect(avatarUrl(null)).toBeNull()
    expect(avatarUrl({ user_id: '123' })).toBeNull()
    expect(avatarUrl({ avatar: 'abc', provider: 'discord' })).toBeNull()
  })
})

describe('avatarMap', () => {
  it('keys avatars by user id', () => {
    const map = avatarMap([
      { user_id: '1', avatar: 'a', provider: 'discord' },
      { user_id: '2', avatar: null },
      { display_name: 'Guest' },
    ])
    expect(Object.keys(map)).toEqual(['1'])
    expect(map['1']).toContain('/avatars/1/a.png')
  })

  it('handles an empty field', () => {
    expect(avatarMap()).toEqual({})
  })
})
