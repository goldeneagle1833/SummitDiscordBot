// A hall floor plan with pins placed by percent (0-100) of its width/height.
// Tap anywhere to pick a spot when `onPick` is given.
export default function HallMap({ map, pins = [], spots = [], onPick, onPickSpot, className = '' }) {
  const pick = (e) => {
    if (!onPick) return
    const rect = e.currentTarget.getBoundingClientRect()
    const x = ((e.clientX - rect.left) / rect.width) * 100
    const y = ((e.clientY - rect.top) / rect.height) * 100
    onPick(Math.round(Math.min(100, Math.max(0, x)) * 100) / 100, Math.round(Math.min(100, Math.max(0, y)) * 100) / 100)
  }

  return (
    <div
      className={`relative w-full select-none overflow-hidden rounded-lg border border-border bg-bg-elevated ${onPick ? 'cursor-crosshair' : ''} ${className}`}
      onClick={pick}
      role={onPick ? 'button' : undefined}
      aria-label={onPick ? 'Tap the map to set your spot' : undefined}
    >
      {map?.image_url ? (
        <img src={map.image_url} alt={`${map.name} hall map`} className="block w-full h-auto" draggable={false} />
      ) : (
        <div
          className="w-full aspect-[3/2] flex items-center justify-center text-text-muted text-sm"
          style={{
            backgroundImage:
              'linear-gradient(rgba(139,148,158,0.15) 1px, transparent 1px), linear-gradient(90deg, rgba(139,148,158,0.15) 1px, transparent 1px)',
            backgroundSize: '10% 10%',
          }}
        >
          <span className="bg-bg-surface/90 px-3 py-1 rounded">Hall map coming soon</span>
        </div>
      )}

      {spots
        .filter((s) => s.x != null && s.y != null)
        // A pin sitting on a quick spot replaces that spot's label
        .filter((s) => !pins.some((p) => p.x != null && Math.abs(p.x - s.x) < 4 && Math.abs(p.y - s.y) < 4))
        .map((s) => (
        <button
          key={s.label}
          type="button"
          onClick={(e) => {
            if (!onPickSpot) return
            e.stopPropagation()
            onPickSpot(s)
          }}
          className={`absolute -translate-x-1/2 -translate-y-1/2 rounded-full bg-bg-surface/90 border border-border text-[10px] sm:text-xs text-text-muted px-1.5 py-0.5 whitespace-nowrap ${onPickSpot ? 'hover:text-text hover:border-primary' : 'pointer-events-none'}`}
          style={{ left: `${s.x}%`, top: `${s.y}%` }}
        >
          {s.label}
        </button>
      ))}

      {pins.filter((p) => p.x != null && p.y != null).map((p, i) => (
        <div
          key={p.key || i}
          className="absolute pointer-events-none"
          style={{ left: `${p.x}%`, top: `${p.y}%`, transform: 'translate(-50%, -100%)' }}
        >
          <div className="flex flex-col items-center">
            {p.name && (
              <span className="mb-1 rounded bg-bg-dark/90 border border-secondary/60 px-1.5 py-0.5 text-[11px] text-secondary whitespace-nowrap shadow-harsh">
                {p.name}
              </span>
            )}
            <span className="relative flex h-9 w-9 items-center justify-center rounded-full border-2 border-secondary bg-bg-dark shadow-harsh overflow-hidden">
              {p.avatar ? (
                <img src={p.avatar} alt="" className="h-full w-full object-cover" onError={(e) => { e.target.style.display = 'none' }} />
              ) : (
                <span className="h-3 w-3 rounded-full bg-secondary" />
              )}
            </span>
            <span className="h-0 w-0 border-x-[6px] border-x-transparent border-t-[8px] border-t-secondary" />
          </div>
        </div>
      ))}
    </div>
  )
}
