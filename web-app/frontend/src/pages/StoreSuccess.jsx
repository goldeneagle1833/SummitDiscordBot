import { Link, useSearchParams } from 'react-router-dom'
import usePageTitle from '@/hooks/usePageTitle'

export default function StoreSuccess() {
  usePageTitle('Order confirmed')
  const [params] = useSearchParams()
  const orderNumber = params.get('order')

  return (
    <div className="max-w-lg mx-auto text-center py-16">
      <div className="text-5xl mb-4">🎉</div>
      <h1 className="text-2xl font-display text-secondary mb-2">Thanks for your order!</h1>
      {orderNumber && (
        <p className="text-text-muted mb-1">
          Order <span className="text-text font-mono">{orderNumber}</span>
        </p>
      )}
      <p className="text-text-muted mb-6">
        A confirmation is on its way. We'll send tracking as soon as it ships.
      </p>
      <div className="flex justify-center gap-4">
        <Link to="/store/orders" className="bg-primary hover:bg-primary-dark text-white font-medium px-5 py-2 rounded transition-colors">
          View my orders
        </Link>
        <Link to="/store" className="px-5 py-2 rounded border border-border hover:bg-bg-surface transition-colors">
          Back to store
        </Link>
      </div>
    </div>
  )
}
