import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import LeaderboardTable from '@/components/leaderboard/LeaderboardTable'
import Spinner from '@/components/ui/Spinner'
import { get } from '@/api/client'
import usePageTitle from '@/hooks/usePageTitle'

export default function Season() {
  usePageTitle('Season')
  const { seasonId } = useParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    get(`/api/seasons/${seasonId}`)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [seasonId])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      <h1 className="text-2xl font-display text-secondary mb-2">
        {data?.title || `Season ${seasonId}`}
      </h1>
      {data?.description && (
        <p className="text-text-muted mb-1">{data.description}</p>
      )}
      <p className="text-sm text-text-muted mb-4">
        {data?.start_date} — {data?.end_date}
        {data?.region && ` · ${data.region}`}
        {data?.creator_display_name && ` · Created by ${data.creator_display_name}`}
        {data?.status === 'ended' && (
          <span className="ml-2 text-xs bg-accent-red/20 text-accent-red px-2 py-0.5 rounded">Ended</span>
        )}
      </p>
      <LeaderboardTable data={data?.leaderboard || []} />
    </div>
  )
}
