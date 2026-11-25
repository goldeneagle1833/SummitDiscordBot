/**
 * Inactivity decay on a Glicko-2 avatar rating: an avatar not played for a
 * week loses 10 points a day until it is played again.
 *
 * `decay` (points lost since the last game) shows "-30 idle" in amber;
 * otherwise `inDays` (1 or 2) shows a muted "decays in 2d" warning.
 * Renders nothing when neither applies.
 */
export const DECAY_RULE = 'Not played on this avatar for a week: loses 10 points a day until you play it again (never below 1500).'

export function DecayTag({ decay, inDays, className = 'text-xs' }) {
  if (decay > 0) {
    return (
      <span
        className={`text-amber-400 whitespace-nowrap ${className}`}
        title={`Lost ${decay} points to inactivity. ${DECAY_RULE}`}
        data-testid="decay-tag"
      >
        {`-${decay} idle`}
      </span>
    )
  }
  if (inDays > 0) {
    return (
      <span
        className={`text-text-muted whitespace-nowrap ${className}`}
        title={`Starts losing points in ${inDays} day${inDays === 1 ? '' : 's'}. ${DECAY_RULE}`}
        data-testid="decay-soon-tag"
      >
        {`decays in ${inDays}d`}
      </span>
    )
  }
  return null
}

export default DecayTag
