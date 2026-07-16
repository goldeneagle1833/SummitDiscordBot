import { Link, useSearchParams } from 'react-router-dom'
import usePageTitle from '@/hooks/usePageTitle'

function CheckoutProgress({ step }) {
  const steps = ['Review', 'Payment', 'Confirmed']
  return (
    <div className="flex items-center justify-center gap-1 mb-8">
      {steps.map((label, i) => {
        const stepNum = i + 1
        const active = stepNum === step
        const done = stepNum < step
        return (
          <div key={label} className="flex items-center gap-1">
            {i > 0 && (
              <div className={`w-8 sm:w-12 h-px ${done || active ? 'bg-secondary' : 'bg-border'}`} />
            )}
            <div className="flex items-center gap-1.5">
              <div
                className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                  done
                    ? 'bg-secondary text-black'
                    : active
                      ? 'bg-secondary/20 text-secondary border border-secondary'
                      : 'bg-bg-elevated text-text-muted border border-border'
                }`}
              >
                {done ? (
                  <svg width="12" height="12" viewBox="0 0 12 12"><path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
                ) : (
                  stepNum
                )}
              </div>
              <span className={`text-xs font-medium hidden sm:inline ${active ? 'text-text-primary' : 'text-text-muted'}`}>
                {label}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default function StoreSuccess() {
  usePageTitle('Order confirmed')
  const [params] = useSearchParams()
  const orderNumber = params.get('order')

  return (
    <div className="max-w-lg mx-auto text-center py-12">
      <CheckoutProgress step={3} />

      <div className="w-16 h-16 rounded-full bg-accent-green/20 flex items-center justify-center mx-auto mb-5">
        <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
          <path d="M8 16l6 6 10-10" stroke="#2a9c4a" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>

      <h1 className="text-2xl font-display text-secondary mb-2">Thanks for your order!</h1>

      {orderNumber && (
        <div className="inline-block bg-bg-surface border border-border rounded-lg px-4 py-2 mt-2 mb-4">
          <span className="text-xs text-text-muted">Order number</span>
          <p className="text-text-primary font-mono font-medium">{orderNumber}</p>
        </div>
      )}

      <p className="text-text-muted mb-8 max-w-sm mx-auto">
        A confirmation is on its way. We'll send tracking as soon as it ships.
      </p>

      <div className="flex justify-center gap-3">
        <Link
          to="/store/orders"
          className="bg-primary hover:bg-primary-dark text-white font-medium px-5 py-2.5 rounded-lg transition-colors"
        >
          View my orders
        </Link>
        <Link
          to="/store"
          className="px-5 py-2.5 rounded-lg border border-border hover:border-secondary/40 hover:bg-bg-surface transition-all text-text-muted hover:text-text"
        >
          Back to store
        </Link>
      </div>
    </div>
  )
}
