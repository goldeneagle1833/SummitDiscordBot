import CollapsibleSection from './CollapsibleSection'

export default function AvatarPerformance({ avatars, open, onToggle }) {
  if (!avatars?.length) return null

  return (
    <CollapsibleSection title="Avatar Performance" open={open} onToggle={onToggle}>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {avatars.map((av) => (
          <div key={av.name} className="bg-bg-raised border border-border rounded-lg p-3 text-center">
            <p className="font-medium text-text-primary text-sm mb-1">{av.name}</p>
            <p className="text-sm">
              <span className="text-accent-green">{av.wins}</span>
              {' - '}
              <span className="text-accent-red">{av.losses}</span>
            </p>
            <p className="text-xs text-text-muted">{av.win_rate}%</p>
          </div>
        ))}
      </div>
    </CollapsibleSection>
  )
}
