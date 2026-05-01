export default function RecordedGames({ games }) {
  if (!games?.length) return null

  return (
    <section>
      <h3 className="text-lg font-semibold text-text-primary mb-1">Self-Reported Games</h3>
      <p className="text-xs text-text-muted mb-3">Games you've recorded for personal tracking. These do not affect your ELO rating.</p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="py-2 px-3 text-text-muted font-semibold">ID</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Result</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Opponent Avatar</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Deck Link</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Play/Draw</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Time</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Date</th>
            </tr>
          </thead>
          <tbody>
            {games.map((g) => (
              <tr key={g.report_id} className="border-b border-border/50">
                <td className="py-2 px-3 text-text-muted">#{g.report_id}</td>
                <td className={`py-2 px-3 ${g.result === 'Win' ? 'text-accent-green' : 'text-accent-red'}`}>{g.result}</td>
                <td className="py-2 px-3">{g.opponent}</td>
                <td className="py-2 px-3">
                  {g.deck_url ? (
                    <a href={g.deck_url} target="_blank" rel="noopener noreferrer" className="text-secondary hover:underline text-xs">
                      View
                    </a>
                  ) : '-'}
                </td>
                <td className="py-2 px-3 text-text-muted">{g.first_player || '-'}</td>
                <td className="py-2 px-3 text-text-muted">{g.match_time ? `${g.match_time} min` : '-'}</td>
                <td className="py-2 px-3 text-text-muted">{g.date ? new Date(g.date).toLocaleDateString() : '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
