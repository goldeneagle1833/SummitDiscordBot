import CollapsibleSection from './CollapsibleSection'

export default function AvatarPerformance({ avatars, open, onToggle }) {
  if (!avatars?.length) return null

  return (
    <CollapsibleSection title="Avatar Performance" open={open} onToggle={onToggle}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="py-2 px-3 text-text-muted font-semibold">Avatar</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Record</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Win Rate</th>
            </tr>
          </thead>
          <tbody>
            {avatars.map((av) => (
              <tr key={av.name} className="border-b border-border/50">
                <td className="py-2 px-3">{av.name}</td>
                <td className="py-2 px-3">
                  <span className="text-accent-green">{av.wins}W</span>
                  {' / '}
                  <span className="text-accent-red">{av.losses}L</span>
                </td>
                <td className="py-2 px-3">{av.win_rate}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </CollapsibleSection>
  )
}
