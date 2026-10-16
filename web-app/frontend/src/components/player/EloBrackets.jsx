import { getWinRateColor } from '@/utils/winRateColor'

/** Win rate against opponents grouped by their ELO, as labelled bars. */
export default function EloBrackets({ brackets }) {
  const rows = (brackets || []).filter((b) => b.wins + b.losses > 0)
  if (!rows.length) return null

  return (
    <section className="bg-bg-surface border border-border rounded-xl p-5">
      <h2 className="text-xs font-bold uppercase tracking-wider text-text-muted mb-4">Win rate vs opponent ELO</h2>
      <ul className="space-y-3">
        {rows.map((b) => (
          <li key={b.bracket} className="grid grid-cols-[96px_1fr_auto] items-center gap-3 text-sm">
            <span className="font-semibold text-text-primary">{b.bracket}</span>
            <div className="h-2.5 rounded bg-bg-raised overflow-hidden" aria-hidden="true">
              <div className="h-full rounded" style={{ width: `${b.win_rate}%`, background: getWinRateColor(b.win_rate) }} />
            </div>
            <span className="tabular-nums text-text-muted w-32 text-right">
              {b.wins}-{b.losses}
              <strong className="ml-2" style={{ color: getWinRateColor(b.win_rate) }}>{b.win_rate}%</strong>
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}
