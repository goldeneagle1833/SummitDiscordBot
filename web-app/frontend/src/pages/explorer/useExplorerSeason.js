import { useEffect, useState } from 'react'
import { fetchSeasons, fetchLeaderboard, fetchSeasonEvents, fetchEventsMap } from '@/api/explorer'

/**
 * The newest Explorer series (the API lists newest first) with its standings,
 * events and map points, for the mini-site's home and events pages. Pass a
 * season id to load that one instead.
 */
export default function useExplorerSeason(seasonId = null) {
  const [seasons, setSeasons] = useState([])
  const [activeId, setActiveId] = useState(seasonId)
  const [data, setData] = useState({ leaderboard: null, events: [], mapEvents: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchSeasons()
      .then((list) => {
        setSeasons(list || [])
        if (!activeId && list?.length) setActiveId(list[0].id)
        if (!list?.length) setLoading(false)
      })
      .catch((e) => { setError(e.message); setLoading(false) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!activeId) return
    let alive = true
    setLoading(true)
    Promise.all([
      fetchLeaderboard(activeId).catch(() => null),
      fetchSeasonEvents(activeId).catch(() => []),
      fetchEventsMap(activeId).catch(() => ({ enabled: false, events: [] })),
    ]).then(([leaderboard, events, map]) => {
      if (!alive) return
      setData({
        leaderboard,
        events: events || [],
        mapEvents: map?.enabled ? (map.events || []) : [],
      })
      setLoading(false)
    })
    return () => { alive = false }
  }, [activeId])

  const season = seasons.find((s) => s.id === activeId) || null
  return { seasons, season, activeId, setActiveId, ...data, loading, error }
}

export function formatEventDate(value) {
  if (!value) return null
  const d = new Date(`${String(value).slice(0, 10)}T12:00:00`)
  if (Number.isNaN(d.getTime())) return { month: '', day: '', full: String(value) }
  return {
    month: d.toLocaleString('en-US', { month: 'short' }).toUpperCase(),
    day: String(d.getDate()).padStart(2, '0'),
    full: d.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' }),
  }
}
