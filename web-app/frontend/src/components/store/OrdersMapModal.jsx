import { useCallback, useEffect, useState } from 'react'
import { adminGetOrderMap } from '@/api/store'
import SeriesMap from '@/components/explorer/SeriesMap'
import { stateName } from './usStates'

const dollars = (cents) => `$${((cents || 0) / 100).toFixed(2)}`

/** Map of where paid orders shipped: one pin per city, sized by order count. */
export default function OrdersMapModal({ storefrontId, days, rangeLabel, title, onClose }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    setError(null)
    adminGetOrderMap(storefrontId, days).then(setData).catch((e) => setError(e.message))
  }, [storefrontId, days])
  useEffect(load, [load])

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const max = Math.max(1, ...(data?.places || []).map((p) => p.orders))
  const points = (data?.places || []).map((p) => ({
    id: `${p.city}-${p.state}`,
    latitude: p.latitude,
    longitude: p.longitude,
    color: '#ffd700',
    radius: 6 + Math.round((p.orders / max) * 12),
    title: `${p.city}, ${stateName(p.state)}`,
    lines: [`${p.orders} ${p.orders === 1 ? 'order' : 'orders'}`, dollars(p.sales_cents)],
  }))

  return (
    <div className="fixed inset-0 z-[1100] bg-black/70 flex items-center justify-center p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Order map"
        className="bg-bg-surface border border-border rounded-lg w-full max-w-5xl max-h-full overflow-auto p-4 space-y-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold">{title} orders · last {rangeLabel}</h2>
          <button type="button" onClick={onClose} className="text-sm text-primary hover:underline">Close</button>
        </div>
        {error && <p className="text-accent-red text-sm">{error}</p>}
        {!data && !error && <p className="text-sm text-text-muted">Loading map…</p>}
        {data && (
          <>
            <SeriesMap points={points} height="h-[60vh]" storageKey="store-orders-map-style" />
            <p className="text-xs text-text-muted">
              One pin per city, sized by how many orders shipped there. Street addresses are never shown.
              {data.locating > 0 && (
                <>
                  {' '}{data.locating} {data.locating === 1 ? 'city is' : 'cities are'} still being placed on the map.{' '}
                  <button type="button" onClick={load} className="text-primary hover:underline">Refresh</button>
                </>
              )}
              {data.not_found > 0 && ` ${data.not_found} couldn't be found.`}
            </p>
          </>
        )}
      </div>
    </div>
  )
}
