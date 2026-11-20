import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { adminGetOrder } from '@/api/store'
import usePageTitle from '@/hooks/usePageTitle'
import { PackingSlip, SLIP_CSS } from './StoreOrderPrint'

export const BULK_PRINT_MAX = 100
const AT_ONCE = 5

/**
 * Put orders into packages: orders paired to ship together (same
 * ship_group) share one slip, everything else gets its own. Keeps the
 * order the ids came in, with a package sitting where its first order was.
 */
export function packagesFor(orders) {
  const out = []
  const byGroup = {}
  orders.forEach((o) => {
    if (o.ship_group && byGroup[o.ship_group]) {
      byGroup[o.ship_group].push(o)
    } else {
      const pkg = [o]
      if (o.ship_group) byGroup[o.ship_group] = pkg
      out.push(pkg)
    }
  })
  return out
}

/**
 * Many packing slips in one print job, one slip per page. Opened from the
 * Store Admin order queue as /admin/store/orders/print?ids=1,2,3 (add
 * &print=1 to open the print dialog once every order has loaded).
 */
export default function StoreOrderBulkPrint() {
  const [params] = useSearchParams()
  const autoPrint = params.get('print') === '1'
  const idsKey = params.get('ids') || ''
  const ids = useMemo(
    () => [...new Set(idsKey.split(',').map((x) => x.trim()).filter((x) => /^\d+$/.test(x)))].slice(0, BULK_PRINT_MAX),
    [idsKey],
  )
  const [orders, setOrders] = useState(null)
  const [loaded, setLoaded] = useState(0)
  const [failed, setFailed] = useState([])

  useEffect(() => {
    let cancelled = false
    setOrders(null)
    setLoaded(0)
    setFailed([])
    const results = new Array(ids.length)
    const bad = []
    let next = 0
    let done = 0
    // A few at a time so a big batch doesn't flood the server
    const worker = async () => {
      while (next < ids.length) {
        const i = next++
        try {
          const d = await adminGetOrder(ids[i])
          results[i] = d.order
        } catch {
          bad.push(ids[i])
        }
        done += 1
        if (!cancelled) setLoaded(done)
      }
    }
    Promise.all(Array.from({ length: Math.min(AT_ONCE, ids.length) }, worker)).then(() => {
      if (cancelled) return
      setFailed(bad)
      setOrders(results.filter(Boolean))
    })
    return () => { cancelled = true }
  }, [ids])

  const packages = useMemo(() => (orders ? packagesFor(orders) : []), [orders])
  const ready = orders !== null && packages.length > 0
  usePageTitle(ready ? `Packing slips (${packages.length})` : 'Packing slips')

  useEffect(() => {
    if (!ready || !autoPrint) return
    const t = setTimeout(() => {
      try {
        window.print()
      } catch {
        /* jsdom and some embedded browsers have no print() */
      }
    }, 300)
    return () => clearTimeout(t)
  }, [ready, autoPrint])

  if (ids.length === 0) {
    return <div className="slip-page"><style>{SLIP_CSS}</style><div className="slip-toolbar">No orders picked to print.</div></div>
  }
  if (orders === null) {
    return (
      <div className="slip-page">
        <style>{SLIP_CSS}</style>
        <div className="slip-toolbar">Loading orders… {loaded} of {ids.length}</div>
      </div>
    )
  }

  const paired = orders.length - packages.length
  return (
    <div className="slip-page slip-bulk">
      <style>{SLIP_CSS}</style>
      <div className="slip-toolbar">
        <span>
          {packages.length} packing {packages.length === 1 ? 'slip' : 'slips'}, one per page
          {paired > 0 && (
            <span className="slip-toolbar-note"> · paired orders share one slip</span>
          )}
          {failed.length > 0 && (
            <span className="slip-toolbar-note" style={{ color: '#b00' }}>
              {' '}· {failed.length} {failed.length === 1 ? 'order' : 'orders'} couldn&apos;t load and {failed.length === 1 ? 'is' : 'are'} left out
            </span>
          )}
        </span>
        {packages.length > 0 && (
          <button type="button" onClick={() => window.print()}>Print all</button>
        )}
      </div>
      {packages.map((pkg) => (
        <PackingSlip key={pkg.map((o) => o.id).join('-')} orders={pkg} />
      ))}
    </div>
  )
}
