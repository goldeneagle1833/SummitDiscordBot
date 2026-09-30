import PostseasonName from '@/components/player/BracketMarks'
export default function PlayerHeader({ data, playerId, eloText, rankText, avatarEntries = [], eventFilter, pastEvents, onEventChange, canSeeLifetime }) {
  return (
    <div className="bg-bg-surface border border-border rounded-lg p-5">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-2xl font-display text-text-primary">
              <PostseasonName playerId={playerId} yurtSize={20}>
                <span tabIndex={0}>{data.name}</span>
              </PostseasonName>
            </h1>
          </div>
          {eloText && <p className="text-text-muted text-sm">{eloText}</p>}
          {rankText && <p className="text-text-muted text-sm">{rankText}</p>}
          {avatarEntries.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-2" aria-label="Event ELO per avatar">
              {avatarEntries.map((entry) => (
                <li
                  key={entry.avatar}
                  className="px-2.5 py-1 text-xs rounded border border-border bg-bg-raised"
                >
                  <span className="text-text-primary font-medium">{entry.avatar}</span>
                  <span className="text-text-muted"> · {entry.event_elo} · #{entry.rank}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <select
          value={eventFilter}
          onChange={(e) => onEventChange(e.target.value)}
          className="bg-bg-raised border border-border rounded px-3 py-2 text-sm min-w-[180px]"
        >
          {canSeeLifetime && <option value="lifetime">Lifetime</option>}
          <option value="current">Current Event</option>
          {pastEvents.map((ev) => (
            <option key={ev.event_id} value={ev.event_id}>{ev.event_name}</option>
          ))}
        </select>
      </div>
    </div>
  )
}
