// Same rules as the Meta Report's tiers (services/meta_report.py archetype_stats),
// run on the Avatars page's own totals so the map follows its season filter.
export const MIN_AVATAR_GAMES = 20
export const MIN_AVATAR_SHARE = 0.01
const TIERS = ['S', 'A', 'B', 'C']

function tierScore(wins, games, share) {
  const adjusted = (wins + 15) / (games + 30)
  return (adjusted - 0.5) * 100 + Math.log2(share * 100 + 1) * 1.5
}

const round1 = (v) => Math.round(v * 10) / 10

/** avatars: [{ name, total, wins }] -> Meta Report archetype rows with tiers. */
export function avatarArchetypes(avatars) {
  const list = (avatars || []).filter((a) => a && a.total > 0)
  const deckGames = list.reduce((s, a) => s + a.total, 0)
  const minimum = Math.max(MIN_AVATAR_GAMES, Math.ceil(deckGames * MIN_AVATAR_SHARE))
  const rows = list
    .filter((a) => a.total >= minimum)
    .map((a) => {
      const share = a.total / deckGames
      return {
        avatar: a.name,
        elements: '',
        games: a.total,
        wins: a.wins,
        winRate: round1((a.wins / a.total) * 100),
        share: round1(share * 100),
        score: tierScore(a.wins, a.total, share),
      }
    })
    .sort((a, b) => b.score - a.score)
  const total = rows.length
  const sCut = Math.min(4, Math.max(1, Math.round(total * 0.1)))
  const aCut = sCut + Math.min(8, Math.round(total * 0.2))
  const bCut = aCut + Math.min(12, Math.round(total * 0.3))
  rows.forEach((r, i) => {
    r.tier = TIERS[i < sCut ? 0 : i < aCut ? 1 : i < bCut ? 2 : 3]
  })
  return { archetypes: rows, minimum, deckGames }
}
