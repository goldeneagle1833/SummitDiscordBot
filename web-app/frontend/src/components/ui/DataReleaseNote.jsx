import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { get } from '@/api/client'

const fmt = (iso) => {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC',
  })
}

// "Data through Oct 31, 2026 · next update Nov 15, 2026": these pages are
// released in the same half-month batches as the Meta Report.
export default function DataReleaseNote({ className = '' }) {
  const [info, setInfo] = useState(null)

  useEffect(() => {
    let cancelled = false
    get('/api/data-release')
      .then((d) => { if (!cancelled && d?.through) setInfo(d) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

  if (!info) return null
  return (
    <p className={`text-xs text-text-muted ${className}`}>
      Data through <span className="text-text-primary">{fmt(info.through)}</span>
      {' · '}next update {fmt(info.next_release)}, with the{' '}
      <Link to="/meta-report" className="text-secondary hover:underline">Meta Report</Link>
    </p>
  )
}
