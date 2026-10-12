import { useEffect, useState } from 'react'
import { adminGetDashboard, salesSummaryCsvUrl } from '@/api/store'
import OrdersMapModal from './OrdersMapModal'
import { stateName } from './usStates'

const RANGES = [
  { days: 7, label: '7 days' },
  { days: 30, label: '30 days' },
  { days: 90, label: '90 days' },
  { days: 365, label: '12 months' },
]
const COLLAPSE_KEY = 'storeAdmin.salesCollapsed'

const dollars = (cents) =>
  `$${((cents || 0) / 100).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
const dollarsExact = (cents) => `$${((cents || 0) / 100).toFixed(2)}`

function readCollapsed() {
  try { return localStorage.getItem(COLLAPSE_KEY) === '1' } catch { return false }
}

function hoursLabel(h) {
  if (h == null) return '—'
  return h < 48 ? `${Math.round(h)} hours` : `${(h / 24).toFixed(1)} days`
}

function waitedLabel(iso) {
  if (!iso) return ''
  const hours = (Date.now() - new Date(iso).getTime()) / 3600000
  return `oldest waiting ${hoursLabel(Math.max(0, hours))}`
}

function Delta({ now, before, days }) {
  if (!before) return <div className="text-xs text-text-muted">No sales the {days} days before</div>
  const pct = Math.round(((now - before) / before) * 100)
  const cls = pct > 0 ? 'text-accent-green' : pct < 0 ? 'text-accent-red' : 'text-text-muted'
  return (
    <div className={`text-xs tabular-nums ${cls}`}>
      {pct > 0 ? '▲ ' : pct < 0 ? '▼ ' : ''}{Math.abs(pct)}% vs the {days} days before
    </div>
  )
}

function Kpi({ label, value, money, delta }) {
  return (
    <div className="bg-bg-base border border-border rounded-lg px-4 py-3">
      <div className="text-xs uppercase tracking-wider text-text-muted">{label}</div>
      <div className={`text-2xl font-semibold tabular-nums ${money ? 'text-secondary' : ''}`}>{value}</div>
      {delta}
    </div>
  )
}

function Card({ title, children, className = '' }) {
  return (
    <div className={`bg-bg-base border border-border rounded-lg px-4 py-3 min-w-0 ${className}`}>
      <h3 className="text-xs uppercase tracking-wider text-text-muted font-medium mb-2">{title}</h3>
      {children}
    </div>
  )
}

function SalesChart({ daily }) {
  const W = 600, H = 160, left = 44, bottom = 18
  const max = Math.max(1, ...daily.map((d) => d.sales_cents + d.unfinished_cents))
  const step = (W - left) / daily.length
  const bw = Math.max(1, step * 0.7)
  const y = (v) => (H - bottom) - (v / max) * (H - bottom - 8)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-40" preserveAspectRatio="none" role="img" aria-label="Sales by day">
      {[0.5, 1].map((f) => (
        <g key={f}>
          <line x1={left} x2={W} y1={y(max * f)} y2={y(max * f)} stroke="#30363d" strokeDasharray="3 3" />
          <text x={left - 6} y={y(max * f) + 4} fill="#8b949e" fontSize="11" textAnchor="end">{dollars(max * f)}</text>
        </g>
      ))}
      <line x1={left} x2={W} y1={H - bottom} y2={H - bottom} stroke="#30363d" />
      {daily.map((d, i) => {
        const x = left + i * step + (step - bw) / 2
        return (
          <g key={d.date}>
            <title>{`${d.date}: ${dollarsExact(d.sales_cents)} paid, ${dollarsExact(d.unfinished_cents)} not finished`}</title>
            <rect x={x} y={y(d.sales_cents)} width={bw} height={(H - bottom) - y(d.sales_cents)} fill="#ffd700" />
            <rect x={x} y={y(d.sales_cents + d.unfinished_cents)} width={bw}
              height={y(d.sales_cents) - y(d.sales_cents + d.unfinished_cents)} fill="#4a68b8" opacity="0.7" />
          </g>
        )
      })}
      <text x={left} y={H - 3} fill="#8b949e" fontSize="11">{daily[0]?.date}</text>
      <text x={W} y={H - 3} fill="#8b949e" fontSize="11" textAnchor="end">Today</text>
    </svg>
  )
}

function Attention({ a }) {
  const lowNames = a.low_stock.map((p) => (p.stock === 0 ? `${p.name} (sold out)` : `${p.name} (${p.stock} left)`))
  const items = [
    { tone: a.to_ship ? 'border-l-yellow-500' : 'border-l-accent-green', n: a.to_ship, label: a.to_ship === 1 ? 'order to ship' : 'orders to ship', sub: waitedLabel(a.oldest_to_ship_at) },
    { tone: 'border-l-border', n: a.awaiting_payment, label: 'checkouts awaiting payment', sub: 'stock held up to 1 hour' },
    { tone: 'border-l-border', n: a.unfinished_week, label: 'unfinished checkouts this week', sub: a.unfinished_week ? `${dollars(a.unfinished_week_cents)} not completed` : '' },
    { tone: a.low_stock.length ? 'border-l-yellow-500' : 'border-l-accent-green', n: a.low_stock.length, label: a.low_stock.length === 1 ? 'product low or sold out' : 'products low or sold out', sub: lowNames.join(', ') },
    { tone: a.flagged ? 'border-l-accent-red' : 'border-l-accent-green', n: a.flagged, label: 'payments flagged (30 days)', sub: a.flagged ? 'check the audit log and Stripe' : 'all clear' },
  ]
  return (
    <ul className="space-y-2">
      {items.map((it) => (
        <li key={it.label} className={`flex flex-wrap items-baseline gap-x-2 bg-bg-surface border-l-[3px] ${it.tone} rounded px-3 py-2 text-sm`}>
          <b className="tabular-nums w-6 text-right">{it.n}</b>
          <span>{it.label}</span>
          {it.sub && <span className="text-xs text-text-muted ml-auto">{it.sub}</span>}
        </li>
      ))}
    </ul>
  )
}

function WhereItShips({ states, onOpenMap }) {
  const total = states.reduce((a, s) => a + s.orders, 0)
  return (
    <button
      type="button"
      onClick={onOpenMap}
      className="text-left w-full bg-bg-base border border-border hover:border-primary rounded-lg px-4 py-3 min-w-0 transition-colors"
      aria-label="Where it ships. Open the order map"
    >
      <div className="flex items-baseline justify-between gap-2 mb-2">
        <h3 className="text-xs uppercase tracking-wider text-text-muted font-medium">Where it ships</h3>
        <span className="text-xs text-primary">Open map</span>
      </div>
      {states.length === 0 ? (
        <p className="text-sm text-text-muted">No orders in this range.</p>
      ) : (
        <ul className="max-h-48 overflow-y-auto pr-1 space-y-2">
          {states.map((s) => (
            <li key={s.state} className="text-sm">
              <div className="flex justify-between gap-2 tabular-nums">
                <span>{stateName(s.state)}</span>
                <span className="text-text-muted">{s.orders} · {dollars(s.sales_cents)}</span>
              </div>
              <div className="h-1.5 rounded bg-bg-elevated overflow-hidden mt-1">
                <div className="h-full bg-secondary" style={{ width: `${(s.orders / total) * 100}%` }} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </button>
  )
}

function Rows({ rows, empty }) {
  if (!rows.length) return <p className="text-sm text-text-muted">{empty}</p>
  return (
    <table className="w-full text-sm tabular-nums">
      <tbody>
        {rows.map(([a, b, c], i) => (
          <tr key={i} className="border-b border-bg-elevated last:border-0">
            <td className="py-1.5 pr-2">{a}</td>
            {c !== undefined && <td className="py-1.5 pr-3 text-right text-text-muted whitespace-nowrap">{b}</td>}
            <td className="py-1.5 text-right text-secondary whitespace-nowrap">{c !== undefined ? c : b}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function SalesDashboard({ storefrontId, title }) {
  const [days, setDays] = useState(30)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [collapsed, setCollapsed] = useState(readCollapsed)
  const [mapOpen, setMapOpen] = useState(false)

  useEffect(() => {
    let live = true
    setError(null)
    adminGetDashboard(storefrontId, days)
      .then((d) => { if (live) setData(d) })
      .catch((e) => { if (live) setError(e.message) })
    return () => { live = false }
  }, [storefrontId, days])

  const toggle = () => {
    const next = !collapsed
    setCollapsed(next)
    try { localStorage.setItem(COLLAPSE_KEY, next ? '1' : '0') } catch { /* private window */ }
  }

  const t = data?.totals
  const p = data?.previous
  const rangeLabel = RANGES.find((r) => r.days === days)?.label
  const m = data?.money
  const rb = data?.repeat_buyers
  const st = data?.ship_time

  return (
    <section aria-label="Sales" className="bg-bg-surface border border-border rounded-lg p-4 my-3 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">
          <button
            type="button"
            onClick={toggle}
            aria-expanded={!collapsed}
            className="flex items-center gap-2 hover:text-secondary"
          >
            <span aria-hidden="true" className={`inline-block text-text-muted transition-transform ${collapsed ? '' : 'rotate-90'}`}>▸</span>
            {title} sales
            <span className="text-text-muted font-normal text-sm">
              · last {rangeLabel}
              {collapsed && t && ` · ${dollars(t.sales_cents)} from ${t.orders} ${t.orders === 1 ? 'order' : 'orders'}`}
            </span>
          </button>
        </h2>
        {!collapsed && (
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex border border-border rounded overflow-hidden" role="group" aria-label="Date range">
            {RANGES.map((r) => (
              <button
                key={r.days}
                type="button"
                aria-pressed={days === r.days}
                onClick={() => setDays(r.days)}
                className={`px-3 py-1 text-sm border-r border-border last:border-r-0 ${days === r.days ? 'bg-bg-elevated text-text' : 'text-text-muted hover:text-text'}`}
              >
                {r.label}
              </button>
            ))}
          </div>
          <a href={salesSummaryCsvUrl(storefrontId)} className="text-sm text-primary hover:underline" download>
            Monthly sales CSV
          </a>
        </div>
        )}
      </div>

      {!collapsed && error && <p className="text-accent-red text-sm">{error}</p>}
      {!collapsed && !data && !error && <p className="text-sm text-text-muted">Loading sales…</p>}

      {!collapsed && data && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Kpi label="Sales" money value={dollars(t.sales_cents)} delta={<Delta now={t.sales_cents} before={p.sales_cents} days={days} />} />
            <Kpi label="Paid orders" value={t.orders} delta={<Delta now={t.orders} before={p.orders} days={days} />} />
            <Kpi label="Average order" value={dollarsExact(t.average_cents)} delta={<Delta now={t.average_cents} before={p.average_cents} days={days} />} />
            <Kpi label="Items sold" value={t.units} delta={<Delta now={t.units} before={p.units} days={days} />} />
          </div>

          <div className="grid lg:grid-cols-[1.7fr_1fr] gap-3">
            <Card title="Sales by day">
              <SalesChart daily={data.daily} />
              <div className="flex flex-wrap gap-4 text-xs text-text-muted mt-1">
                <span><i className="inline-block w-2.5 h-2.5 rounded-sm bg-secondary mr-1.5 align-[-1px]" />Paid sales</span>
                <span><i className="inline-block w-2.5 h-2.5 rounded-sm bg-brand-blue-light mr-1.5 align-[-1px]" />Checkouts not finished</span>
              </div>
            </Card>
            <Card title="Needs attention"><Attention a={data.attention} /></Card>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
            <Card title="Top products">
              <Rows empty="No sales in this range." rows={data.top_products.map((x) => [x.name, `${x.units} sold`, dollars(x.sales_cents)])} />
            </Card>
            <WhereItShips states={data.states} onOpenMap={() => setMapOpen(true)} />
            <Card title="Money in">
              <Rows empty="" rows={[
                ['Products', dollarsExact(m.products_cents)],
                ['Shipping collected', dollarsExact(m.shipping_cents)],
                ...(m.tax_cents ? [['Tax', dollarsExact(m.tax_cents)]] : []),
                ['Total, before Stripe fees', dollarsExact(m.products_cents + m.shipping_cents + m.tax_cents)],
              ]} />
              <p className="text-xs text-text-muted mt-2">
                {m.refunded_orders
                  ? `${m.refunded_orders} refunded ${m.refunded_orders === 1 ? 'order' : 'orders'} (${dollarsExact(m.refunded_cents)}) not counted.`
                  : 'No refunds in this range.'}
              </p>
            </Card>
            <Card title="Ship time">
              {st.shipped ? (
                <>
                  <div className="text-2xl font-semibold tabular-nums">{hoursLabel(st.average_hours)}</div>
                  <p className="text-sm text-text-muted">
                    average from paid to shipped, over {st.shipped} {st.shipped === 1 ? 'order' : 'orders'}.
                    Median {hoursLabel(st.median_hours)}. {Math.round((st.within_2_days / st.shipped) * 100)}% shipped within 2 days.
                  </p>
                </>
              ) : <p className="text-sm text-text-muted">Nothing shipped in this range.</p>}
            </Card>
            <Card title="Repeat buyers">
              <p className="text-sm mb-2">
                <b className="tabular-nums">{rb.repeat}</b> of {rb.buyers} {rb.buyers === 1 ? 'buyer' : 'buyers'} ordered more than once.
              </p>
              <Rows empty="No buyers in this range." rows={rb.best.map((b) => [b.username, `${b.orders} ${b.orders === 1 ? 'order' : 'orders'}`, dollars(b.spent_cents)])} />
            </Card>
            <Card title="Monthly limit hits">
              {data.limit_hits.length ? (
                <>
                  <Rows empty="" rows={data.limit_hits.map((h) => [h.name, `limit ${h.cap} · ${h.buyers} ${h.buyers === 1 ? 'buyer' : 'buyers'}`, `${h.hits} ${h.hits === 1 ? 'hit' : 'hits'}`])} />
                  <p className="text-xs text-text-muted mt-2">A hit is one buyer reaching a product&apos;s monthly limit in a month. Lots of hits can mean the limit is too low.</p>
                </>
              ) : <p className="text-sm text-text-muted">No products have a monthly limit.</p>}
            </Card>
          </div>
        </>
      )}
      {mapOpen && (
        <OrdersMapModal
          storefrontId={storefrontId}
          days={days}
          rangeLabel={rangeLabel}
          title={title}
          onClose={() => setMapOpen(false)}
        />
      )}
    </section>
  )
}
