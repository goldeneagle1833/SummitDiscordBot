import { describe, it, expect } from 'vitest'
import { filterParticipants, swissRecord, EMPTY_PARTICIPANT_FILTERS } from '../ParticipantFilters'

const decks = [
  { deck_id: 'a', player: 'weisel', deck_name: 'Imposter Tempo', avatar: 'Imposter', elements: ['Water', 'Earth'] },
  { deck_id: 'b', player: 'Frogimago', deck_name: 'Fire Padfinder', avatar: 'Pathfinder', elements: ['Fire'] },
  { deck_id: 'c', player: 'Moth', deck_name: 'Burnt Toasties', avatar: 'Necromancer', elements: ['Fire', 'Earth'] },
]
const history = {
  a: { matches: [{ phase: 'SingleElimination', result: 'Loss' }, { phase: 'Swiss', result: 'Win' }, { phase: 'Swiss', result: 'Loss' }] },
  b: { matches: [{ phase: 'Swiss', result: 'Loss' }, { phase: 'Swiss', result: 'Loss' }, { phase: 'Swiss', result: 'Loss' }] },
}
const historyFor = (d) => history[d.deck_id] || null
const f = (patch) => ({ ...EMPTY_PARTICIPANT_FILTERS, ...patch })
const ids = (list) => list.map((d) => d.deck_id)

describe('filterParticipants', () => {
  it('returns everything with no filters', () => {
    expect(ids(filterParticipants(decks, f({}), historyFor))).toEqual(['a', 'b', 'c'])
  })
  it('searches player and deck name', () => {
    expect(ids(filterParticipants(decks, f({ q: 'frog' }), historyFor))).toEqual(['b'])
    expect(ids(filterParticipants(decks, f({ q: 'toast' }), historyFor))).toEqual(['c'])
  })
  it('filters by avatar and by all picked elements', () => {
    expect(ids(filterParticipants(decks, f({ avatar: 'Imposter' }), historyFor))).toEqual(['a'])
    expect(ids(filterParticipants(decks, f({ elements: ['Fire'] }), historyFor))).toEqual(['b', 'c'])
    expect(ids(filterParticipants(decks, f({ elements: ['Fire', 'Earth'] }), historyFor))).toEqual(['c'])
  })
  it('counts only Swiss losses and drops players without history', () => {
    expect(swissRecord(history.a)).toEqual({ wins: 1, losses: 1 })
    expect(ids(filterParticipants(decks, f({ losses: '1' }), historyFor))).toEqual(['a'])
    expect(ids(filterParticipants(decks, f({ losses: '3' }), historyFor))).toEqual(['a', 'b'])
  })
})
