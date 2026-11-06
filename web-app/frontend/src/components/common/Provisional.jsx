import { HIDDEN_CHANGE_TITLE, PROVISIONAL_GAMES, provisionalLabel, provisionalOf } from '@/utils/provisional'

/**
 * Small muted tag shown instead of a provisional rating: "Provisional (3/8)".
 * Same look as the leaderboard's "not yet eligible" tag. `className` replaces
 * the default text size.
 */
export function ProvisionalTag({ games, className = 'text-xs' }) {
  return (
    <span
      className={`text-text-muted whitespace-nowrap ${className}`}
      title={`Rating shown after ${PROVISIONAL_GAMES} games`}
      data-testid="provisional-tag"
    >
      {provisionalLabel(games)}
    </span>
  )
}

/**
 * A rating, or the provisional tag when `obj` flags it provisional.
 * `value` defaults to obj[field]; `prefix` picks `<prefix>_provisional`.
 */
export function Rating({ obj, field, value, prefix = '', fallback = null, className }) {
  const prov = provisionalOf(obj, prefix)
  if (prov) return <ProvisionalTag games={prov.games} className={className} />
  const v = value !== undefined ? value : obj?.[field]
  return v ?? fallback
}

/** Muted dash shown instead of a per-match change hidden while provisional. */
export function HiddenChange({ className = '' }) {
  return (
    <span className={`text-text-muted ${className}`} title={HIDDEN_CHANGE_TITLE} data-testid="hidden-change">
      {'—'}
    </span>
  )
}

export default ProvisionalTag
