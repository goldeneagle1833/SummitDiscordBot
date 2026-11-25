import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import usePageTitle from '@/hooks/usePageTitle'
import Spinner from '@/components/ui/Spinner'
import { getBotTraffic, blockClient, unblockClient } from '@/api/admin'

const RANGES = [
  { label: '24h', hours: 24 },
  { label: '3d', hours: 72 },
  { label: '7d', hours: 168 },
]

const FILTERS = [
  { key: 'suspect', label: 'Suspicious' },
  { key: 'bots', label: 'All bots' },
  { key: 'all', label: 'Everything' },
]

const KIND_STYLE = {
  search: 'bg-green-500/15 text-green-300',
  preview: 'bg-green-500/15 text-green-300',
  partner: 'bg-blue-500/15 text-blue-300',
  seo: 'bg-amber-500/15 text-amber-300',
  ai: 'bg-amber-500/15 text-amber-300',
  bot: 'bg-orange-500/15 text-orange-300',
  script: 'bg-red-500/15 text-red-300',
  browser: 'bg-white/5 text-text-muted',
}

const fmt = (n) => (n ?? 0).toLocaleString('en-US')

function ago(ts) {
  if (!ts) return '—'
  const s = Math.max(0, Date.now() / 1000 - ts)
  if (s < 3600) return `${Math.round(s / 60)}m ago`
  if (s < 86400) return `${Math.round(s / 3600)}h ago`
  return `${Math.round(s / 86400)}d ago`
}

// A short, readable name for a user agent: the bot's own name when it gives one.
export function shortAgent(ua) {
  if (!ua) return '(no user agent)'
  const named = ua.match(/compatible;\s*([A-Za-z][\w.-]*(?:bot|crawler|spider|agent|Bot|Crawler)[\w./-]*)/)
  if (named) return named[1]
  const bot = ua.match(/([A-Za-z][\w-]*(?:bot|Bot|crawler|Crawler|spider|externalagent|externalhit)[\w./-]*)/)
  if (bot) return bot[1]
  if (!ua.startsWith('Mozilla/')) return ua.length > 60 ? `${ua.slice(0, 60)}…` : ua
  const browser = ua.match(/(HeadlessChrome|Edg|OPR|Firefox|Chrome|Version)\/(\d+)/)
  const os = ua.match(/\((Windows|Macintosh|iPhone|iPad|Linux; Android|X11; Linux|Android)[^)]*\)/)
  const name = browser ? `${browser[1] === 'Version' ? 'Safari' : browser[1]} ${browser[2]}` : 'Browser'
  return os ? `${name} on ${os[1].replace('X11; Linux', 'Linux').replace('Linux; Android', 'Android')}` : name
}

// The word we suggest blocking for an agent: the bot's name, lower-cased.
export function suggestPattern(ua) {
  const name = shortAgent(ua)
  return name.split(/[\s/;(]/)[0].toLowerCase()
}

function Stat({ label, value, tone }) {
  return (
    <div className="bg-bg-surface border border-border rounded-soft p-3">
      <div className="text-xs text-text-muted">{label}</div>
      <div className={`text-xl font-semibold ${tone || 'text-text-primary'}`}>{value}</div>
    </div>
  )
}

function BlockButton({ blocked, busy, onBlock, onUnblock }) {
  if (blocked) {
    return (
      <button type="button" disabled={busy} onClick={onUnblock}
        className="text-xs px-3 py-1.5 rounded-soft border border-border hover:border-primary/60 disabled:opacity-50">
        Unblock
      </button>
    )
  }
  return (
    <button type="button" disabled={busy} onClick={onBlock}
      className="text-xs px-3 py-1.5 rounded-soft bg-accent-red/90 text-white hover:bg-accent-red disabled:opacity-50">
      Block
    </button>
  )
}

function ClientCard({ client, busy, onBlock, onUnblock }) {
  const [open, setOpen] = useState(false)
  return (
    <div className={`bg-bg-surface border rounded-soft p-3 ${client.suspect ? 'border-accent-red/60' : 'border-border'}`}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold text-text-primary break-all">{shortAgent(client.user_agent)}</span>
            <span className={`text-[11px] px-1.5 py-0.5 rounded ${KIND_STYLE[client.kind] || KIND_STYLE.bot}`}>
              {client.kind_label}
            </span>
            {client.suspect && <span className="text-[11px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-300">Looks like scraping</span>}
            {client.block_id && <span className="text-[11px] px-1.5 py-0.5 rounded bg-white/10 text-text-primary">Blocked</span>}
          </div>
          <div className="text-xs text-text-muted mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
            <span>{fmt(client.requests)} requests</span>
            <span>{fmt(client.data_requests)} data</span>
            <span>peak {fmt(client.peak_data_hour)}/hour</span>
            <span>{fmt(client.ips)} {client.ips === 1 ? 'IP' : 'IPs'}</span>
            {client.blocked > 0 && <span>{fmt(client.blocked)} refused</span>}
            <span>last {ago(client.last_seen)}</span>
          </div>
          <button type="button" onClick={() => setOpen(!open)} className="text-[11px] text-text-muted underline mt-1">
            {open ? 'Hide' : 'Full user agent'}
          </button>
          {open && <div className="text-[11px] text-text-muted break-all mt-1 font-mono">{client.user_agent || '(none)'}</div>}
        </div>
        <BlockButton blocked={!!client.block_id} busy={busy} onBlock={onBlock} onUnblock={onUnblock} />
      </div>
    </div>
  )
}

export default function BotTraffic() {
  usePageTitle('Bot Traffic')
  const [hours, setHours] = useState(24)
  const [filter, setFilter] = useState('bots')
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState(null)

  const load = useCallback(() => {
    setError(null)
    getBotTraffic(hours).then(setData).catch((e) => setError(e.message || 'Could not load bot traffic'))
  }, [hours])

  useEffect(() => { load() }, [load])

  const clients = useMemo(() => {
    if (!data) return []
    if (filter === 'suspect') return data.clients.filter((c) => c.suspect || c.block_id)
    if (filter === 'bots') return data.clients.filter((c) => c.kind !== 'browser' || c.suspect || c.block_id)
    return data.clients
  }, [data, filter])

  async function act(fn, done) {
    setBusy(true)
    setNotice(null)
    try {
      await fn()
      setNotice(done)
      load()
    } catch (e) {
      setNotice(e.message || 'That did not work')
    } finally {
      setBusy(false)
    }
  }

  function block(kind, pattern, label) {
    const value = window.prompt(
      kind === 'agent'
        ? `Block every client whose name contains this text (case doesn't matter). Edit it if needed:`
        : `Block this IP address from the site's data:`,
      pattern,
    )
    if (!value) return
    const reason = window.prompt(`Why block ${label}? (optional, goes in the admin log)`, '') || ''
    act(() => blockClient(kind, value, reason), `Blocked ${value}. It takes up to 30 seconds to apply everywhere.`)
  }

  function unblock(id, label) {
    if (!window.confirm(`Unblock ${label}?`)) return
    act(() => unblockClient(id), `Unblocked ${label}.`)
  }

  const activeBlocks = data?.blocks.filter((b) => b.active) || []
  const pastBlocks = data?.blocks.filter((b) => !b.active) || []

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link to="/admin" className="text-xs text-text-muted hover:underline">← Admin</Link>
          <h1 className="text-2xl font-display text-secondary">Bot Traffic</h1>
          <p className="text-sm text-text-muted mt-1 max-w-2xl">
            Who is calling the site's server, grouped by the name their software sends. Blocking refuses all of
            their requests for site data. Pages still load, but nothing on them fills in. Partners with an API key
            are never blocked.
          </p>
        </div>
        <div className="flex gap-1">
          {RANGES.map((r) => (
            <button key={r.hours} type="button" onClick={() => setHours(r.hours)}
              className={`text-xs px-3 py-1.5 rounded-soft border ${hours === r.hours ? 'border-primary text-primary' : 'border-border text-text-muted'}`}>
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {notice && <div className="text-sm bg-bg-surface border border-border rounded-soft p-3">{notice}</div>}
      {error && <div className="text-sm text-red-300">{error}</div>}
      {!data && !error && <Spinner />}

      {data && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Stat label="Bot requests" value={fmt(data.totals.bot_requests)} />
            <Stat label="Different bots" value={fmt(data.totals.bot_clients)} />
            <Stat label="Look like scraping" value={fmt(data.totals.suspects)} tone={data.totals.suspects ? 'text-red-300' : undefined} />
            <Stat label="Requests refused" value={fmt(data.totals.blocked)} />
          </div>
          <p className="text-xs text-text-muted -mt-3">
            Out of {fmt(data.totals.requests)} requests in this period. "Looks like scraping" means more than{' '}
            {fmt(data.thresholds.suspect_data_per_hour)} data requests in one hour, or a script pulling lots of data.
            Search engines and link previews are never flagged.
          </p>

          <section className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-lg font-semibold">Clients</h2>
              <div className="flex gap-1">
                {FILTERS.map((f) => (
                  <button key={f.key} type="button" onClick={() => setFilter(f.key)}
                    className={`text-xs px-3 py-1.5 rounded-soft border ${filter === f.key ? 'border-primary text-primary' : 'border-border text-text-muted'}`}>
                    {f.label}
                  </button>
                ))}
              </div>
            </div>
            {clients.length === 0 && <p className="text-sm text-text-muted">Nothing here for this period.</p>}
            {clients.map((c) => (
              <ClientCard key={c.user_agent} client={c} busy={busy}
                onBlock={() => block('agent', suggestPattern(c.user_agent), shortAgent(c.user_agent))}
                onUnblock={() => unblock(c.block_id, shortAgent(c.user_agent))} />
            ))}
          </section>

          <section className="space-y-2">
            <h2 className="text-lg font-semibold">Busiest IP addresses</h2>
            <p className="text-xs text-text-muted">
              By data requests. This catches a scraper that pretends to be an ordinary browser, which the list above can't.
            </p>
            {data.ips.length === 0 && <p className="text-sm text-text-muted">No addresses recorded yet.</p>}
            {data.ips.map((ip) => (
              <div key={ip.ip} className={`bg-bg-surface border rounded-soft p-3 flex items-start gap-3 ${ip.suspect ? 'border-accent-red/60' : 'border-border'}`}>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-sm text-text-primary">{ip.ip}</span>
                    {ip.suspect && <span className="text-[11px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-300">Looks like scraping</span>}
                    {ip.keyed_requests > 0 && <span className="text-[11px] px-1.5 py-0.5 rounded bg-blue-500/15 text-blue-300">API key</span>}
                    {ip.block_id && <span className="text-[11px] px-1.5 py-0.5 rounded bg-white/10">Blocked</span>}
                  </div>
                  <div className="text-xs text-text-muted mt-1 flex flex-wrap gap-x-3">
                    <span>{fmt(ip.data_requests)} data</span>
                    <span>peak {fmt(ip.peak_data_hour)}/hour</span>
                    <span>{fmt(ip.agents)} {ip.agents === 1 ? 'client' : 'clients'}, mostly {shortAgent(ip.top_agent)}</span>
                    <span>last {ago(ip.last_seen)}</span>
                  </div>
                </div>
                <BlockButton blocked={!!ip.block_id} busy={busy}
                  onBlock={() => block('ip', ip.ip, ip.ip)} onUnblock={() => unblock(ip.block_id, ip.ip)} />
              </div>
            ))}
          </section>

          <section className="space-y-2">
            <h2 className="text-lg font-semibold">Block list</h2>
            {activeBlocks.length === 0 && <p className="text-sm text-text-muted">Nothing is blocked.</p>}
            {activeBlocks.map((b) => (
              <div key={b.id} className="bg-bg-surface border border-border rounded-soft p-3 flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-text-primary">
                    <span className="text-text-muted">{b.kind === 'ip' ? 'IP' : 'Name contains'}</span>{' '}
                    <span className="font-mono">{b.pattern}</span>
                  </div>
                  <div className="text-xs text-text-muted mt-0.5">
                    {b.reason || 'No reason given'} · by {b.created_by || 'unknown'}, {ago(b.created_at)}
                  </div>
                </div>
                <BlockButton blocked busy={busy} onUnblock={() => unblock(b.id, b.pattern)} />
              </div>
            ))}
            {pastBlocks.length > 0 && (
              <details className="text-xs text-text-muted">
                <summary className="cursor-pointer">Lifted blocks ({pastBlocks.length})</summary>
                <ul className="mt-2 space-y-1">
                  {pastBlocks.map((b) => (
                    <li key={b.id} className="flex items-center gap-2">
                      <span className="font-mono">{b.pattern}</span>
                      <span>lifted by {b.removed_by || 'unknown'}, {ago(b.removed_at)}</span>
                      <button type="button" disabled={busy} className="underline"
                        onClick={() => act(() => blockClient(b.kind, b.pattern, b.reason || ''), `Blocked ${b.pattern} again.`)}>
                        Block again
                      </button>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </section>
        </>
      )}
    </div>
  )
}
