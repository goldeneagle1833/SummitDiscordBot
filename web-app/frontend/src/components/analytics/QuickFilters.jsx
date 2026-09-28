const ELEMENT_DOTS = {
  Earth: '#a07a4a',
  Fire: '#d9553a',
  Water: '#4d8fd6',
  Air: '#b3b6d4',
}

export const QUICK_FILTER_GROUPS = [
  { key: 'type', label: 'Card type', options: ['Avatar', 'Minion', 'Magic', 'Aura', 'Artifact', 'Site'] },
  { key: 'element', label: 'Element', options: ['Earth', 'Fire', 'Water', 'Air', 'None', 'Multi'] },
  { key: 'rarity', label: 'Rarity', options: ['Ordinary', 'Exceptional', 'Elite', 'Unique'] },
]

const CHIP = 'inline-flex items-center gap-1.5 rounded-full border px-3 min-h-[32px] text-xs transition-colors'
const CHIP_OFF = `${CHIP} border-border bg-bg-surface text-[#c9d1d9] hover:border-primary/60`
const CHIP_ON = `${CHIP} border-secondary bg-[#2b2a1a] text-secondary`

/**
 * One-tap card filters. Selecting a chip again clears it; only one value per
 * group applies at a time, which matches how the analytics table filters.
 */
export default function QuickFilters({ filters, onChange, disabled }) {
  const setGroup = (key, value) =>
    onChange({ ...filters, [key]: filters[key] === value ? '' : value })

  return (
    <div className="flex flex-wrap items-center gap-2" aria-label="Quick filters">
      {QUICK_FILTER_GROUPS.map((group, index) => (
        <div key={group.key} role="group" aria-label={group.label} className="flex flex-wrap items-center gap-2">
          {index > 0 && <span aria-hidden="true" className="hidden sm:block w-px h-5 bg-border mx-1" />}
          {group.options.map((option) => {
            const active = filters[group.key] === option
            return (
              <button
                key={option}
                type="button"
                aria-pressed={active}
                disabled={disabled}
                onClick={() => setGroup(group.key, option)}
                className={`${active ? CHIP_ON : CHIP_OFF} disabled:opacity-50`}
              >
                {ELEMENT_DOTS[option] && (
                  <span aria-hidden="true" className="w-2 h-2 rounded-full" style={{ background: ELEMENT_DOTS[option] }} />
                )}
                {option}
                {active && <span aria-hidden="true">×</span>}
              </button>
            )
          })}
        </div>
      ))}
    </div>
  )
}
