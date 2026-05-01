import CollapsibleSection from './CollapsibleSection'

export default function AvatarMatchups({ matchups, open, onToggle }) {
  if (!matchups?.length) return null

  return (
    <CollapsibleSection title="Performance Against Other Avatars" open={open} onToggle={onToggle}>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {matchups.map((m) => (
          <div key={m.opponent_avatar} className="bg-bg-raised border border-border rounded-lg p-3 text-center">
            <p className="font-medium text-text-primary text-sm mb-1">{m.opponent_avatar}</p>
            <p className="text-sm">
              <span className="text-accent-green">{m.wins}</span>
              {' - '}
              <span className="text-accent-red">{m.losses}</span>
            </p>
            <p className="text-xs text-text-muted">{m.win_rate}% ({m.total_games} games)</p>
          </div>
        ))}
      </div>
    </CollapsibleSection>
  )
}
