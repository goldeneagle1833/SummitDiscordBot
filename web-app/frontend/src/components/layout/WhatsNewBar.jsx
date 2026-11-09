import { Link } from 'react-router-dom'
import { useArrival } from '@/hooks/useNewContent'
import { dismissArrival } from '@/utils/newContent'

// Bar under the menu on a page opened from a new-content dot: says what's new
export default function WhatsNewBar({ pageKey, pathname }) {
  const arrival = useArrival(pageKey)
  if (!arrival || arrival.dismissed || !arrival.note?.text) return null
  const { text, link } = arrival.note
  // No link when it would just reload this page
  const showLink = link && link !== pathname
  return (
    <div className="bg-bg-elevated border-b border-border" role="status">
      <div className="max-w-content mx-auto px-4 py-2 flex items-center gap-3 text-sm">
        <span className="inline-block w-2 h-2 rounded-full bg-white shrink-0" aria-hidden="true" />
        <span className="flex-1 min-w-0">
          <span className="font-semibold text-text-primary">{text}</span>
          <span className="text-text-muted"> since your last visit</span>
          {showLink && (
            <Link to={link} className="ml-2 text-secondary hover:underline whitespace-nowrap">View →</Link>
          )}
        </span>
        <button
          type="button"
          onClick={() => dismissArrival(pageKey)}
          className="text-text-muted hover:text-text text-lg leading-none px-1"
          aria-label="Dismiss"
        >
          &times;
        </button>
      </div>
    </div>
  )
}
