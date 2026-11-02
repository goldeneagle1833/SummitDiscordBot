/**
 * Filters for the Matches tab: opponent, result, my avatar, opponent
 * avatar and play/draw. The server applies them before paging and sends back the record
 * for what is left, shown as a one-line summary.
 */
const SELECT_CLASS = 'h-11 w-full min-w-0 rounded-lg border border-border bg-bg-raised px-3 text-sm text-text-primary'

function withCurrent(list, value, label = value) {
  if (!value || list.some((o) => o.value === value)) return list
  return [{ value, label }, ...list]
}

export default function MatchFilters({ filters = {}, data, onChange }) {
  const options = data?.options || {}
  const set = (key, value, extra = {}) => {
    const next = { ...filters, ...extra, [key]: value }
    Object.keys(next).forEach((k) => { if (!next[k]) delete next[k] })
    onChange(next)
  }

  const opponents = withCurrent(
    (options.opponents || []).map((o) => ({ value: o.id, label: `${o.name} (${o.games})` })),
    filters.opponent,
    filters.opponentName,
  )
  const avatars = withCurrent((options.avatars || []).map((a) => ({ value: a, label: a })), filters.avatar)
  const oppAvatars = withCurrent((options.opponent_avatars || []).map((a) => ({ value: a, label: a })), filters.opponent_avatar)

  const active = ['opponent', 'result', 'avatar', 'opponent_avatar', 'play_draw'].some((k) => filters[k])
  if (!active && !(options.opponents || []).length) return null
  const ranked = data?.ranked || { wins: 0, losses: 0 }
  const casual = data?.casual || { wins: 0, losses: 0 }
  const record = (r) => {
    const total = r.wins + r.losses
    const rate = total ? Math.round((r.wins / total) * 1000) / 10 : 0
    return `${r.wins}W - ${r.losses}L${total ? ` (${rate}%)` : ''}`
  }

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-4 space-y-3">
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <label className="flex flex-col gap-1 text-xs text-text-muted">
          Opponent
          <select
            value={filters.opponent || ''}
            onChange={(e) => set('opponent', e.target.value, {
              opponentName: e.target.selectedOptions[0]?.text.replace(/ \(\d+\)$/, '') || '',
            })}
            className={SELECT_CLASS}
          >
            <option value="">All opponents</option>
            {opponents.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-text-muted">
          Result
          <select value={filters.result || ''} onChange={(e) => set('result', e.target.value)} className={SELECT_CLASS}>
            <option value="">Wins and losses</option>
            <option value="win">Wins</option>
            <option value="loss">Losses</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-text-muted">
          Avatar
          <select value={filters.avatar || ''} onChange={(e) => set('avatar', e.target.value)} className={SELECT_CLASS}>
            <option value="">All avatars</option>
            {avatars.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-text-muted">
          Opp. Avatar
          <select value={filters.opponent_avatar || ''} onChange={(e) => set('opponent_avatar', e.target.value)} className={SELECT_CLASS}>
            <option value="">All avatars</option>
            {oppAvatars.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-text-muted">
          Play/Draw
          <select value={filters.play_draw || ''} onChange={(e) => set('play_draw', e.target.value)} className={SELECT_CLASS}>
            <option value="">Play and draw</option>
            <option value="play">On the play</option>
            <option value="draw">On the draw</option>
          </select>
        </label>
      </div>
      {active && (
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
          <p className="text-text-primary" data-testid="filter-record">
            <span className="text-text-muted">Ranked:</span> {record(ranked)}
            {casual.wins + casual.losses > 0 && (
              <><span className="text-text-muted ml-3">Casual:</span> {record(casual)}</>
            )}
          </p>
          <button
            type="button"
            onClick={() => onChange({})}
            className="h-9 px-3 rounded-lg border border-border text-xs text-text-muted hover:border-secondary hover:text-secondary"
          >
            Clear filters
          </button>
        </div>
      )}
    </div>
  )
}
