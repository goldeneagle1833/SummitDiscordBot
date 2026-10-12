import { useState } from 'react'
import { adminSetSaleAlerts } from '@/api/store'

/** The current user's own switch for Discord DMs about new sales. */
export default function SaleAlertsToggle({ storefront, onChanged }) {
  const [on, setOn] = useState(Boolean(storefront.sale_alerts))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const flip = async () => {
    const next = !on
    setBusy(true)
    setError(null)
    setOn(next)
    try {
      await adminSetSaleAlerts(storefront.id, next)
      onChanged?.()
    } catch (e) {
      setOn(!next)
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <button
        type="button"
        role="switch"
        aria-checked={on}
        aria-label={`Discord message me about ${storefront.name} sales`}
        disabled={busy}
        onClick={flip}
        className={`relative inline-flex h-5 w-9 shrink-0 rounded-full border transition-colors disabled:opacity-50 ${
          on ? 'bg-accent-green border-accent-green' : 'bg-bg-elevated border-border'
        }`}
      >
        <span
          className={`absolute top-0.5 h-3.5 w-3.5 rounded-full bg-white transition-all ${on ? 'left-[18px]' : 'left-0.5'}`}
        />
      </button>
      <span className="text-text-muted">
        Discord message me when {storefront.name} makes a sale
      </span>
      {error && <span className="text-accent-red">{error}</span>}
    </div>
  )
}
