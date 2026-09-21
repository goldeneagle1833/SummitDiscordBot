// Top-cut voice requirement: ranked games played as voice matches this season.

export function VoiceGamesCell({ count = 0, requirement }) {
  const min = requirement?.min_games || 0
  const met = count >= min
  return (
    <span
      className={met ? 'text-accent-green' : 'text-text-muted'}
      title={`${count} ranked voice game${count === 1 ? '' : 's'} this season`}
    >
      {met ? '✓' : `${count}/${min}`}
    </span>
  )
}

export function VoiceRequirementNote({ requirement }) {
  if (!requirement?.min_games) return null
  return (
    <p className="text-xs text-text-muted mb-3">
      {'\u{1F50A}'} Voice: ranked games queued with voice this season.{' '}
      {requirement.enforced
        ? `Top cut requires ${requirement.min_games}.`
        : `Top cut will require ${requirement.min_games} starting next season.`}
    </p>
  )
}
