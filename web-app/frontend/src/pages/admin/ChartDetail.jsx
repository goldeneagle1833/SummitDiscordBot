import { useState, useEffect, useMemo, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { get } from '@/api/client'
import usePageTitle from '@/hooks/usePageTitle'
import Spinner from '@/components/ui/Spinner'
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, Legend,
  ResponsiveContainer, CartesianGrid,
} from 'recharts'

const CHART_STYLE = {
  grid: { stroke: 'rgba(255,255,255,0.05)' },
  axis: { tick: { fill: 'rgba(255,255,255,0.4)', fontSize: 10 }, tickLine: false, axisLine: false },
  tooltip: { contentStyle: { background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 4, fontSize: 11 } },
}

const RANGE_FILTERS = [
  { label: 'All Time', value: null, mode: 'weekly' },
  { label: '1 Hour', value: 1, mode: 'hourly' },
  { label: '12 Hours', value: 12, mode: 'hourly' },
  { label: '24 Hours', value: 24, mode: 'hourly' },
  { label: '4 Weeks', value: 28, mode: 'daily' },
  { label: '12 Weeks', value: 84, mode: 'daily' },
  { label: '26 Weeks', value: 182, mode: 'daily' },
  { label: '52 Weeks', value: 364, mode: 'daily' },
]

const CHARTS = {
  'games-over-time': {
    title: 'Games Over Time',
    weeklyKey: 'games_over_time',
    hourlyKey: 'games_over_time',
    hasSourceFilter: true,
    supportsHourly: true,
  },
  'unique-players': {
    title: 'Unique Players Over Time',
    weeklyKey: 'players_over_time',
    hourlyKey: 'players_over_time',
    supportsHourly: true,
  },
  'new-players': {
    title: 'New Player Acquisition',
    weeklyKey: 'new_players_per_week',
    supportsHourly: false,
  },
  'avg-games-per-player': {
    title: 'Avg Games per Player per Week',
    weeklyKey: 'avg_games_per_player',
    supportsHourly: false,
  },
}

function weekLabel(yw) {
  if (!yw) return ''
  const [year, week] = yw.split('-').map(Number)
  const jan1 = new Date(year, 0, 1)
  const firstMonday = new Date(jan1)
  firstMonday.setDate(jan1.getDate() + ((8 - jan1.getDay()) % 7))
  const target = new Date(firstMonday)
  target.setDate(firstMonday.getDate() + (week - 1) * 7)
  return target.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' })
}

function hourLabel(bucket) {
  if (!bucket) return ''
  const d = new Date(bucket + 'Z')
  return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', hour12: true })
}

function dayLabel(bucket) {
  if (!bucket) return ''
  const [y, m, d] = bucket.split('-').map(Number)
  const date = new Date(y, m - 1, d)
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function renderChart(chartType, data, source) {
  switch (chartType) {
    case 'games-over-time':
      if (source === 'online') {
        return (
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.grid.stroke} />
            <XAxis dataKey="label" {...CHART_STYLE.axis} interval="preserveStartEnd" />
            <YAxis {...CHART_STYLE.axis} />
            <Tooltip {...CHART_STYLE.tooltip} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="bot" name="Online" fill="rgba(77,184,255,0.8)" radius={[2, 2, 2, 2]} />
          </BarChart>
        )
      }
      if (source === 'paper') {
        return (
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.grid.stroke} />
            <XAxis dataKey="label" {...CHART_STYLE.axis} interval="preserveStartEnd" />
            <YAxis {...CHART_STYLE.axis} />
            <Tooltip {...CHART_STYLE.tooltip} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="web" name="Paper" fill="rgba(63,185,80,0.8)" radius={[2, 2, 2, 2]} />
          </BarChart>
        )
      }
      return (
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.grid.stroke} />
          <XAxis dataKey="label" {...CHART_STYLE.axis} interval="preserveStartEnd" />
          <YAxis {...CHART_STYLE.axis} />
          <Tooltip {...CHART_STYLE.tooltip} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Bar dataKey="bot" name="Online" stackId="a" fill="rgba(77,184,255,0.8)" radius={[0, 0, 2, 2]} />
          <Bar dataKey="web" name="Paper" stackId="a" fill="rgba(63,185,80,0.8)" radius={[2, 2, 0, 0]} />
        </BarChart>
      )

    case 'unique-players':
      return (
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.grid.stroke} />
          <XAxis dataKey="label" {...CHART_STYLE.axis} interval="preserveStartEnd" />
          <YAxis {...CHART_STYLE.axis} />
          <Tooltip {...CHART_STYLE.tooltip} />
          <Line dataKey="combined" name="Unique Players" stroke="rgba(168,130,255,0.8)" dot={false} strokeWidth={2} />
        </LineChart>
      )

    case 'new-players':
      return (
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.grid.stroke} />
          <XAxis dataKey="label" {...CHART_STYLE.axis} interval="preserveStartEnd" />
          <YAxis {...CHART_STYLE.axis} />
          <Tooltip {...CHART_STYLE.tooltip} />
          <Bar dataKey="count" name="New Players" fill="rgba(255,136,68,0.8)" radius={[2, 2, 0, 0]} />
        </BarChart>
      )

    case 'avg-games-per-player':
      return (
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.grid.stroke} />
          <XAxis dataKey="label" {...CHART_STYLE.axis} interval="preserveStartEnd" />
          <YAxis {...CHART_STYLE.axis} />
          <Tooltip {...CHART_STYLE.tooltip} />
          <Line dataKey="avg" name="Avg Games/Player" stroke="rgba(219,154,4,0.8)" dot={false} strokeWidth={2} />
        </LineChart>
      )

    default:
      return null
  }
}

export default function ChartDetail() {
  const { chartType } = useParams()
  const chart = CHARTS[chartType]
  usePageTitle(chart?.title || 'Chart Detail')

  const [weeklyData, setWeeklyData] = useState(null)
  const [hourlyData, setHourlyData] = useState(null)
  const [dailyData, setDailyData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [subLoading, setSubLoading] = useState(false)
  const [error, setError] = useState(null)
  const [activeFilter, setActiveFilter] = useState({ value: null, mode: 'weekly' })
  const [source, setSource] = useState('all')

  useEffect(() => {
    get('/api/admin/dashboard-stats')
      .then(setWeeklyData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const handleFilterChange = useCallback((filter) => {
    setActiveFilter(filter)
    if (filter.mode === 'hourly' && chart?.supportsHourly) {
      setSubLoading(true)
      get(`/api/admin/chart-stats-hourly?hours=${filter.value}`)
        .then(setHourlyData)
        .catch((e) => setError(e.message))
        .finally(() => setSubLoading(false))
    } else if (filter.mode === 'daily') {
      setSubLoading(true)
      get(`/api/admin/chart-stats-daily?days=${filter.value}`)
        .then(setDailyData)
        .catch((e) => setError(e.message))
        .finally(() => setSubLoading(false))
    }
  }, [chart])

  const chartData = useMemo(() => {
    if (activeFilter.mode === 'hourly' && chart?.supportsHourly) {
      if (!hourlyData?.success) return []
      const raw = hourlyData[chart.hourlyKey] || []
      return raw.map(d => ({ ...d, label: hourLabel(d.bucket) }))
    }
    if (activeFilter.mode === 'daily') {
      if (!dailyData?.success || !chart) return []
      const key = chart.weeklyKey // daily endpoint uses same keys
      const raw = dailyData[key] || []
      return raw.map(d => ({ ...d, label: dayLabel(d.bucket) }))
    }
    if (!weeklyData?.success || !chart) return []
    const raw = weeklyData[chart.weeklyKey] || []
    const withLabels = raw.map(d => ({ ...d, label: weekLabel(d.week) }))
    if (!activeFilter.value) return withLabels
    return withLabels.slice(-activeFilter.value)
  }, [weeklyData, hourlyData, dailyData, chart, activeFilter])

  const granLabel = activeFilter.mode === 'hourly' ? 'hour' : activeFilter.mode === 'daily' ? 'day' : 'week'

  if (!chart) {
    return (
      <div className="text-center py-12">
        <p className="text-text-muted">Unknown chart type.</p>
        <Link to="/admin/audit-log" className="text-secondary hover:underline text-sm mt-2 inline-block">Back to Dashboard</Link>
      </div>
    )
  }

  if (loading) return <Spinner className="py-12" />
  if (error || !weeklyData?.success) {
    return <p className="text-text-muted text-sm">Failed to load data{error ? `: ${error}` : '.'}</p>
  }

  const availableFilters = RANGE_FILTERS.filter(f =>
    f.mode === 'weekly' || f.mode === 'daily' || chart.supportsHourly
  )

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/admin/audit-log" className="text-text-muted hover:text-secondary transition-colors text-sm">&larr; Dashboard</Link>
      </div>

      <h1 className="text-2xl font-display text-secondary">{chart.title}</h1>

      <div className="flex flex-wrap gap-3">
        <div className="flex items-center gap-1 bg-bg-raised border border-border rounded-lg p-1">
          {availableFilters.map(f => (
            <button
              key={f.label}
              onClick={() => handleFilterChange(f)}
              className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                activeFilter.value === f.value && activeFilter.mode === f.mode
                  ? 'bg-secondary text-bg-base'
                  : 'text-text-muted hover:text-text-primary'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        {chart.hasSourceFilter && (
          <div className="flex items-center gap-1 bg-bg-raised border border-border rounded-lg p-1">
            {[
              { label: 'All', value: 'all' },
              { label: 'Online', value: 'online' },
              { label: 'Paper', value: 'paper' },
            ].map(f => (
              <button
                key={f.value}
                onClick={() => setSource(f.value)}
                className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                  source === f.value
                    ? 'bg-secondary text-bg-base'
                    : 'text-text-muted hover:text-text-primary'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="bg-bg-raised border border-border rounded-lg p-6">
        {subLoading ? (
          <Spinner className="py-20" />
        ) : (
          <ResponsiveContainer width="100%" height={400}>
            {renderChart(chartType, chartData, source)}
          </ResponsiveContainer>
        )}
      </div>

      {!subLoading && chartData.length > 0 && (
        <p className="text-xs text-text-muted">
          Showing {chartData.length} {granLabel}{chartData.length !== 1 ? 's' : ''} of data
        </p>
      )}
    </div>
  )
}
