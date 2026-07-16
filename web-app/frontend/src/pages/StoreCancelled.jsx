import { Link, useSearchParams } from 'react-router-dom'
import usePageTitle from '@/hooks/usePageTitle'

export default function StoreCancelled() {
  usePageTitle('Checkout cancelled')
  const [params] = useSearchParams()
  const orderNumber = params.get('order')

  return (
    <div className="max-w-lg mx-auto text-center py-16">
      <div className="w-16 h-16 rounded-full bg-bg-elevated border border-border flex items-center justify-center mx-auto mb-5">
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
          <path d="M9 9l10 10M19 9L9 19" stroke="#8b949e" strokeWidth="2.5" strokeLinecap="round" />
        </svg>
      </div>

      <h1 className="text-2xl font-display text-secondary mb-2">Checkout cancelled</h1>
      <p className="text-text-muted mb-2">
        No payment was taken{orderNumber ? <> for order <span className="font-mono">{orderNumber}</span></> : ''}.
      </p>
      <p className="text-text-muted text-sm mb-8">
        Your cart items will be released back to stock shortly. You can start a new checkout any time.
      </p>
      <Link
        to="/store"
        className="inline-flex items-center gap-2 bg-primary hover:bg-primary-dark text-white font-medium px-5 py-2.5 rounded-lg transition-colors"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M10 3L5 8l5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
        Back to store
      </Link>
    </div>
  )
}
