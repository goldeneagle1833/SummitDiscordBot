import CollapsibleSection from './CollapsibleSection'

export default function EloBrackets({ brackets, open, onToggle }) {
  if (!brackets?.length) return null

  return (
    <CollapsibleSection title="Winrate vs Opponent ELO" open={open} onToggle={onToggle}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="py-2 px-3 text-text-muted font-semibold">Bracket</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Record</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Win Rate</th>
            </tr>
          </thead>
          <tbody>
            {brackets.map((b) => (
              <tr key={b.bracket} className="border-b border-border/50">
                <td className="py-2 px-3">{b.bracket}</td>
                <td className="py-2 px-3">
                  <span className="text-accent-green">{b.wins}W</span>
                  {' / '}
                  <span className="text-accent-red">{b.losses}L</span>
                </td>
                <td className="py-2 px-3">{b.win_rate}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </CollapsibleSection>
  )
}
