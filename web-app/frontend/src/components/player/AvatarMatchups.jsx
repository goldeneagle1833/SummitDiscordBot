import CollapsibleSection from './CollapsibleSection'

export default function AvatarMatchups({ matchups, open, onToggle }) {
  if (!matchups?.length) return null

  return (
    <CollapsibleSection title="Performance Against Other Avatars" open={open} onToggle={onToggle}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="py-2 px-3 text-text-muted font-semibold">Opponent</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Record</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Win Rate</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Games</th>
            </tr>
          </thead>
          <tbody>
            {matchups.map((m) => (
              <tr key={m.opponent_avatar} className="border-b border-border/50">
                <td className="py-2 px-3">{m.opponent_avatar}</td>
                <td className="py-2 px-3">
                  <span className="text-accent-green">{m.wins}W</span>
                  {' / '}
                  <span className="text-accent-red">{m.losses}L</span>
                </td>
                <td className="py-2 px-3">{m.win_rate}%</td>
                <td className="py-2 px-3 text-text-muted">{m.total_games}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </CollapsibleSection>
  )
}
