export default function PlayerHeader({ data, eloText, rankText, eloSource, onSourceChange, eventFilter, pastEvents, onEventChange }) {
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
        </div>

        <select
          value={eventFilter}
          onChange={(e) => onEventChange(e.target.value)}
          className="bg-bg-raised border border-border rounded px-3 py-2 text-sm min-w-[180px]"
        >
          <option value="lifetime">Lifetime</option>
          <option value="current">Current Event</option>
          {pastEvents.map((ev) => (
            <option key={ev.event_id} value={ev.event_id}>{ev.event_name}</option>
          ))}
        </select>
      </div>
    </div>
  )
}
