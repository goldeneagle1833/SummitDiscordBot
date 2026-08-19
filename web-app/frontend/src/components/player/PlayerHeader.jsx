export default function PlayerHeader({ data, eloText, rankText, eloSource, onSourceChange, eventFilter, pastEvents, onEventChange, canSeeLifetime }) {
  const avatarEventElos = data.avatar_event_elos || []

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-5">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-2xl font-display text-text-primary">{data.name}</h1>
            {(data.has_web_matches || data.has_bot_matches) && (
              <div className="inline-flex bg-bg-raised border border-border rounded-lg overflow-hidden">
                <button
                  onClick={() => onSourceChange('web')}
                  className={`px-3 py-1 text-xs font-medium transition-colors ${
                    eloSource === 'web' ? 'bg-secondary text-black' : 'text-text-muted hover:text-text-primary'
                  }`}
                >
                  Paper
                </button>
                <button
                  onClick={() => onSourceChange('bot')}
                  className={`px-3 py-1 text-xs font-medium transition-colors ${
                    eloSource === 'bot' ? 'bg-secondary text-black' : 'text-text-muted hover:text-text-primary'
                  }`}
                >
                  Online
                </button>
              </div>
            )}
          </div>
          <p className="text-text-muted text-sm">{eloText}</p>
          {rankText && <p className="text-text-muted text-sm">{rankText}</p>}
          {data.avatar_specific_event && (
            <div className="mt-3">
              <p className="text-xs uppercase tracking-wide text-text-muted mb-2">
                {data.avatar_event?.event_name || 'Event'} avatar ELO
              </p>
              {avatarEventElos.length ? (
                <div className="flex flex-wrap gap-2">
                  {avatarEventElos.map((entry) => (
                    <div
                      key={entry.avatar}
                      className="bg-bg-raised border border-border rounded px-3 py-2 text-sm"
                    >
                      <span className="font-semibold text-text-primary">{entry.avatar}</span>
                      <span className="text-secondary ml-2">{entry.elo} ELO</span>
                      {entry.rank > 0 && (
                        <span className="text-text-muted ml-2">#{entry.rank}</span>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-text-muted">No games recorded for this event.</p>
              )}
            </div>
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
