import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { getEvent } from '@/api/events'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

export default function StatsEvent() {
  usePageTitle('Event Stats')
  const { folder } = useParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    getEvent(folder)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [folder])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      <h1 className="text-2xl font-display text-secondary mb-4">
        {data?.display_name || folder} Stats
      </h1>
      <pre className="text-sm text-text-muted bg-bg-surface p-4 rounded-soft overflow-auto">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  )
}
