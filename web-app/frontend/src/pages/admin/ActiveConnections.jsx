import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { get } from '@/api/client'
import usePageTitle from '@/hooks/usePageTitle'
import Spinner from '@/components/ui/Spinner'

function parseUA(ua) {
  if (!ua) return { browser: 'Unknown', os: 'Unknown', device: 'Unknown' }

  let browser = 'Unknown'
  if (ua.includes('Edg/')) browser = 'Edge'
  else if (ua.includes('OPR/') || ua.includes('Opera')) browser = 'Opera'
  else if (ua.includes('Chrome/') && !ua.includes('Edg/')) browser = 'Chrome'
  else if (ua.includes('Safari/') && !ua.includes('Chrome')) browser = 'Safari'
  else if (ua.includes('Firefox/')) browser = 'Firefox'

  let os = 'Unknown'
  if (ua.includes('Windows')) os = 'Windows'
  else if (ua.includes('Mac OS')) os = 'macOS'
  else if (ua.includes('Android')) os = 'Android'
  else if (ua.includes('iPhone') || ua.includes('iPad')) os = 'iOS'
  else if (ua.includes('Linux')) os = 'Linux'
  else if (ua.includes('CrOS')) os = 'ChromeOS'

  let device = 'Desktop'
  if (ua.includes('Mobile') || ua.includes('Android') || ua.includes('iPhone')) device = 'Mobile'
  else if (ua.includes('iPad') || ua.includes('Tablet')) device = 'Tablet'

  return { browser, os, device }
}

function timeAgo(ts) {
  if (!ts) return '--'
  const diff = (Date.now() - new Date(ts + 'Z').getTime()) / 1000
  if (diff < 10) return 'just now'
  if (diff < 60) return `${Math.floor(diff)}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  return `${Math.floor(diff / 3600)}h ago`
}

function duration(first, last) {
  if (!first || !last) return '--'
  const diff = (new Date(last + 'Z').getTime() - new Date(first + 'Z').getTime()) / 1000
  if (diff < 60) return `${Math.floor(diff)}s`
  if (diff < 3600) return `${Math.floor(diff / 60)}m`
  return `${Math.floor(diff / 3600)}h ${Math.floor((diff % 3600) / 60)}m`
}

function tzToRegion(tz) {
  if (!tz) return null
  const parts = tz.split('/')
  if (parts.length >= 2) return parts.slice(1).join('/').replace(/_/g, ' ')
  return tz
}

export default function ActiveConnections() {
  usePageTitle('Active Connections')
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    get('/api/analytics/active-sessions')
      .then(d => { if (d.success) setSessions(d.sessions) })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 10000)
    return () => clearInterval(id)
  }, [load])

  const activeCount = sessions.filter(s => {
    const diff = (Date.now() - new Date(s.last_seen + 'Z').getTime()) / 1000
    return diff <= 60
  }).length

  const uniqueIPs = new Set(sessions.map(s => s.ip).filter(Boolean)).size
  const uniqueTZs = new Set(sessions.map(s => s.timezone).filter(Boolean)).size
  const mobileCount = sessions.filter(s => parseUA(s.user_agent).device === 'Mobile').length

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/admin/audit-log" className="text-text-muted hover:text-secondary transition-colors text-sm">&larr; Admin</Link>
        <div>
          <h1 className="text-2xl font-display text-secondary">Active Connections</h1>
          <p className="text-sm text-text-muted">Live view of users on the site — refreshes every 10s</p>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-bg-raised border border-border rounded-lg p-4 text-center relative">
          <div className="absolute top-2 right-2 w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          <div className="text-2xl font-bold text-green-400">{activeCount}</div>
          <div className="text-xs text-text-muted mt-1">Active Now</div>
        </div>
        <div className="bg-bg-raised border border-border rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-secondary">{sessions.length}</div>
          <div className="text-xs text-text-muted mt-1">Total Sessions</div>
        </div>
        <div className="bg-bg-raised border border-border rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-secondary">{uniqueIPs}</div>
          <div className="text-xs text-text-muted mt-1">Unique IPs</div>
        </div>
        <div className="bg-bg-raised border border-border rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-secondary">{mobileCount}</div>
          <div className="text-xs text-text-muted mt-1">Mobile</div>
        </div>
      </div>

      {loading ? <Spinner className="py-12" /> : sessions.length === 0 ? (
        <p className="text-text-muted text-sm py-8 text-center">No active connections.</p>
      ) : (
        <div className="bg-bg-raised border border-border rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border text-text-muted bg-bg-surface">
                  <th className="py-2 px-3 text-left">Status</th>
                  <th className="py-2 px-3 text-left">Session</th>
                  <th className="py-2 px-3 text-left">IP</th>
                  <th className="py-2 px-3 text-left">Page</th>
                  <th className="py-2 px-3 text-left">Browser</th>
                  <th className="py-2 px-3 text-left">OS</th>
                  <th className="py-2 px-3 text-left">Device</th>
                  <th className="py-2 px-3 text-left">Location</th>
                  <th className="py-2 px-3 text-left">Duration</th>
                  <th className="py-2 px-3 text-left">Last Seen</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((s, i) => {
                  const { browser, os, device } = parseUA(s.user_agent)
                  const isActive = (Date.now() - new Date(s.last_seen + 'Z').getTime()) / 1000 <= 60
                  return (
                    <tr key={i} className="border-b border-border/30 hover:bg-bg-surface/50 transition-colors">
                      <td className="py-2 px-3">
                        <div className={`w-2 h-2 rounded-full ${isActive ? 'bg-green-400' : 'bg-yellow-500 opacity-50'}`} />
                      </td>
                      <td className="py-2 px-3 font-mono text-text-muted">{s.session_id}</td>
                      <td className="py-2 px-3 font-mono">{s.ip || '--'}</td>
                      <td className="py-2 px-3 font-mono text-secondary">{s.path || '--'}</td>
                      <td className="py-2 px-3">{browser}</td>
                      <td className="py-2 px-3">{os}</td>
                      <td className="py-2 px-3">
                        <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                          device === 'Mobile' ? 'bg-purple-500/20 text-purple-300'
                            : device === 'Tablet' ? 'bg-blue-500/20 text-blue-300'
                            : 'bg-gray-500/20 text-gray-300'
                        }`}>
                          {device}
                        </span>
                      </td>
                      <td className="py-2 px-3 whitespace-nowrap">{tzToRegion(s.timezone) || '--'}</td>
                      <td className="py-2 px-3 whitespace-nowrap text-text-muted">{duration(s.first_seen, s.last_seen)}</td>
                      <td className="py-2 px-3 whitespace-nowrap text-text-muted">{timeAgo(s.last_seen)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {sessions.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-bg-raised border border-border rounded-lg p-4">
            <h3 className="text-sm font-semibold mb-3">By Browser</h3>
            <div className="space-y-1">
              {Object.entries(sessions.reduce((acc, s) => {
                const b = parseUA(s.user_agent).browser
                acc[b] = (acc[b] || 0) + 1
                return acc
              }, {})).sort((a, b) => b[1] - a[1]).map(([name, count]) => (
                <div key={name} className="flex justify-between text-xs">
                  <span>{name}</span>
                  <span className="text-text-muted">{count}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-bg-raised border border-border rounded-lg p-4">
            <h3 className="text-sm font-semibold mb-3">By Timezone</h3>
            <div className="space-y-1">
              {Object.entries(sessions.reduce((acc, s) => {
                const tz = s.timezone || 'Unknown'
                acc[tz] = (acc[tz] || 0) + 1
                return acc
              }, {})).sort((a, b) => b[1] - a[1]).map(([name, count]) => (
                <div key={name} className="flex justify-between text-xs">
                  <span>{name.replace(/_/g, ' ')}</span>
                  <span className="text-text-muted">{count}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
