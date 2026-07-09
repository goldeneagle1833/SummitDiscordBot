import { Link, useSearchParams } from 'react-router-dom'
import usePageTitle from '@/hooks/usePageTitle'

export default function StoreCancelled() {
  usePageTitle('Checkout cancelled')
  const [params] = useSearchParams()
  const orderNumber = params.get('order')

  return (
    <div className="max-w-lg mx-auto text-center py-16">
      <h1 className="text-2xl font-display text-secondary mb-2">Checkout cancelled</h1>
      <p className="text-text-muted mb-6">
        No payment was taken{orderNumber ? <> for order <span className="font-mono">{orderNumber}</span></> : ''}.
        Your items are released back to stock after the checkout window expires.
      </p>
      <Link to="/store" className="bg-primary hover:bg-primary-dark text-white font-medium px-5 py-2 rounded transition-colors">
        Back to store
      </Link>
    </div>
  )
}
