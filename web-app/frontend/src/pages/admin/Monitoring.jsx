import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import usePageTitle from '@/hooks/usePageTitle'
import Spinner from '@/components/ui/Spinner'
import { getMonitoring } from '@/api/admin'
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, Legend,
  ResponsiveContainer, CartesianGrid,
} from 'recharts'

const RANGES = [
  { label: '1h', hours: 1 },
  { label: '6h', hours: 6 },
  { label: '24h', hours: 24 },
  { label: '7d', hours: 168 },
]
const REFRESH_MS = 60000

// Validated against the #161b22 surface (dark mode): lightness band, CVD separation, contrast
const SERIES = { blue: '#388bfd', amber: '#c08a1e', violet: '#a371f7' }
const STATUS = { ok: '#3fb950', degraded: '#d29922', down: '#f85149' }
const STATUS_ICON = { ok: '✓', degraded: '!', down: '✕' }

const CHART_STYLE = {
  grid: { stroke: 'rgba(255,255,255,0.05)' },
  axis: { tick: { fill: 'rgba(255,255,255,0.4)', fontSize: 10 }, tickLine: false, axisLine: false },
  tooltip: {
    contentStyle: { background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 4, fontSize: 11 },
    labelStyle: { color: '#f0f6fc' },
  },
}

export function formatMs(value, count) {
  if (value == null) return count ? '> 30s' : '—'
  return value >= 1000 ? `${(value / 1000).toFixed(value >= 10000 ? 0 : 1)}s` : `${Math.round(value)}ms`
}

export function formatUptime(seconds) {
  if (seconds == null) return '—'
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d) return `${d}d ${h}h`
  if (h) return `${h}h ${m}m`
  return `${m}m`
}

function formatTick(t, hours) {
  const d = new Date(t * 1000)
  if (hours > 24) return d.toLocaleDateString('en-US', { weekday: 'short', hour: 'numeric' })
  return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
}

function formatTs(t) {
  return new Date(t * 1000).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', second: '2-digit' })
}

function StatusBadge({ status }) {
  const color = STATUS[status] || STATUS.degraded
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-sm font-semibold border"
      style={{ color, borderColor: color, background: `${color}1a` }}>
      <span aria-hidden>{STATUS_ICON[status] || '?'}</span>
      {status ? status.toUpperCase() : 'UNKNOWN'}
    </span>
  )
}

function StatTile({ label, value, sub, warn }) {
  return (
    <div className="bg-bg-raised border border-border rounded-lg p-4">
      <div className="text-xs text-text-muted">{label}</div>
      <div className="text-2xl font-bold text-text-primary mt-1 flex items-center gap-2">
        {value}
        {warn && <span className="text-xs font-semibold px-1.5 py-0.5 rounded" style={{ color: STATUS.degraded, background: `${STATUS.degraded}1a` }}>! high</span>}
      </div>
      {sub && <div className="text-xs text-text-muted mt-1">{sub}</div>}
    </div>
  )
}

function ChartPanel({ title, subtitle, empty, children }) {
  return (
    <div className="bg-bg-raised border border-border rounded-lg p-4">
      <h3 className="text-sm font-semibold">{title}</h3>
      {subtitle && <p className="text-xs text-text-muted mb-2">{subtitle}</p>}
      {empty
        ? <div className="h-[200px] flex items-center justify-center text-sm text-text-muted">No data in this range yet</div>
        : <ResponsiveContainer width="100%" height={200}>{children}</ResponsiveContainer>}
    </div>
  )
}

function Section({ title, subtitle, children, right }) {
  return (
    <section className="space-y-2">
      <div className="flex items-end justify-between gap-2 flex-wrap">
        <div>
          <h2 className="text-lg font-semibold text-text-primary">{title}</h2>
          {subtitle && <p className="text-xs text-text-muted">{subtitle}</p>}
        </div>
        {right}
      </div>
      {children}
    </section>
  )
}

function Table({ columns, rows, rowKey, emptyText = 'Nothing to show' }) {
  return (
    <div className="overflow-x-auto bg-bg-raised border border-border rounded-lg">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border text-text-muted">
            {columns.map(c => (
              <th key={c.key} className={`py-2 px-3 font-medium whitespace-nowrap ${c.align === 'right' ? 'text-right' : 'text-left'}`}>
                {c.onSort
                  ? <button onClick={c.onSort} className={`hover:text-text-primary ${c.active ? 'text-secondary' : ''}`}>{c.label}{c.active ? ' ↓' : ''}</button>
                  : c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr><td colSpan={columns.length} className="py-4 text-center text-text-muted">{emptyText}</td></tr>
          )}
          {rows.map(r => (
            <tr key={rowKey(r)} className="border-b border-border/30 hover:bg-white/[0.02]">
              {columns.map(c => (
                <td key={c.key} className={`py-1.5 px-3 ${c.align === 'right' ? 'text-right tabular-nums' : ''} ${c.className || ''}`}>
                  {c.render ? c.render(r) : r[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const ENDPOINT_SORTS = {
  total_s: 'Total time',
  count: 'Requests',
  p95_ms: 'p95',
  errors_5xx: '5xx',
}

export default function Monitoring() {
  usePageTitle('Monitoring')
  const [hours, setHours] = useState(24)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [updatedAt, setUpdatedAt] = useState(null)
  const [endpointSort, setEndpointSort] = useState('total_s')
  const [endpointFilter, setEndpointFilter] = useState('')

  const load = useCallback(() => {
    getMonitoring(hours)
      .then(d => { setData(d); setError(null); setUpdatedAt(new Date()) })
      .catch(e => setError(e.message || 'Failed to load monitoring data'))
      .finally(() => setLoading(false))
  }, [hours])

  useEffect(() => {
    setLoading(true)
    load()
    const id = setInterval(load, REFRESH_MS)
    return () => clearInterval(id)
  }, [load])

  const endpoints = useMemo(() => {
    if (!data) return []
    const q = endpointFilter.trim().toLowerCase()
    return data.endpoints
      .filter(e => !q || e.endpoint.toLowerCase().includes(q))
      // Overflow p95 (null with requests) sorts as slowest
      .sort((a, b) => (b[endpointSort] ?? Infinity) - (a[endpointSort] ?? Infinity))
      .slice(0, 50)
  }, [data, endpointSort, endpointFilter])

  if (loading && !data) return <Spinner className="py-20" />
  if (error && !data) return <div className="text-center py-20 text-accent-red">{error}</div>
  if (!data) return null

  const { health, totals, resources_now: now } = data
  const tick = t => formatTick(t, hours)
  const tooltipLabel = t => formatTs(t)
  const checks = Object.entries(health.checks).map(([name, c]) => ({ name, ...c }))
  const failing = checks.filter(c => !c.ok)

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <Link to="/admin/audit-log" className="text-xs text-text-muted hover:text-text-primary">← Admin</Link>
          <h1 className="text-2xl font-display text-secondary">Monitoring</h1>
          <p className="text-sm text-text-muted">API performance, outbound services, and server resources</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex rounded-md border border-border overflow-hidden" role="group" aria-label="Time range">
            {RANGES.map(r => (
              <button key={r.hours} onClick={() => setHours(r.hours)}
                className={`px-3 py-1.5 text-sm ${hours === r.hours ? 'bg-secondary text-bg-dark font-semibold' : 'bg-bg-raised text-text-muted hover:text-text-primary'}`}>
                {r.label}
              </button>
            ))}
          </div>
          <div className="text-xs text-text-muted text-right">
            {updatedAt && <>Updated {updatedAt.toLocaleTimeString()}<br /></>}
            {error ? <span className="text-accent-red">Refresh failed</span> : 'Auto-refresh 60s'}
          </div>
        </div>
      </div>

      {/* Health */}
      <div className="bg-bg-raised border border-border rounded-lg p-4 flex items-center gap-4 flex-wrap">
        <StatusBadge status={health.status} />
        <div className="text-sm text-text-muted">
          v{health.version} · worker uptime {formatUptime(health.uptime_s)}
        </div>
        <div className="text-sm flex-1 min-w-[200px]">
          {failing.length === 0
            ? <span className="text-text-muted">All {checks.length} checks passing</span>
            : <span>Failing: {failing.map(c => <code key={c.name} className="mx-1 px-1.5 py-0.5 rounded bg-bg-dark text-xs">{c.name} ({c.detail})</code>)}</span>}
        </div>
      </div>

      {/* Headline numbers */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatTile label="Requests" value={totals.count.toLocaleString()} sub={`${totals.errors_4xx.toLocaleString()} 4xx`} />
        <StatTile label="5xx error rate" value={`${totals.error_rate_5xx}%`} sub={`${totals.errors_5xx.toLocaleString()} server errors`} warn={totals.error_rate_5xx >= 5} />
        <StatTile label="Latency p95" value={formatMs(totals.p95_ms, totals.count)} sub={`avg ${formatMs(totals.avg_ms, totals.count)} · max ${formatMs(totals.max_ms, totals.count)}`} />
        <StatTile label="Worker memory" value={now ? `${Math.round(now.total_rss_mb)} MB` : '—'} sub={now ? `${now.workers.length} worker${now.workers.length === 1 ? '' : 's'}` : 'no recent sample'} />
        <StatTile label="Host memory" value={now?.sys_mem_percent != null ? `${now.sys_mem_percent}%` : '—'} sub={now?.sys_mem_available_mb != null ? `${Math.round(now.sys_mem_available_mb)} MB free` : null} warn={now?.sys_mem_percent >= 90} />
        <StatTile label="Disk" value={now ? `${now.disk_percent}%` : '—'} sub={now ? `${now.disk_free_gb} GB free` : null} warn={now?.disk_percent >= 90} />
      </div>

      {/* Charts */}
      <Section title="API traffic" subtitle="All Flask requests (nginx-served SPA and images excluded)">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <ChartPanel title="Requests" empty={!data.traffic.length}>
            <BarChart data={data.traffic}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.grid.stroke} vertical={false} />
              <XAxis dataKey="t" tickFormatter={tick} {...CHART_STYLE.axis} minTickGap={30} />
              <YAxis {...CHART_STYLE.axis} width={40} allowDecimals={false} />
              <Tooltip {...CHART_STYLE.tooltip} labelFormatter={tooltipLabel} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
              <Bar dataKey="count" name="Requests" fill={SERIES.blue} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ChartPanel>
          <ChartPanel title="Errors" empty={!data.traffic.length}>
            <BarChart data={data.traffic}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.grid.stroke} vertical={false} />
              <XAxis dataKey="t" tickFormatter={tick} {...CHART_STYLE.axis} minTickGap={30} />
              <YAxis {...CHART_STYLE.axis} width={40} allowDecimals={false} />
              <Tooltip {...CHART_STYLE.tooltip} labelFormatter={tooltipLabel} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="errors_5xx" name="5xx" stackId="e" fill={STATUS.down} />
              <Bar dataKey="errors_4xx" name="4xx" stackId="e" fill={SERIES.amber} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ChartPanel>
          <ChartPanel title="Latency" subtitle="p95 is estimated from latency histogram buckets" empty={!data.traffic.length}>
            <LineChart data={data.traffic}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.grid.stroke} vertical={false} />
              <XAxis dataKey="t" tickFormatter={tick} {...CHART_STYLE.axis} minTickGap={30} />
              <YAxis {...CHART_STYLE.axis} width={48} tickFormatter={v => formatMs(v)} />
              <Tooltip {...CHART_STYLE.tooltip} labelFormatter={tooltipLabel} formatter={v => formatMs(v, 1)} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line dataKey="avg_ms" name="Average" stroke={SERIES.blue} dot={false} strokeWidth={2} />
              <Line dataKey="p95_ms" name="p95" stroke={SERIES.violet} dot={false} strokeWidth={2} connectNulls />
            </LineChart>
          </ChartPanel>
          <ChartPanel title="Worker memory (RSS)" subtitle="Summed across gunicorn workers" empty={!data.resources.length}>
            <LineChart data={data.resources}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.grid.stroke} vertical={false} />
              <XAxis dataKey="t" tickFormatter={tick} {...CHART_STYLE.axis} minTickGap={30} />
              <YAxis {...CHART_STYLE.axis} width={48} tickFormatter={v => `${Math.round(v)}MB`} />
              <Tooltip {...CHART_STYLE.tooltip} labelFormatter={tooltipLabel} formatter={v => `${v} MB`} />
              <Line dataKey="rss_mb" name="RSS" stroke={SERIES.blue} dot={false} strokeWidth={2} />
            </LineChart>
          </ChartPanel>
          <ChartPanel title="Host utilisation" empty={!data.resources.length}>
            <LineChart data={data.resources}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.grid.stroke} vertical={false} />
              <XAxis dataKey="t" tickFormatter={tick} {...CHART_STYLE.axis} minTickGap={30} />
              <YAxis {...CHART_STYLE.axis} width={40} domain={[0, 100]} tickFormatter={v => `${v}%`} />
              <Tooltip {...CHART_STYLE.tooltip} labelFormatter={tooltipLabel} formatter={v => `${v}%`} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line dataKey="sys_cpu_percent" name="CPU" stroke={SERIES.blue} dot={false} strokeWidth={2} />
              <Line dataKey="sys_mem_percent" name="Memory" stroke={SERIES.amber} dot={false} strokeWidth={2} />
              <Line dataKey="disk_percent" name="Disk" stroke={SERIES.violet} dot={false} strokeWidth={2} />
            </LineChart>
          </ChartPanel>
          <ChartPanel title="Worker CPU" subtitle="Summed across workers; 100% = one core" empty={!data.resources.length}>
            <LineChart data={data.resources}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.grid.stroke} vertical={false} />
              <XAxis dataKey="t" tickFormatter={tick} {...CHART_STYLE.axis} minTickGap={30} />
              <YAxis {...CHART_STYLE.axis} width={40} tickFormatter={v => `${v}%`} />
              <Tooltip {...CHART_STYLE.tooltip} labelFormatter={tooltipLabel} formatter={v => `${v}%`} />
              <Line dataKey="cpu_percent" name="CPU" stroke={SERIES.blue} dot={false} strokeWidth={2} />
            </LineChart>
          </ChartPanel>
        </div>
      </Section>

      <Section title="Outbound services" subtitle="Every call the web app makes to Curiosa, Discord, Google, YouTube, the bot API, etc. Errors include timeouts and connection failures.">
        <Table
          rowKey={r => r.service}
          rows={data.external}
          emptyText="No outbound calls in this range"
          columns={[
            { key: 'service', label: 'Service', className: 'font-medium' },
            { key: 'count', label: 'Calls', align: 'right', render: r => r.count.toLocaleString() },
            { key: 'error_rate', label: 'Errors', align: 'right', render: r => <span style={r.errors ? { color: STATUS.down } : undefined}>{r.errors} ({r.error_rate}%)</span> },
            { key: 'avg_ms', label: 'Avg', align: 'right', render: r => formatMs(r.avg_ms, r.count) },
            { key: 'p95_ms', label: 'p95', align: 'right', render: r => formatMs(r.p95_ms, r.count) },
            { key: 'max_ms', label: 'Max', align: 'right', render: r => formatMs(r.max_ms, r.count) },
          ]}
        />
      </Section>

      <Section
        title="Endpoints"
        subtitle="Top 50. Sort by total time to find what's costing the workers the most."
        right={
          <input value={endpointFilter} onChange={e => setEndpointFilter(e.target.value)} placeholder="Filter endpoints…"
            className="bg-bg-dark border border-border rounded px-2 py-1 text-sm w-56 max-w-full" />
        }
      >
        <Table
          rowKey={r => `${r.method} ${r.endpoint}`}
          rows={endpoints}
          columns={[
            { key: 'endpoint', label: 'Endpoint', className: 'font-mono whitespace-nowrap', render: r => <><span className="text-text-muted">{r.method}</span> {r.endpoint}</> },
            { key: 'count', label: ENDPOINT_SORTS.count, align: 'right', onSort: () => setEndpointSort('count'), active: endpointSort === 'count', render: r => r.count.toLocaleString() },
            { key: 'total_s', label: ENDPOINT_SORTS.total_s, align: 'right', onSort: () => setEndpointSort('total_s'), active: endpointSort === 'total_s', render: r => `${r.total_s}s` },
            { key: 'avg_ms', label: 'Avg', align: 'right', render: r => formatMs(r.avg_ms, r.count) },
            { key: 'p95_ms', label: ENDPOINT_SORTS.p95_ms, align: 'right', onSort: () => setEndpointSort('p95_ms'), active: endpointSort === 'p95_ms', render: r => <span style={(r.p95_ms == null || r.p95_ms > data.slow_request_ms) ? { color: STATUS.degraded } : undefined}>{formatMs(r.p95_ms, r.count)}</span> },
            { key: 'max_ms', label: 'Max', align: 'right', render: r => formatMs(r.max_ms, r.count) },
            { key: 'errors_4xx', label: '4xx', align: 'right' },
            { key: 'errors_5xx', label: ENDPOINT_SORTS.errors_5xx, align: 'right', onSort: () => setEndpointSort('errors_5xx'), active: endpointSort === 'errors_5xx', render: r => <span style={r.errors_5xx ? { color: STATUS.down } : undefined}>{r.errors_5xx}</span> },
          ]}
        />
      </Section>

      <Section title="Recent server errors" subtitle="Unhandled exceptions and 5xx responses. Request ID matches the X-Request-ID header and the gunicorn access log (rid=).">
        <Table
          rowKey={r => `${r.ts}-${r.request_id}-${r.endpoint}`}
          rows={data.errors}
          emptyText="No server errors in this range"
          columns={[
            { key: 'ts', label: 'When', className: 'whitespace-nowrap', render: r => formatTs(r.ts) },
            { key: 'endpoint', label: 'Request', className: 'font-mono whitespace-nowrap', render: r => <><span className="text-text-muted">{r.method}</span> {r.path}</> },
            { key: 'status', label: 'Status', align: 'right' },
            { key: 'error_type', label: 'Type', className: 'whitespace-nowrap' },
            { key: 'message', label: 'Message', className: 'font-mono text-text-muted max-w-md truncate', render: r => <span title={r.message}>{r.message}</span> },
            { key: 'request_id', label: 'Request ID', className: 'font-mono text-text-muted whitespace-nowrap' },
          ]}
        />
      </Section>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Section title="Health checks">
          <Table
            rowKey={r => r.name}
            rows={checks}
            columns={[
              { key: 'name', label: 'Check', className: 'font-mono' },
              { key: 'ok', label: 'Status', render: r => <span style={{ color: r.ok ? STATUS.ok : STATUS.down }}>{r.ok ? '✓ pass' : '✕ fail'}</span> },
              { key: 'detail', label: 'Detail', className: 'text-text-muted' },
              { key: 'ms', label: 'Time', align: 'right', render: r => (r.ms != null ? `${r.ms}ms` : '') },
            ]}
          />
        </Section>
        <Section title="Workers" subtitle="Latest sample per gunicorn worker">
          <Table
            rowKey={r => r.pid}
            rows={now?.workers || []}
            emptyText="No sample in the last 3 minutes"
            columns={[
              { key: 'pid', label: 'PID', className: 'font-mono' },
              { key: 'rss_mb', label: 'RSS', align: 'right', render: r => (r.rss_mb != null ? `${r.rss_mb} MB` : '—') },
              { key: 'cpu_percent', label: 'CPU', align: 'right', render: r => (r.cpu_percent != null ? `${r.cpu_percent}%` : '—') },
              { key: 'threads', label: 'Threads', align: 'right' },
              { key: 'open_fds', label: 'FDs', align: 'right', render: r => r.open_fds ?? '—' },
            ]}
          />
          {now?.load_1m != null && <p className="text-xs text-text-muted">Load average (1m): {now.load_1m}</p>}
        </Section>
        <Section title="Databases" subtitle="File size including WAL/SHM">
          <Table
            rowKey={r => r.name}
            rows={data.databases}
            columns={[
              { key: 'name', label: 'Database', className: 'font-mono' },
              { key: 'size_mb', label: 'Size', align: 'right', render: r => (r.exists ? `${r.size_mb} MB` : <span className="text-text-muted">missing</span>) },
            ]}
          />
        </Section>
      </div>
    </div>
  )
}
