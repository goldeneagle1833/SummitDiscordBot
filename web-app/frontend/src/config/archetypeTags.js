// Manually curated strategic tags, keyed by the server's stable archetype ID.
// Tags are non-hierarchical; their display order is fixed below.
export const STRATEGY_COLORS = {
  Midrange: '#2E7D32',
  Aggro: '#C62828',
  Control: '#1565C0',
  Tempo: '#7B1FA2',
  Ramp: '#795548',
}

const STRATEGY_ORDER = Object.keys(STRATEGY_COLORS)

// To classify another archetype, add its group.id and applicable tags here.
const ARCHETYPE_TAGS = {
  'pathfinder-fire': ['Midrange', 'Aggro'],
  'archimago-earth-fire': ['Control'],
  'avatar-of-air-air': ['Aggro', 'Tempo'],
  'necromancer-air-water': ['Midrange'],
  'necromancer-fire': ['Aggro'],
  'imposter-earth-fire': ['Midrange', 'Control'],
  'imposter-fire-water': ['Midrange', 'Aggro'],
  'savior-earth-fire': ['Aggro'],
  'pathfinder-water': ['Midrange'],
  'imposter-air-water': ['Midrange'],
  'deathspeaker-earth-fire': ['Midrange', 'Control'],
  'geomancer-earth-fire': ['Midrange', 'Control'],
  'sorcerer-air-earth': ['Midrange', 'Ramp'],
  'avatar-of-air-air-water': ['Tempo'],
  'imposter-earth-water': ['Midrange'],
}

export function getArchetypeTags(archetypeId) {
  const tags = Object.hasOwn(ARCHETYPE_TAGS, archetypeId)
    ? ARCHETYPE_TAGS[archetypeId]
    : []
  return STRATEGY_ORDER.filter((tag) => tags.includes(tag))
}
