import { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { adminGetOrder, formatMoney } from '@/api/store'
import usePageTitle from '@/hooks/usePageTitle'

// Shown on every slip. Edit here to change the wording.
const SELLER_NAME = 'Sorcerers Summit'
const SITE_NAME = 'sorcererssummit.com'
const QUESTIONS_STEPS = [
  `Log into your account on ${SITE_NAME} and open My Orders to see the status and tracking for this order.`,
  'Message us in the Sorcerers Summit Discord with your order number and a description of the issue.',
  'If you can’t reach us on Discord, reply to the order confirmation email and we’ll get back to you within 48 hours.',
]
const FEEDBACK_INTRO =
  'If there is a problem with your order, please contact us first using the steps on the left so we have a chance to make it right.'
const FEEDBACK_STEPS = [
  'Let us know how we did in the Sorcerers Summit Discord.',
  `Check ${SITE_NAME} for new tokens, events, and community series.`,
]

function fmtDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
}

function addressLines(order) {
  const cityLine =
    [order.ship_city, order.ship_state].filter(Boolean).join(', ') +
    (order.ship_postal ? ` ${order.ship_postal}` : '')
  return [order.ship_name, order.ship_line1, order.ship_line2, cityLine.trim(), order.ship_country !== 'US' ? order.ship_country : '']
    .map((l) => (l || '').trim())
    .filter(Boolean)
}

function shippingMethod(order) {
  if (order.shipping_cents === 0) return 'Free shipping'
  return 'Standard'
}

/**
 * Printable packing slip for one order, laid out like a TCGplayer slip:
 * bold ship-to block for a window envelope, order details, item table,
 * and a help footer. Rendered outside the site layout. Opened with
 * ?print=1 it calls window.print() once the order has loaded.
 */
export default function StoreOrderPrint() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const autoPrint = params.get('print') === '1'
  const [order, setOrder] = useState(null)
  const [error, setError] = useState(null)
  usePageTitle(order ? `Packing slip ${order.order_number}` : 'Packing slip')

  useEffect(() => {
    adminGetOrder(id)
      .then((d) => setOrder(d.order))
      .catch((e) => setError(e.message))
  }, [id])

  useEffect(() => {
    if (!order || !autoPrint) return
    // Let the browser paint before opening the print dialog
    const t = setTimeout(() => {
      try {
        window.print()
      } catch {
        /* jsdom and some embedded browsers have no print() */
      }
    }, 150)
    return () => clearTimeout(t)
  }, [order, autoPrint])

  if (error) {
    return <div className="slip-page"><p>{error}</p></div>
  }
  if (!order) {
    return <div className="slip-page"><p>Loading order…</p></div>
  }

  const items = order.items || []
  const totalQty = items.reduce((n, i) => n + i.quantity, 0)
  const currency = order.currency || 'USD'
  const address = addressLines(order)

  return (
    <div className="slip-page">
      <style>{`
        .slip-page {
          background: #fff;
          color: #000;
          min-height: 100vh;
          font-family: Helvetica, Arial, sans-serif;
          font-size: 10pt;
          line-height: 1.3;
        }
        .slip {
          width: 8.5in;
          min-height: 11in;
          margin: 0 auto;
          padding: 0.5in;
          box-sizing: border-box;
          display: flex;
          flex-direction: column;
        }
        .slip-toolbar {
          width: 8.5in;
          margin: 0 auto;
          padding: 0.25in 0.5in 0;
          box-sizing: border-box;
          display: flex;
          justify-content: space-between;
          align-items: center;
          color: #666;
        }
        .slip-toolbar button {
          background: #000;
          color: #fff;
          border: 0;
          padding: 6px 16px;
          font: inherit;
          cursor: pointer;
        }
        .slip-shipto { font-size: 14pt; font-weight: bold; line-height: 1.15; margin-top: 4px; }
        .slip-order-number { font-size: 14pt; font-weight: bold; margin-top: 0.55in; }
        .slip-thanks { margin-top: 6px; }
        .slip-columns { display: flex; gap: 0.4in; margin-top: 0.3in; }
        .slip-columns > div { flex: 1; }
        .slip-label { font-weight: bold; }
        .slip-kv { display: grid; grid-template-columns: 1.4in 1fr; row-gap: 2px; }
        .slip-table { width: 100%; border-collapse: collapse; margin-top: 0.4in; }
        .slip-table th { text-align: left; font-weight: bold; padding: 3px 4px; border-bottom: 1px solid #000; }
        .slip-table td { padding: 4px; vertical-align: top; }
        .slip-table .num { text-align: right; white-space: nowrap; }
        .slip-table .qty { text-align: center; width: 0.7in; }
        .slip-table tr.total td { border-top: 1px solid #000; }
        .slip-table tr.summary td { padding-top: 1px; padding-bottom: 1px; }
        .slip-table .sku { color: #555; font-size: 8.5pt; }
        .slip-help { display: flex; gap: 0.3in; margin-top: 0.35in; }
        .slip-help > div { flex: 1; }
        .slip-help ol { margin: 4px 0 0; padding-left: 1.3em; }
        .slip-help li { margin-bottom: 4px; }
        .slip-help p { margin: 4px 0 8px; }
        .slip-footer {
          margin-top: auto;
          padding-top: 0.3in;
          display: flex;
          justify-content: space-between;
        }
        @media print {
          html, body { background: #fff !important; color: #000 !important; margin: 0; }
          .slip-toolbar { display: none; }
          .slip-page { min-height: 0; }
          .slip { min-height: 0; height: auto; padding: 0; width: auto; }
          .slip-footer { position: fixed; bottom: 0; left: 0; right: 0; padding: 0; }
          @page { size: letter; margin: 0.5in; }
        }
      `}</style>

      <div className="slip-toolbar">
        <span>Packing slip preview</span>
        <button type="button" onClick={() => window.print()}>Print</button>
      </div>

      <div className="slip">
        <div>Ship To:</div>
        {address.length > 0 ? (
          <div className="slip-shipto">
            {address.map((line, i) => <div key={i}>{line}</div>)}
          </div>
        ) : (
          <div className="slip-shipto" style={{ fontStyle: 'italic', fontWeight: 'normal' }}>
            No shipping address on file
          </div>
        )}

        <div className="slip-order-number">Order Number: {order.order_number}</div>
        <div className="slip-thanks">Thank you for buying from {SELLER_NAME} on {SITE_NAME}.</div>

        <div className="slip-columns">
          <div>
            <div className="slip-label">Shipping Address:</div>
            {address.length > 0 ? (
              address.map((line, i) => <div key={i}>{line}</div>)
            ) : (
              <div>No shipping address on file</div>
            )}
          </div>
          <div className="slip-kv">
            <div>Order Date:</div>
            <div>{fmtDate(order.created_at)}</div>
            <div>Shipping Method:</div>
            <div>
              {shippingMethod(order)}
              {order.tracking_number && (
                <>
                  <br />
                  {order.tracking_carrier ? `${order.tracking_carrier} ` : ''}{order.tracking_number}
                </>
              )}
            </div>
            <div>Buyer Name:</div>
            <div>{order.username}</div>
            {order.email && (
              <>
                <div>Buyer Email:</div>
                <div>{order.email}</div>
              </>
            )}
            <div>Seller Name:</div>
            <div>{SELLER_NAME}</div>
          </div>
        </div>

        <table className="slip-table">
          <thead>
            <tr>
              <th className="qty">Quantity</th>
              <th>Description</th>
              <th className="num">Price</th>
              <th className="num">Total Price</th>
            </tr>
          </thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.id}>
                <td className="qty">{i.quantity}</td>
                <td>
                  {i.product_name}
                  {i.sku && <span className="sku"> ({i.sku})</span>}
                </td>
                <td className="num">{formatMoney(i.unit_price_cents, currency)}</td>
                <td className="num">{formatMoney(i.unit_price_cents * i.quantity, currency)}</td>
              </tr>
            ))}
            <tr className="total">
              <td className="qty">{totalQty}</td>
              <td className="slip-label">Total</td>
              <td />
              <td className="num">{formatMoney(order.subtotal_cents, currency)}</td>
            </tr>
            <tr className="summary">
              <td />
              <td>Shipping</td>
              <td />
              <td className="num">{formatMoney(order.shipping_cents, currency)}</td>
            </tr>
            {order.tax_cents > 0 && (
              <tr className="summary">
                <td />
                <td>Tax</td>
                <td />
                <td className="num">{formatMoney(order.tax_cents, currency)}</td>
              </tr>
            )}
            <tr className="summary">
              <td />
              <td className="slip-label">Order Total</td>
              <td />
              <td className="num slip-label">{formatMoney(order.total_cents, currency)}</td>
            </tr>
          </tbody>
        </table>

        <div className="slip-help">
          <div>
            <div className="slip-label">For Any Questions About Your Order:</div>
            <ol>
              {QUESTIONS_STEPS.map((step, i) => <li key={i}>{step}</li>)}
            </ol>
          </div>
          <div>
            <div className="slip-label">To Provide Feedback for This Order:</div>
            <p>{FEEDBACK_INTRO}</p>
            <ol>
              {FEEDBACK_STEPS.map((step, i) => <li key={i}>{step}</li>)}
            </ol>
          </div>
        </div>

        <div className="slip-footer">
          <span>Order Number: {order.order_number}</span>
          <span>1 of 1</span>
        </div>
      </div>
    </div>
  )
}
