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
      <h1 className="text-2xl font-display text-secondary mb-4">Season {seasonId}</h1>
      <LeaderboardTable data={data?.leaderboard || data || []} />
    </div>
  )
}
