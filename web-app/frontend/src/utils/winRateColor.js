/** Red (0%) through white (50%) to green (100%), as on the Avatars page. */
export function getWinRateColor(winRate) {
  const pct = Math.max(0, Math.min(100, winRate))
  if (pct <= 50) {
    const ratio = pct / 50
    return `rgb(${Math.round(231 + 24 * ratio)}, ${Math.round(76 + 179 * ratio)}, ${Math.round(60 + 195 * ratio)})`
  }
  const ratio = (pct - 50) / 50
  return `rgb(${Math.round(255 - 209 * ratio)}, ${Math.round(255 - 51 * ratio)}, ${Math.round(255 - 142 * ratio)})`
}
